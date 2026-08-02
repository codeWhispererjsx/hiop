"""Reset HIOP operational data while preserving access and required catalogs.

Run without arguments to preview. Destructive execution requires the exact
confirmation token so this cannot be triggered accidentally.
"""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.db.database import engine


PRESERVE = {
    "alembic_version",
    "users",
    "system_settings",
    "automation_actions",
    "change_categories",
    "change_types",
    "ci_classes",
    "ci_lifecycles",
    "ci_relationship_types",
    "ci_statuses",
    "ci_types",
    "discovery_oui_vendors",
}


def preserved_tables(inspector) -> set[str]:
    """Include every table referenced by a preserved table."""
    keep = set(PRESERVE)
    changed = True
    while changed:
        changed = False
        for table in tuple(keep):
            for foreign_key in inspector.get_foreign_keys(table):
                parent = foreign_key.get("referred_table")
                if parent and parent not in keep:
                    keep.add(parent)
                    changed = True
    return keep


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", help="Required value: RESET-HIOP-DATA")
    parser.add_argument(
        "--remove-disabled-users",
        action="store_true",
        help="Also remove disabled test or retired accounts after dependent data is cleared.",
    )
    args = parser.parse_args()
    inspector = inspect(engine)
    all_tables = set(inspector.get_table_names())
    keep = preserved_tables(inspector)
    targets = sorted(all_tables - keep)

    with engine.connect() as connection:
        populated = []
        for table in targets:
            count = connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            if count:
                populated.append((table, count))
        print(f"Preserving {len(keep)} tables: {', '.join(sorted(keep))}")
        print(f"Reset targets: {len(targets)} tables; {sum(count for _, count in populated)} rows")
        for table, count in populated:
            print(f"  {table}: {count}")

    if args.confirm != "RESET-HIOP-DATA":
        print("Preview only. Re-run with --confirm RESET-HIOP-DATA to execute.")
        return

    quoted = ", ".join(f'"{table}"' for table in targets)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        if args.remove_disabled_users:
            removed = connection.execute(text("DELETE FROM users WHERE is_active = false")).rowcount
            print(f"Removed disabled users: {removed}")
    print("Operational data reset complete.")


if __name__ == "__main__":
    main()
