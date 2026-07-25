from app.services.secret_encryption_service import (
    SecretEncryptionError, SecretEncryptionService,
)


class SNMPSecretError(SecretEncryptionError):
    pass


class SNMPSecretService:
    KEY_NAME = "HIOP_SNMP_SECRET_KEY"

    @classmethod
    def encrypt_secret(cls, plaintext: str) -> str:
        try:
            return SecretEncryptionService.encrypt(plaintext, environment_key=cls.KEY_NAME)
        except SecretEncryptionError as error:
            raise SNMPSecretError(str(error)) from error

    @classmethod
    def decrypt_secret(cls, ciphertext: str) -> str:
        try:
            return SecretEncryptionService.decrypt(ciphertext, environment_key=cls.KEY_NAME)
        except SecretEncryptionError as error:
            raise SNMPSecretError(str(error)) from error
