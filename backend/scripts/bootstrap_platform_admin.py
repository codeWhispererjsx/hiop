"""One-time interactive bootstrap for the first HIOP platform administrator."""
import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from app.core.security import hash_password
from app.db.database import SessionLocal
from app.models.user import User
from app.services.audit_service import create_audit_log


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first HIOP platform administrator")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", args.username):
        parser.error("username must be 3-50 characters using letters, numbers, dot, underscore, or hyphen")
    if "@" not in args.email or len(args.email) > 100:
        parser.error("enter a valid administrator email address")
    password = getpass.getpass("New platform administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("passwords do not match")
    if len(password) < 12 or not re.search(r"[A-Z]", password) or not re.search(r"[a-z]", password) or not re.search(r"\d", password):
        parser.error("password must be at least 12 characters with uppercase, lowercase, and a number")

    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == "platformadmin").first():
            parser.error("bootstrap refused: a platform administrator already exists")
        if db.query(User).filter((func.lower(User.username) == args.username.lower()) | (func.lower(User.email) == args.email.lower())).first():
            parser.error("username or email already exists")
        user = User(username=args.username, email=args.email.lower(), hashed_password=hash_password(password), role="platformadmin", is_active=True, organization_id=None)
        db.add(user)
        db.flush()
        create_audit_log(db, user.username, "PLATFORM_BOOTSTRAP_COMPLETED", "User", user.id, "Created the first platform administrator using the guarded bootstrap command")
        db.commit()
        print("First platform administrator created successfully.")
        return 0
    except SystemExit:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
