import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from app.core.config import settings
from app.core.rate_limit import FailedLoginLimiter
from app.core.security import ALGORITHM, create_access_token, decode_access_token
from app.schemas.device import DeviceCreate
from app.schemas.ticket import TicketCreate, TicketUpdate
from app.schemas.user import PasswordReset, UserCreate
from app.services.audit_service import _csv_safe as audit_csv_safe
from app.services.report_service import _csv_safe as report_csv_safe


class SecurityContractTests(unittest.TestCase):
    def test_access_tokens_have_required_security_claims(self):
        token = create_access_token({"sub": "security@example.com", "role": "admin"})
        payload = decode_access_token(token)
        self.assertEqual(payload["iss"], "hiop")
        self.assertEqual(payload["sub"], "security@example.com")
        self.assertIn("iat", payload)
        self.assertIn("exp", payload)
        self.assertIn("jti", payload)
        self.assertLessEqual(payload["exp"] - payload["iat"], settings.access_token_expire_minutes * 60)

    def test_expired_and_wrong_issuer_tokens_are_rejected(self):
        expired = jwt.encode(
            {"sub": "security@example.com", "iss": "hiop", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.secret_key,
            algorithm=ALGORITHM,
        )
        wrong_issuer = jwt.encode(
            {"sub": "security@example.com", "iss": "other", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.secret_key,
            algorithm=ALGORITHM,
        )
        self.assertIsNone(decode_access_token(expired))
        self.assertIsNone(decode_access_token(wrong_issuer))

    def test_failed_login_limiter_returns_retry_after(self):
        limiter = FailedLoginLimiter(limit=2, window_seconds=60)
        limiter.failure("client")
        limiter.failure("client")
        with self.assertRaises(HTTPException) as error:
            limiter.check("client")
        self.assertEqual(error.exception.status_code, 429)
        self.assertIn("Retry-After", error.exception.headers)
        limiter.success("client")
        limiter.check("client")

    def test_device_network_identifiers_are_normalized_and_validated(self):
        valid = DeviceCreate(
            asset_tag=" SEC-1 ", hostname="host", device_type="Server", brand="Brand", model="Model",
            serial_number="Serial", department="IT", location="Data room", ip_address="192.168.1.10",
            mac_address="aa-bb-cc-dd-ee-ff",
        )
        self.assertEqual(valid.asset_tag, "SEC-1")
        self.assertEqual(valid.mac_address, "AA:BB:CC:DD:EE:FF")
        with self.assertRaises(ValidationError):
            DeviceCreate(
                asset_tag="SEC-2", hostname="host", device_type="Server", brand="Brand", model="Model",
                serial_number="Serial", department="IT", location="Data room", ip_address="not-an-ip",
                mac_address="AA:BB:CC:DD:EE:FF",
            )

    def test_ticket_and_password_enums_are_restricted(self):
        with self.assertRaises(ValidationError):
            TicketCreate(title="Valid title", description="Valid description", priority="Emergency")
        with self.assertRaises(ValidationError):
            TicketUpdate(status="Deleted")
        with self.assertRaises(ValidationError):
            PasswordReset(password="alllowercase1")
        user = UserCreate(username="security-tech", email="security@example.com", password="StrongPass1", role="technician")
        self.assertEqual(user.role, "technician")

    def test_csv_exports_neutralize_spreadsheet_formulas(self):
        for sanitizer in (audit_csv_safe, report_csv_safe):
            self.assertEqual(sanitizer("=HYPERLINK('bad')"), "'=HYPERLINK('bad')")
            self.assertEqual(sanitizer("ordinary"), "ordinary")



if __name__ == "__main__":
    unittest.main()
