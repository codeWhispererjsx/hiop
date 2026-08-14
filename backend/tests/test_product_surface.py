from app.main import app


def test_removed_specialist_apis_are_not_exposed():
    paths = set(app.openapi()["paths"])
    removed_prefixes = (
        "/api/v1/active-directory",
        "/api/v1/analytics",
        "/api/v1/business-intelligence",
        "/api/v1/cmdb",
        "/api/v1/configuration-management",
        "/api/v1/reports",
        "/api/v1/snmp",
        "/api/v1/tickets",
        "/api/v1/topologies",
    )
    assert not [path for path in paths if path.startswith(removed_prefixes)]


def test_five_pillar_api_foundation_remains_exposed():
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/v1/auth/login",
        "/api/v1/dashboard/",
        "/api/v1/devices/",
        "/api/v1/network/scan",
        "/api/v1/discovery-intelligence/quick-scan",
        "/api/v1/automation/workflows",
        "/api/v1/incidents",
        "/api/v1/settings",
        "/api/v1/users",
    }
    assert expected <= paths
