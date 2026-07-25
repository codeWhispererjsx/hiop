from app.models.snmp import SNMPPollRun


class SNMPPollingService:
    """Persistence lifecycle only; execution and scheduling are absent in Epic 4A."""
    def __init__(self, db):
        self.db = db

    def create_poll_run(self, target_id, actor, poll_type="composite"):
        run = SNMPPollRun(target_id=target_id, triggered_by=actor.id, poll_type=poll_type, status="pending")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def execute_poll(self, *args, **kwargs):
        raise NotImplementedError("Live SNMP polling is reserved for Epic 4B.")

    def cancel_poll(self, run):
        if run.status not in {"pending", "running"}:
            raise ValueError("Only pending or running polls may be cancelled.")
        run.status = "cancelled"
        self.db.commit()
        return run

    def finalize_poll_run(self, *args, **kwargs):
        raise NotImplementedError("Poll finalization is reserved for Epic 4B.")
