"""Shared authenticated encryption for integration secrets."""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretEncryptionError(Exception):
    pass


class SecretEncryptionService:
    @staticmethod
    def derived_key(environment_key: str) -> bytes:
        raw_key = os.getenv(environment_key) or settings.secret_key
        if not raw_key:
            raise SecretEncryptionError("Integration secret encryption key is unavailable.")
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    @classmethod
    def _fernet(cls, environment_key: str) -> Fernet:
        return Fernet(cls.derived_key(environment_key))

    @classmethod
    def encrypt(cls, plaintext: str, *, environment_key: str) -> str:
        if not plaintext:
            raise SecretEncryptionError("Cannot encrypt an empty secret.")
        try:
            return cls._fernet(environment_key).encrypt(plaintext.encode()).decode()
        except SecretEncryptionError:
            raise
        except Exception as error:
            raise SecretEncryptionError("Integration secret encryption failed.") from error

    @classmethod
    def decrypt(cls, ciphertext: str, *, environment_key: str) -> str:
        if not ciphertext:
            raise SecretEncryptionError("Cannot decrypt an empty secret payload.")
        try:
            return cls._fernet(environment_key).decrypt(ciphertext.encode()).decode()
        except InvalidToken as error:
            raise SecretEncryptionError("Invalid encryption key or corrupted secret payload.") from error
        except SecretEncryptionError:
            raise
        except Exception as error:
            raise SecretEncryptionError("Integration secret decryption failed.") from error
