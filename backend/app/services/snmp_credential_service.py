from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.snmp import SNMPCredential
from app.core.config import settings
from app.schemas.snmp import SNMPCredentialCreate, SNMPCredentialSecretUpdate, SNMPCredentialUpdate
from app.services.audit_service import create_audit_log
from app.services.snmp_secret_service import SNMPSecretError, SNMPSecretService


class SNMPCredentialService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _encrypted(payload: SNMPCredentialCreate) -> dict:
        try:
            return {
                "community_encrypted": SNMPSecretService.encrypt_secret(payload.community) if payload.community else None,
                "authentication_secret_encrypted": SNMPSecretService.encrypt_secret(payload.authentication_secret) if payload.authentication_secret else None,
                "privacy_secret_encrypted": SNMPSecretService.encrypt_secret(payload.privacy_secret) if payload.privacy_secret else None,
            }
        except SNMPSecretError as error:
            raise HTTPException(503, "SNMP credential encryption is unavailable.") from error

    def create_credential(self, payload: SNMPCredentialCreate, actor):
        if payload.version.value == "v1" and not settings.snmp_allow_v1:
            raise HTTPException(400, "SNMPv1 is disabled by security policy.")
        if (
            settings.environment == "production"
            and settings.snmp_v3_required_in_production
            and payload.version.value != "v3"
        ):
            raise HTTPException(400, "SNMPv3 is required in production.")
        if (
            payload.authentication_protocol.value == "MD5"
            or payload.privacy_protocol.value == "DES"
        ) and not settings.snmp_allow_legacy_protocols:
            raise HTTPException(400, "Legacy SNMP security protocols are disabled.")
        values = payload.model_dump(
            mode="json",
            exclude={"community", "authentication_secret", "privacy_secret"},
        )
        values.update(self._encrypted(payload))
        row = SNMPCredential(**values, created_by=actor.id, updated_by=actor.id)
        self.db.add(row)
        create_audit_log(self.db, actor.username, "SNMP_CREDENTIAL_CREATED", "SNMPCredential", str(row.id), f"Created SNMP credential profile '{row.name}'.")
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise HTTPException(409, "An SNMP credential with this name already exists.") from error
        self.db.refresh(row)
        return row

    def update_credential(self, row: SNMPCredential, payload: SNMPCredentialUpdate, actor):
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_CREDENTIAL_UPDATED", "SNMPCredential", str(row.id), f"Updated SNMP credential profile '{row.name}'.")
        self.db.commit()
        self.db.refresh(row)
        return row

    def rotate_secret(self, row: SNMPCredential, payload: SNMPCredentialSecretUpdate, actor):
        if row.version in {"v1", "v2c"} and (
            payload.authentication_secret or payload.privacy_secret or not payload.community
        ):
            raise HTTPException(400, "SNMPv1/v2c rotation accepts only a community string.")
        if row.version == "v3":
            if payload.community:
                raise HTTPException(400, "SNMPv3 rotation cannot include a community string.")
            if row.security_level == "noAuthNoPriv":
                raise HTTPException(400, "noAuthNoPriv has no secret material to rotate.")
            if row.security_level == "authNoPriv" and (
                not payload.authentication_secret or payload.privacy_secret
            ):
                raise HTTPException(400, "authNoPriv rotation requires only an authentication secret.")
            if row.security_level == "authPriv" and not (
                payload.authentication_secret or payload.privacy_secret
            ):
                raise HTTPException(400, "authPriv rotation requires authentication or privacy secret material.")
        try:
            if payload.community:
                row.community_encrypted = SNMPSecretService.encrypt_secret(payload.community)
            if payload.authentication_secret:
                row.authentication_secret_encrypted = SNMPSecretService.encrypt_secret(payload.authentication_secret)
            if payload.privacy_secret:
                row.privacy_secret_encrypted = SNMPSecretService.encrypt_secret(payload.privacy_secret)
        except SNMPSecretError as error:
            raise HTTPException(503, "SNMP credential encryption is unavailable.") from error
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_SECRET_ROTATED", "SNMPCredential", str(row.id), "Rotated encrypted SNMP credential material.")
        self.db.commit()
        self.db.refresh(row)
        return row

    def disable_credential(self, row: SNMPCredential, actor):
        row.enabled = False
        row.updated_by = actor.id
        create_audit_log(self.db, actor.username, "SNMP_CREDENTIAL_DISABLED", "SNMPCredential", str(row.id), f"Disabled SNMP credential profile '{row.name}'.")
        self.db.commit()
        self.db.refresh(row)
        return row
