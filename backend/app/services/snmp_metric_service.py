class SNMPMetricService:
    """Bounded metric query surface; collection is not implemented."""
    def __init__(self, repository):
        self.repository = repository

    def list_metrics(self, *, page=1, page_size=50, filters=None):
        return self.repository.list(page=page, page_size=min(page_size, 100), filters=filters)
