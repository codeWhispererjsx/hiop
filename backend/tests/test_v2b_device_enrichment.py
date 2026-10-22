from app.main import app
from app.api.v1 import discovery_intelligence
from app.schemas.settings import SettingsBundle


def test_snmp_enrichment_is_not_exposed_by_the_application():
    paths = set(app.openapi()["paths"])
    assert not any("/snmp" in path for path in paths)
    assert not any(path.endswith("/discovery-intelligence/results/{id}/enrich") for path in paths)
    assert not hasattr(SettingsBundle, "snmp")
    assert not hasattr(discovery_intelligence, "enrich_result")
