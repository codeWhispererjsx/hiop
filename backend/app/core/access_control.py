"""Small, explicit V3 operational role policy (no dynamic enterprise IAM)."""

ROLE_DEFINITIONS = {
    "platformadmin": {
        "name": "Platform Administrator",
        "description": "Platform control, organization provisioning, platform health, and platform audit.",
        "permissions": ["platform.organizations.manage", "platform.users.manage", "platform.health.view", "platform.audit.view", "platform.organization.inspect"],
    },
    "admin": {
        "name": "IT Administrator",
        "description": "Day-to-day discovery, inventory, monitoring, incident, and operational administration.",
        "permissions": ["users.manage_operational", "discovery.execute", "devices.manage", "assets.manage", "incidents.manage", "topology.view", "ports.view", "vlans.view"],
    },
    "technician": {
        "name": "IT Technician",
        "description": "Normal IT operations without user, role, permission, or critical settings administration.",
        "permissions": ["discovery.execute", "devices.view", "assets.view", "monitor.view", "incidents.operate_assigned", "topology.view", "ports.view", "vlans.view"],
    },
    "viewer": {
        "name": "Viewer",
        "description": "Read-only access to operational information.",
        "permissions": ["overview.view", "discovery.view", "devices.view", "assets.view", "monitor.view", "incidents.view", "topology.view", "ports.view", "vlans.view", "reports.view"],
    },
}

SUPPORTED_ROLES = tuple(ROLE_DEFINITIONS)
OPERATIONAL_ROLES = ("admin", "technician", "viewer")


def role_definitions():
    return [{"key": key, **value} for key, value in ROLE_DEFINITIONS.items()]
