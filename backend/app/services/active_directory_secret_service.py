import base64
import hashlib
import os
# pyrefly: ignore [missing-import]
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class ActiveDirectorySecretError(Exception):
    """Exception raised for secret encryption/decryption errors."""
    pass


class ActiveDirectorySecretService:
    @staticmethod
    def _get_fernet_key() -> bytes:
        """Derive a 32-byte URL-safe base64 key from HIOP_AD_SECRET_KEY or settings.SECRET_KEY."""
        raw_key = os.getenv("HIOP_AD_SECRET_KEY") or getattr(settings, "SECRET_KEY", None)
        if not raw_key:
            raise ActiveDirectorySecretError("Encryption key for Active Directory secrets is missing.")
        
        # Derive deterministic 32-byte key via SHA-256
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    @classmethod
    def encrypt_secret(cls, plaintext: str) -> str:
        """Encrypt plaintext bind secret into ciphertext string."""
        if not plaintext:
            raise ActiveDirectorySecretError("Cannot encrypt empty secret.")
        try:
            key = cls._get_fernet_key()
            fernet = Fernet(key)
            encrypted = fernet.encrypt(plaintext.encode("utf-8"))
            return encrypted.decode("utf-8")
        except ActiveDirectorySecretError:
            raise
        except Exception as err:
            raise ActiveDirectorySecretError(f"Failed to encrypt secret: {err}") from err

    @classmethod
    def decrypt_secret(cls, ciphertext: str) -> str:
        """Decrypt ciphertext bind secret back to plaintext string."""
        if not ciphertext:
            raise ActiveDirectorySecretError("Cannot decrypt empty ciphertext.")
        try:
            key = cls._get_fernet_key()
            fernet = Fernet(key)
            decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken as err:
            raise ActiveDirectorySecretError("Invalid encryption key or corrupted secret payload.") from err
        except ActiveDirectorySecretError:
            raise
        except Exception as err:
            raise ActiveDirectorySecretError(f"Failed to decrypt secret: {err}") from err
