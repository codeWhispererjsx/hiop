import base64
import hashlib
import os

from app.core.config import settings
from app.services.secret_encryption_service import (
    SecretEncryptionError, SecretEncryptionService,
)


class ActiveDirectorySecretError(Exception):
    """Exception raised for secret encryption/decryption errors."""
    pass


class ActiveDirectorySecretService:
    @staticmethod
    def _get_fernet_key() -> bytes:
        """Compatibility helper retained for callers that inspect key availability."""
        raw_key = os.getenv("HIOP_AD_SECRET_KEY") or settings.secret_key
        if not raw_key:
            raise ActiveDirectorySecretError(
                "Encryption key for Active Directory secrets is missing."
            )
        return base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest())

    @classmethod
    def encrypt_secret(cls, plaintext: str) -> str:
        """Encrypt plaintext bind secret into ciphertext string."""
        if not plaintext:
            raise ActiveDirectorySecretError("Cannot encrypt empty secret.")
        try:
            cls._get_fernet_key()
            return SecretEncryptionService.encrypt(
                plaintext, environment_key="HIOP_AD_SECRET_KEY"
            )
        except SecretEncryptionError as err:
            raise ActiveDirectorySecretError(str(err)) from err

    @classmethod
    def decrypt_secret(cls, ciphertext: str) -> str:
        """Decrypt ciphertext bind secret back to plaintext string."""
        if not ciphertext:
            raise ActiveDirectorySecretError("Cannot decrypt empty ciphertext.")
        try:
            return SecretEncryptionService.decrypt(
                ciphertext, environment_key="HIOP_AD_SECRET_KEY"
            )
        except SecretEncryptionError as err:
            message = str(err)
            if "Invalid encryption key" in message:
                raise ActiveDirectorySecretError(
                    "Invalid encryption key or corrupted secret payload."
                ) from err
            raise ActiveDirectorySecretError(message) from err
