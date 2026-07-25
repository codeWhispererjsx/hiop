class SNMPDiscoveryService:
    def __init__(self, db):
        self.db = db

    def build_candidate(self, *args, **kwargs):
        raise NotImplementedError("SNMP discovery candidates are reserved for Epic 4B.")

    def match_inventory(self, *args, **kwargs):
        raise NotImplementedError("SNMP inventory matching is reserved for Epic 4B.")

    def review_candidate(self, *args, **kwargs):
        raise NotImplementedError("SNMP candidate review is reserved for Epic 4B.")
