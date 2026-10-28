from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset_intelligence import ManagedAsset
from app.services.device_correlation_service import normalized_hostname

AssetIndex = dict[tuple[UUID | None, str, str], list[ManagedAsset]]


def _value(row, field: str):
    return row.get(field) if isinstance(row, Mapping) else getattr(row, field, None)


def _normalized_hostname(value: str | None) -> str | None:
    return normalized_hostname(value)


def _normalized_serial(value: str | None) -> str | None:
    text = (value or "").strip().casefold()
    if not text or text in {"n/a", "na", "unknown", "unknown device", "not available"}:
        return None
    return text


def index_imported_assets(assets: list[ManagedAsset]) -> AssetIndex:
    index: AssetIndex = {}
    for asset in assets:
        if asset.source != "inventory_import" or asset.device_id or asset.status == "retired":
            continue
        hostname = _normalized_hostname(asset.name)
        serial_number = _normalized_serial(asset.serial_number)
        if hostname:
            index.setdefault((asset.property_id, "hostname", hostname), []).append(asset)
        if serial_number:
            index.setdefault((asset.property_id, "serial_number", serial_number), []).append(asset)
    return index


def find_imported_asset_candidates(result, asset_index: AssetIndex) -> list[dict[str, object]]:
    hostnames = {
        value
        for value in (
            _normalized_hostname(_value(result, "primary_hostname")),
            _normalized_hostname(_value(result, "fqdn")),
            _normalized_hostname(_value(result, "ad_computer_name")),
        )
        if value
    }
    serial_number = _normalized_serial(_value(result, "serial_number"))
    property_id = _value(result, "property_id")
    if not property_id or (not hostnames and not serial_number):
        return []

    matches_by_asset: dict[UUID, tuple[ManagedAsset, set[str]]] = {}
    for hostname in hostnames:
        for asset in asset_index.get((property_id, "hostname", hostname), []):
            matches_by_asset.setdefault(asset.id, (asset, set()))[1].add("hostname")
    if serial_number:
        for asset in asset_index.get((property_id, "serial_number", serial_number), []):
            matches_by_asset.setdefault(asset.id, (asset, set()))[1].add("serial_number")

    candidates = []
    for asset, matched_fields in matches_by_asset.values():
        candidates.append(
            {
                "asset_id": str(asset.id),
                "asset_number": asset.asset_number,
                "name": asset.name,
                "department": asset.department_name,
                "location": asset.location_name,
                "matched_fields": sorted(matched_fields),
            }
        )
    return candidates


def imported_asset_candidates_for_result(
    db: Session,
    result,
    organization_id: UUID | None,
) -> list[dict[str, object]]:
    if not organization_id or not result.property_id:
        return []
    assets = db.scalars(
        select(ManagedAsset).where(
            ManagedAsset.organization_id == organization_id,
            ManagedAsset.property_id == result.property_id,
            ManagedAsset.source == "inventory_import",
            ManagedAsset.device_id.is_(None),
            ManagedAsset.status != "retired",
        )
    ).all()
    return find_imported_asset_candidates(result, index_imported_assets(assets))
