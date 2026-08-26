from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).parents[2]


def test_production_image_contains_postgres_backup_tools():
    dockerfile = ROOT.joinpath("backend/Dockerfile").read_text(encoding="utf-8")
    assert "postgresql-client" in dockerfile
    assert "/var/lib/hiop/backups" in dockerfile


def test_compose_persists_and_schedules_database_backups():
    compose = ROOT.joinpath("docker-compose.yml").read_text(encoding="utf-8")
    backend = compose.split("\n  backend:", 1)[1].split("\n  frontend:", 1)[0]
    assert "SCHEDULED_BACKUP_ENABLED" in compose
    assert "RESTORE_TEST_DATABASE_URL" in compose
    assert "hiop_backup_data:/var/lib/hiop/backups" in backend
    assert "hiop_backup_data:" in compose


def test_windows_backup_script_has_no_default_password():
    script = ROOT.joinpath("scripts/backup-postgres.ps1").read_text(encoding="utf-8")
    assert '"Admin"' not in script
    assert "Set PGPASSWORD" in script


def test_production_example_fails_closed_without_real_operator_values():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-production-readiness.py"), "--env-file", str(ROOT / "backend/.env.production.example")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "RESULT NOT READY" in result.stdout
    assert "SECRET_KEY" in result.stdout
    assert "REPLACE_WITH" not in result.stdout


def test_readiness_checker_accepts_complete_non_secret_test_configuration():
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "DATABASE_URL": "postgresql+psycopg2://hiop:test-password@db:5432/hiop",
        "SECRET_KEY": "s" * 64,
        "HIOP_AD_SECRET_KEY": "a" * 64,
        "HIOP_SNMP_SECRET_KEY": "n" * 64,
        "HIOP_DISCOVERY_CREDENTIAL_KEY": "d" * 64,
        "CORS_ORIGINS": '["https://hiop.hotel.invalid"]',
        "REQUIRE_EMAIL_VERIFICATION": "true",
        "SMTP_HOST": "smtp.test.invalid",
        "SMTP_USERNAME": "test-user",
        "SMTP_PASSWORD": "test-password",
        "SMTP_SENDER_ADDRESS": "hiop@hotel.invalid",
        "SCHEDULED_BACKUP_ENABLED": "true",
        "BACKUP_DIR": "/var/lib/hiop/backups",
        "RESTORE_TEST_DATABASE_URL": "postgresql+psycopg2://hiop:test-password@db:5432/hiop_restore_drill",
        "ENABLE_SUBDOMAIN_ROUTING": "false",
        "SNMP_ALLOW_V1": "false",
        "SNMP_ALLOW_LEGACY_PROTOCOLS": "false",
    }
    with tempfile.TemporaryDirectory() as directory:
        env_file = Path(directory) / "production.env"
        env_file.write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check-production-readiness.py"), "--env-file", str(env_file)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode == 0
    assert "RESULT CONFIGURATION READY" in result.stdout
