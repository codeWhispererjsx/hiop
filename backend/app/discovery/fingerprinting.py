"""Offline vendor hints and deliberately conservative device fingerprinting."""

from dataclasses import dataclass


OUI_VENDORS = {
    "00000c": "Cisco",
    "000142": "Cisco",
    "000c29": "VMware",
    "005056": "VMware",
    "001a11": "Google",
    "001422": "Dell",
    "0017a4": "HP",
    "001c73": "Aruba",
    "001f6c": "Hikvision",
    "0024d7": "Intel",
    "0418d6": "Ubiquiti",
    "24a43c": "Ubiquiti",
    "3c0754": "Apple",
    "48437c": "Dell",
    "687251": "Ubiquiti",
    "7483c2": "Ubiquiti",
}


@dataclass(frozen=True)
class Fingerprint:
    device_type_guess: str
    operating_system_guess: str | None
    confidence_score: float


def lookup_vendor(mac_address: str | None) -> str | None:
    if not mac_address:
        return None
    prefix = mac_address.replace(":", "").replace("-", "").lower()[:6]
    return OUI_VENDORS.get(prefix)


def fingerprint(hostname: str | None, vendor: str | None) -> Fingerprint:
    text = " ".join(part.lower() for part in (hostname, vendor) if part)
    rules = (
        ("printer", ("printer", "laserjet", "officejet", "epson", "xerox", "brother")),
        ("access point", ("accesspoint", "access-point", "ap-", "unifi", "ubiquiti", "aruba")),
        ("switch", ("switch", "sw-", "catalyst")),
        ("router", ("router", "gateway", "gw-")),
        ("ip phone", ("phone", "polycom", "yealink", "avaya")),
        ("pos", ("pos-", "pointofsale", "point-of-sale")),
        ("camera", ("camera", "cam-", "hikvision", "dahua", "axis")),
        ("server", ("server", "srv-", "vmware", "esxi", "hyperv")),
        ("mobile", ("iphone", "ipad", "android", "mobile")),
        ("workstation", ("desktop", "laptop", "workstation", "pc-", "macbook", "dell", "intel")),
    )
    guess = "unknown"
    for label, markers in rules:
        if any(marker in text for marker in markers):
            guess = label
            break

    evidence = int(bool(hostname)) + int(bool(vendor))
    if guess == "unknown":
        confidence = 15.0 + evidence * 10.0
    else:
        confidence = 45.0 + evidence * 15.0
    confidence = min(confidence, 85.0)

    os_guess = None
    if hostname:
        lower = hostname.lower()
        if any(marker in lower for marker in ("win-", "desktop-", "laptop-")):
            os_guess = "possibly Windows"
        elif any(marker in lower for marker in ("ubuntu", "linux", "debian", "rhel")):
            os_guess = "possibly Linux"
        elif any(marker in lower for marker in ("macbook", "imac")):
            os_guess = "possibly macOS"
    return Fingerprint(guess, os_guess, confidence)
