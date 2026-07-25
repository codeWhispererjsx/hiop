from app.schemas.snmp import validate_oid


class SNMPProfileService:
    def __init__(self, db):
        self.db = db

    def classify_device(self, *args, **kwargs):
        raise NotImplementedError("SNMP classification is reserved for Epic 4B.")

    def resolve_profile(self, *args, **kwargs):
        raise NotImplementedError("SNMP profile resolution is reserved for Epic 4B.")

    def validate_oid_definition(self, oid: str) -> str:
        return validate_oid(oid)
