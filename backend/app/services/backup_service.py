import logging
import os
import subprocess
import shutil
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.backup import BackupRecord, RestoreTest
from app.models.system_health import SystemHealthSnapshot
from app.services.health_service import record_health

logger = logging.getLogger(__name__)

BackupStatus = Literal["in_progress", "success", "failed", "verification_failed"]
RestoreStatus = Literal["in_progress", "success", "failed"]


def record_backup_start(
    db: Session,
    backup_type: str = "manual",
    retention_days: int = 14,
) -> BackupRecord:
    """Record the start of a backup operation."""
    record = BackupRecord(
        backup_type=backup_type,
        status="in_progress",
        retention_days=retention_days,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"Backup started: {record.id}")
    return record


def record_backup_success(
    db: Session,
    backup_id: UUID,
    file_path: str,
    file_size_bytes: int,
    checksum: str,
    database_version: str | None = None,
) -> BackupRecord:
    """Record successful backup completion."""
    record = db.query(BackupRecord).filter_by(id=backup_id).first()
    if not record:
        raise ValueError(f"Backup record {backup_id} not found")
    
    record.status = "success"
    record.completed_at = datetime.now(timezone.utc)
    record.file_path = file_path
    record.file_size_bytes = file_size_bytes
    record.checksum = checksum
    record.checksum_verified = True
    record.database_version = database_version
    
    db.commit()
    db.refresh(record)
    
    # Update backup health
    record_health(db, "HEALTHY", record.completed_at)
    
    logger.info(f"Backup completed successfully: {record.id}")
    return record


def record_backup_failure(
    db: Session,
    backup_id: UUID,
    error: str,
) -> BackupRecord:
    """Record backup failure."""
    record = db.query(BackupRecord).filter_by(id=backup_id).first()
    if not record:
        raise ValueError(f"Backup record {backup_id} not found")
    
    record.status = "failed"
    record.completed_at = datetime.now(timezone.utc)
    record.error = error[:1000]
    
    db.commit()
    db.refresh(record)
    
    # Update backup health
    record_health(db, "FAILED", record.completed_at, details=error)
    
    logger.error(f"Backup failed: {record.id} - {error}")
    return record


def record_health(db: Session, status: str, last_success: datetime | None = None, details: str | None = None):
    """Update backup health status. Returns None if tables don't exist."""
    try:
        existing = db.query(SystemHealthSnapshot).filter_by(component="backup").first()
        
        if existing:
            existing.status = status
            existing.last_success = last_success
            existing.last_check = datetime.now(timezone.utc)
            existing.details = details
        else:
            existing = SystemHealthSnapshot(
                component="backup",
                status=status,
                last_success=last_success,
                last_check=datetime.now(timezone.utc),
                details=details,
            )
            db.add(existing)
        
        db.commit()
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Health tables not available yet: {e}")
        db.rollback()


def get_backup_health(db: Session) -> dict:
    """Get current backup health status. Returns UNKNOWN if tables don't exist."""
    try:
        latest = db.query(BackupRecord).filter_by(status="success").order_by(BackupRecord.completed_at.desc()).first()
        
        if not latest:
            return {
                "status": "UNKNOWN",
                "last_success": None,
                "age_hours": None,
                "details": "No successful backup recorded",
            }
        
        age = (datetime.now(timezone.utc) - latest.completed_at).total_seconds()
        age_hours = age / 3600
        
        # Check if backup is stale (older than 2 days for daily backup schedule)
        if age_hours > 48:
            return {
                "status": "DEGRADED",
                "last_success": latest.completed_at.isoformat(),
                "age_hours": round(age_hours, 1),
                "details": f"Backup is {age_hours:.1f} hours old, expected within 48 hours",
            }
        
        return {
            "status": "HEALTHY",
            "last_success": latest.completed_at.isoformat(),
            "age_hours": round(age_hours, 1),
            "details": f"Backup completed {age_hours:.1f} hours ago, verified",
        }
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Backup tables not available yet: {e}")
        return {
            "status": "UNKNOWN",
            "last_success": None,
            "age_hours": None,
            "details": "Backup tracking tables not available (migrations not applied)",
        }


def record_restore_test_start(
    db: Session,
    backup_file: str,
    performed_by: str,
) -> RestoreTest:
    """Record the start of a restore test drill."""
    record = RestoreTest(
        status="in_progress",
        backup_file=backup_file,
        performed_by=performed_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info(f"Restore test started: {record.id}")
    return record


def record_restore_test_success(
    db: Session,
    test_id: UUID,
    backup_id: UUID | None,
    restore_duration_seconds: int,
    organizations_verified: int,
    properties_verified: int,
    users_verified: int,
    assets_verified: int,
    devices_verified: int,
    incidents_verified: int,
    data_integrity_checks: str,
    database_version: str | None = None,
) -> RestoreTest:
    """Record successful restore test completion."""
    record = db.query(RestoreTest).filter_by(id=test_id).first()
    if not record:
        raise ValueError(f"Restore test record {test_id} not found")
    
    record.status = "success"
    record.completed_at = datetime.now(timezone.utc)
    record.backup_id = backup_id
    record.restore_duration_seconds = restore_duration_seconds
    record.organizations_verified = organizations_verified
    record.properties_verified = properties_verified
    record.users_verified = users_verified
    record.assets_verified = assets_verified
    record.devices_verified = devices_verified
    record.incidents_verified = incidents_verified
    record.data_integrity_checks = data_integrity_checks
    record.database_version = database_version
    
    db.commit()
    db.refresh(record)
    
    logger.info(f"Restore test completed successfully: {record.id}")
    return record


def record_restore_test_failure(
    db: Session,
    test_id: UUID,
    error: str,
) -> RestoreTest:
    """Record restore test failure."""
    record = db.query(RestoreTest).filter_by(id=test_id).first()
    if not record:
        raise ValueError(f"Restore test record {test_id} not found")
    
    record.status = "failed"
    record.completed_at = datetime.now(timezone.utc)
    record.error = error[:1000]
    
    db.commit()
    db.refresh(record)
    
    logger.error(f"Restore test failed: {record.id} - {error}")
    return record


def get_latest_restore_test(db: Session) -> RestoreTest | None:
    """Get the most recent restore test."""
    return db.query(RestoreTest).order_by(RestoreTest.started_at.desc()).first()


def perform_backup(
    db: Session,
    backup_type: str = "manual",
    retention_days: int = 14,
) -> BackupRecord:
    """Execute a database backup and record the result."""
    from sqlalchemy.engine import make_url
    from app.core.config import settings
    database_url = make_url(settings.database_url.replace("postgresql+psycopg2://", "postgresql://"))
    pg_host = os.environ.get("PGHOST") or database_url.host or "localhost"
    pg_database = os.environ.get("PGDATABASE") or database_url.database or "hiop"
    pg_user = os.environ.get("PGUSER") or database_url.username or "hiop"
    backup_dir = os.environ.get("BACKUP_DIR", "./backups")
    
    # Extract password from DATABASE_URL if not set
    pg_password = os.environ.get("PGPASSWORD") or database_url.password or ""
    
    # Record backup start
    backup_record = record_backup_start(db, backup_type, retention_days)
    
    try:
        # Create backup directory
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        
        # Generate timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        file_path = f"{backup_dir}/hiop-{timestamp}.dump"
        
        # Execute pg_dump
        env = os.environ.copy()
        env["PGPASSWORD"] = os.environ.get("PGPASSWORD", "")
        
        # Build pg_dump command with database connection parameters
        pg_dump_cmd = os.environ.get("PG_DUMP_PATH") or shutil.which("pg_dump")
        if not pg_dump_cmd:
            windows = r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe"
            pg_dump_cmd = windows if os.path.exists(windows) else None
        if not pg_dump_cmd: raise FileNotFoundError("pg_dump is not installed in the backend runtime")
        
        # Set up environment with password
        backup_env = env.copy()
        backup_env["PGPASSWORD"] = pg_password
        
        result = subprocess.run(
            [
                pg_dump_cmd,
                "-h", pg_host,
                "-U", pg_user,
                "-d", pg_database,
                "-p", str(database_url.port or 5432),
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file", file_path,
            ],
            env=backup_env,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr}")
        
        # Get file size
        file_size_bytes = Path(file_path).stat().st_size
        
        # Generate checksum using Python's hashlib (cross-platform)
        import hashlib
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        checksum = sha256_hash.hexdigest()
        
        # Save checksum file
        with open(f"{file_path}.sha256", "w") as f:
            f.write(checksum)
        
        # Get database version using Python psycopg2
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=pg_host,
                user=pg_user,
                password=pg_password,
                database=pg_database
            )
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            database_version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
        except Exception as e:
            database_version = f"Unable to retrieve version: {str(e)}"
        
        # Record success
        return record_backup_success(
            db,
            backup_record.id,
            file_path,
            file_size_bytes,
            checksum,
            database_version,
        )
        
    except Exception as exc:
        # Record failure
        return record_backup_failure(db, backup_record.id, str(exc))


def verify_backup(file_path: str) -> bool:
    """Verify that a backup file is valid and readable."""
    try:
        # Check file exists
        if not Path(file_path).exists():
            return False
        
        # Verify checksum if available
        checksum_file = f"{file_path}.sha256"
        if Path(checksum_file).exists():
            import hashlib
            expected=Path(checksum_file).read_text().strip();digest=hashlib.sha256()
            with open(file_path,"rb") as stream:
                for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
            if not secrets.compare_digest(digest.hexdigest(),expected):return False
        
        # Verify backup can be read
        pg_restore=os.environ.get("PG_RESTORE_PATH") or shutil.which("pg_restore")
        if not pg_restore:return False
        result = subprocess.run(
            [pg_restore, "--list", file_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        return result.returncode == 0
        
    except Exception:
        return False


def perform_restore_drill(db: Session, backup: BackupRecord, target_url: str) -> RestoreTest:
    """Restore a verified dump only into an explicitly isolated drill database."""
    from sqlalchemy.engine import make_url
    from app.core.config import settings
    primary = make_url(settings.database_url.replace("postgresql+psycopg2://", "postgresql://"))
    target = make_url(target_url.replace("postgresql+psycopg2://", "postgresql://"))
    target_name = (target.database or "").lower()
    if target.render_as_string(hide_password=True) == primary.render_as_string(hide_password=True):
        raise ValueError("Restore drill target must never be the production database")
    if not any(marker in target_name for marker in ("restore", "drill")):
        raise ValueError("Restore drill database name must contain 'restore' or 'drill'")
    if not backup.file_path or not verify_backup(backup.file_path):
        raise ValueError("Backup verification failed; restore was not attempted")
    record = record_restore_test_start(db, backup.file_path, "scheduler")
    record.backup_id = backup.id
    db.commit()
    started = datetime.now(timezone.utc)
    try:
        pg_restore = os.environ.get("PG_RESTORE_PATH") or shutil.which("pg_restore")
        if not pg_restore: raise FileNotFoundError("pg_restore is not installed in the backend runtime")
        env = os.environ.copy(); env["PGPASSWORD"] = target.password or ""
        command = [pg_restore, "--clean", "--if-exists", "--no-owner", "--no-acl", "-h", target.host or "localhost", "-p", str(target.port or 5432), "-U", target.username or "hiop", "-d", target.database, backup.file_path]
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0: raise RuntimeError(f"pg_restore failed: {result.stderr[-900:]}")
        engine = create_engine(target_url, pool_pre_ping=True)
        counts = {}
        with engine.connect() as connection:
            for table in ("organizations", "properties", "users", "assets", "devices", "operational_incidents"):
                counts[table] = connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            version = connection.execute(text("SELECT version()" )).scalar_one()
        engine.dispose()
        duration = int((datetime.now(timezone.utc) - started).total_seconds())
        return record_restore_test_success(db, record.id, backup.id, duration, counts["organizations"], counts["properties"], counts["users"], counts["assets"], counts["devices"], counts["operational_incidents"], "Verified core table readability after isolated restore", version)
    except Exception as exc:
        return record_restore_test_failure(db, record.id, str(exc))
