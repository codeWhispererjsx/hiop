import re
import fnmatch
import ipaddress
from difflib import SequenceMatcher
from typing import Any, Mapping


IDENTITY_FIELDS = ("mac_address", "asset_tag", "serial_number")
TEXT_FIELDS = ("hostname", "department_name", "building_name", "floor_name", "room_name", "vendor", "brand", "model")
WEIGHTS = {
    "mac_address": 96,
    "asset_tag": 95,
    "serial_number": 92,
    "hostname": 40,
    "ip_address": 35,
    "department_name": 10,
    "room_name": 10,
    "network_zone": 12,
    "vendor": 5,
    "brand": 5,
    "model": 7,
}


def normalized(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().lower().split())
    return text or None


def compact(value: Any) -> str | None:
    text = normalized(value)
    return re.sub(r"[^a-z0-9]", "", text) if text else None


def normalize_record(record: Any) -> dict[str, str | None]:
    def get(name: str, *alternatives: str) -> Any:
        if isinstance(record, Mapping):
            return next((record.get(key) for key in (name, *alternatives) if record.get(key) is not None), None)
        return next((getattr(record, key, None) for key in (name, *alternatives) if getattr(record, key, None) is not None), None)
    return {
        "mac_address": compact(get("mac_address")),
        "asset_tag": compact(get("asset_tag")),
        "serial_number": compact(get("serial_number")),
        "hostname": normalized(get("hostname")),
        "ip_address": normalized(get("ip_address")),
        "department_name": normalized(get("department_name", "department")),
        "building_name": normalized(get("building_name")),
        "floor_name": normalized(get("floor_name")),
        "room_name": normalized(get("room_name", "location")),
        "network_zone": normalized(get("network_zone")),
        "vendor": normalized(get("vendor")),
        "brand": normalized(get("brand")),
        "model": normalized(get("model")),
    }


def classify(score: int, thresholds: Mapping[str, int]) -> str:
    if score >= thresholds["exact"]: return "exact"
    if score >= thresholds["strong"]: return "strong"
    if score >= thresholds["probable"]: return "probable"
    if score >= thresholds["weak"]: return "weak"
    return "none"


def score_records(source: Any, candidate: Any, settings: Mapping[str, Any]) -> dict[str, Any]:
    left, right = normalize_record(source), normalize_record(candidate)
    evidence: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    matching: list[str] = []
    score = 0
    for field, weight in WEIGHTS.items():
        if left[field] and right[field] and left[field] == right[field]:
            matching.append(field)
            score += weight
            evidence.append({"field": field, "kind": "exact", "weight": weight})
    for field in IDENTITY_FIELDS:
        if left[field] and right[field] and left[field] != right[field]:
            penalty = int(settings["conflict_penalty"])
            score -= penalty
            conflicts.append({"field": field, "imported": left[field], "candidate": right[field], "penalty": penalty})
    if matching and any(field in IDENTITY_FIELDS for field in matching) and left["hostname"] and right["hostname"] and left["hostname"] != right["hostname"]:
        penalty = int(settings["conflict_penalty"])
        score -= penalty
        conflicts.append({"field": "hostname", "imported": left["hostname"], "candidate": right["hostname"], "penalty": penalty})
    fuzzy_enabled = bool(settings["fuzzy_matching_enabled"])
    fuzzy_fields = ("hostname", "asset_tag", "department_name", "building_name", "floor_name", "room_name", "vendor", "brand", "model")
    if fuzzy_enabled:
        for field in fuzzy_fields:
            if field in matching or not left[field] or not right[field]:
                continue
            similarity = round(SequenceMatcher(None, left[field], right[field]).ratio() * 100)
            threshold = int(settings["hostname_similarity_threshold"] if field == "hostname" else settings["fuzzy_similarity_threshold"])
            if similarity >= threshold:
                contribution = min(18 if field == "hostname" else 8, max(1, similarity // 10))
                score += contribution
                evidence.append({"field": field, "kind": "similar", "similarity": similarity, "weight": contribution})
    score = max(0, min(100, score))
    thresholds = {key: int(settings[f"{key}_match_threshold"]) for key in ("exact", "strong", "probable", "weak")}
    level = classify(score, thresholds)
    fuzzy_only = bool(evidence) and not matching
    if conflicts:
        action = "review"
    elif level in {"exact", "strong"} and not fuzzy_only:
        action = "link"
    elif level in {"probable", "weak"}:
        action = "review"
    else:
        action = "create_new"
    return {"score": score, "level": level, "evidence": evidence, "conflicts": conflicts, "matching_fields": matching, "recommended_action": action, "fuzzy_only": fuzzy_only}


def select_subnet_rule(address: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    ip = ipaddress.ip_address(address)
    matches = []
    for rule in rules:
        network = ipaddress.ip_network(str(rule.get("cidr", "")), strict=False)
        if ip in network: matches.append((network.prefixlen, rule))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def select_hostname_rule(hostname: str, rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    for rule in rules:
        pattern = str(rule.get("pattern", ""))
        if pattern and len(pattern) <= 128 and fnmatch.fnmatchcase(hostname.lower(), pattern.lower()):
            return rule
    return None
