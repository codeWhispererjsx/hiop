class CollectorError(Exception): pass
class MockCollector:
    """Safe foundation collector; deliberately performs no network I/O."""
    def describe_capabilities(self): return {"connection_test":True,"live_collection":False,"host_key_verification":True,"tls_verification":True}
    def test_connection(self): return {"status":"passed","stages":[{"name":"assignment","status":"passed"},{"name":"transport","status":"warning","message":"Mock collector; no device connection performed"}]}
    def collect_configuration(self): raise CollectorError("Live collectors are disabled in Epic 2B test foundation")
