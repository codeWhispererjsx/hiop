from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class GeneralSettings(BaseModel):
    application_name: str = Field(min_length=2, max_length=80)
    short_name: str = Field(min_length=2, max_length=12)
    timezone: str = Field(min_length=3, max_length=64)
    date_format: Literal["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]
    time_format: Literal["12-hour", "24-hour"]
    default_page_size: Literal[10, 25, 50, 100]
    default_landing_page: Literal["/dashboard", "/devices", "/network", "/alerts", "/tickets", "/reports"]
    support_email: EmailStr | None = None


class OrganizationSettings(BaseModel):
    organization_name: str = Field(min_length=2, max_length=100)
    property_name: str = Field(min_length=2, max_length=100)
    it_department_name: str = Field(min_length=2, max_length=100)
    address: str = Field(default="", max_length=200)
    city: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=80)
    support_email: EmailStr | None = None
    support_phone: str = Field(default="", max_length=40)


class NetworkSettings(BaseModel):
    approved_network: str = Field(min_length=3, max_length=64)
    automatic_scanning: bool
    scan_interval_minutes: int = Field(ge=5, le=1440)
    ping_timeout_seconds: int = Field(ge=1, le=30)
    max_concurrent_workers: int = Field(ge=1, le=32)
    exclude_retired_devices: bool = True
    automatic_alerts: bool = True
    automatic_offline_tickets: bool = True
    offline_threshold: int = Field(ge=1, le=20)

    @field_validator("approved_network")
    @classmethod
    def validate_private_network(cls, value: str) -> str:
        from ipaddress import ip_network
        try:
            network = ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError("Enter a valid CIDR network") from exc
        if not network.is_private:
            raise ValueError("Only a private approved network may be configured")
        return str(network)


class NotificationSettings(BaseModel):
    email_notifications: bool
    device_offline: bool
    device_restored: bool
    ticket_assignment: bool
    critical_alerts: bool
    sender_display_name: str = Field(min_length=2, max_length=80)
    recipient_email: EmailStr | None = None


class SettingsBundle(BaseModel):
    general: GeneralSettings
    organization: OrganizationSettings
    network: NetworkSettings
    notifications: NotificationSettings
    email: dict
    security: dict
    application: dict


class PublicSettings(BaseModel):
    application_name: str
    short_name: str
    property_name: str
    organization_name: str
    support_email: str | None


class SystemHealth(BaseModel):
    status: Literal["Healthy", "Degraded", "Unavailable"]
    api: str
    database: str
    scheduler: str
    websocket: str
    email: str
    last_scan: str | None
    application_version: str
    environment: str
    server_time: str
