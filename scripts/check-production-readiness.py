"""Fail-closed production configuration check for HIOP deployments.

This command reads an environment file without printing secret values. It does
not contact the hotel network or alter application data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


PLACEHOLDERS = ("replace", "change-me", "example.com", "your-")
REQUIRED_SECRETS = (
    "SECRET_KEY",
    "HIOP_AD_SECRET_KEY",
    "HIOP_SNMP_SECRET_KEY",
    "HIOP_DISCOVERY_CREDENTIAL_KEY",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate HIOP production configuration without exposing secrets.")
    parser.add_argument("--env-file", type=Path, required=True, help="Protected production environment file")
    args = parser.parse_args()
    if not args.env_file.is_file():
        print(f"FAIL environment file not found: {args.env_file}")
        return 1

    env = load_env(args.env_file)
    failures: list[str] = []
    warnings: list[str] = []

    if env.get("ENVIRONMENT") != "production":
        failures.append("ENVIRONMENT must be production")
    if truthy(env.get("DEBUG")):
        failures.append("DEBUG must be false")

    database_url = env.get("DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        failures.append("DATABASE_URL must use PostgreSQL")
    if any(marker in database_url.lower() for marker in PLACEHOLDERS):
        failures.append("DATABASE_URL contains a placeholder")

    for name in REQUIRED_SECRETS:
        value = env.get(name, "")
        if len(value) < 32 or any(marker in value.lower() for marker in PLACEHOLDERS):
            failures.append(f"{name} must be a non-placeholder secret of at least 32 characters")

    try:
        origins = json.loads(env.get("CORS_ORIGINS", "[]"))
    except json.JSONDecodeError:
        origins = []
        failures.append("CORS_ORIGINS must be a JSON array")
    if not origins:
        failures.append("CORS_ORIGINS must contain the deployed frontend origin")
    elif any(not isinstance(origin, str) or not origin.startswith("https://") or "localhost" in origin or any(marker in origin.lower() for marker in PLACEHOLDERS) for origin in origins):
        failures.append("Every production CORS origin must be an explicit HTTPS URL")

    if truthy(env.get("REQUIRE_EMAIL_VERIFICATION")):
        for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SENDER_ADDRESS"):
            if not env.get(name):
                failures.append(f"{name} is required when email verification is enabled")

    if not truthy(env.get("SCHEDULED_BACKUP_ENABLED")):
        failures.append("SCHEDULED_BACKUP_ENABLED must be true")
    backup_dir = env.get("BACKUP_DIR", "")
    if not backup_dir or not (Path(backup_dir).is_absolute() or backup_dir.startswith("/")):
        failures.append("BACKUP_DIR must be an absolute persistent path")

    restore_url = env.get("RESTORE_TEST_DATABASE_URL", "")
    if not restore_url:
        warnings.append("RESTORE_TEST_DATABASE_URL is not configured; automated restore drills will remain disabled")
    elif restore_url == database_url or not any(marker in restore_url.lower() for marker in ("restore", "drill")):
        failures.append("RESTORE_TEST_DATABASE_URL must be a separate database containing restore or drill in its name")

    if truthy(env.get("ENABLE_SUBDOMAIN_ROUTING")):
        domain = env.get("BASE_DOMAIN", "")
        if not domain or domain in {"localhost", "127.0.0.1"} or urlparse(f"//{domain}").hostname is None:
            failures.append("Subdomain routing requires a verified non-local BASE_DOMAIN")

    if truthy(env.get("SNMP_ALLOW_V1")) or truthy(env.get("SNMP_ALLOW_LEGACY_PROTOCOLS")):
        failures.append("Legacy SNMP protocols must be disabled")

    for item in warnings:
        print(f"WARN {item}")
    for item in failures:
        print(f"FAIL {item}")
    if failures:
        print(f"RESULT NOT READY ({len(failures)} blocking issue(s), {len(warnings)} warning(s))")
        return 1
    print(f"RESULT CONFIGURATION READY ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
