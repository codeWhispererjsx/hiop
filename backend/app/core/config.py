from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_version: str
    debug: bool
    database_url: str

    api_prefix: str = "/api/v1"
    secret_key: str
    access_token_expire_minutes: int = 60
    environment: Literal["development", "testing", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_pool_size: int = Field(default=10, ge=1, le=50)
    database_max_overflow: int = Field(default=20, ge=0, le=100)
    database_pool_recycle_seconds: int = Field(default=1800, ge=300, le=86400)
    scheduler_enabled: bool = True

    # Active Directory integration is opt-in and disabled by default.
    active_directory_enabled: bool = False
    ad_default_ldap_port: int = Field(default=389, ge=1, le=65535)
    ad_default_ldaps_port: int = Field(default=636, ge=1, le=65535)
    ad_connection_timeout_seconds: int = Field(default=10, ge=1, le=300)
    ad_search_timeout_seconds: int = Field(default=30, ge=1, le=600)
    ad_default_page_size: int = Field(default=500, ge=1, le=5000)
    ad_maximum_page_size: int = Field(default=5000, ge=1, le=10000)
    ad_maximum_objects_per_sync: int = Field(default=100000, ge=1, le=1000000)
    ad_maximum_objects_per_query: int = Field(default=500, ge=1, le=10000)
    ad_maximum_groups_with_members: int = Field(default=10, ge=0, le=100)
    ad_maximum_group_members: int = Field(default=100, ge=1, le=5000)
    ad_maximum_attributes: int = Field(default=32, ge=1, le=100)
    ad_connection_retry_count: int = Field(default=1, ge=0, le=2)
    ad_sync_concurrency: int = Field(default=1, ge=1, le=10)
    ad_sync_default_mode: Literal["full", "incremental"] = "incremental"
    ad_sync_incremental_overlap_minutes: int = Field(default=5, ge=1, le=1440)
    ad_sync_maximum_duration_minutes: int = Field(default=120, ge=1, le=1440)
    ad_sync_batch_size: int = Field(default=250, ge=10, le=5000)
    ad_sync_retry_limit: int = Field(default=1, ge=0, le=3)
    ad_sync_missing_grace_period_minutes: int = Field(default=0, ge=0, le=43200)
    ad_sync_progress_broadcast_interval_seconds: int = Field(default=2, ge=1, le=60)
    ad_sync_stale_run_timeout_minutes: int = Field(default=180, ge=5, le=1440)
    ad_minimum_sync_interval_minutes: int = Field(default=15, ge=1, le=1440)
    ad_maximum_sync_interval_minutes: int = Field(default=14400, ge=15, le=525600)
    ad_tls_verification_required: bool = True
    ad_allow_insecure_ldap: bool = False
    ad_allow_public_hosts: bool = False
    ad_approved_hosts: list[str] = []

    # SNMP foundation. Transport, polling, scheduling, and alerts remain disabled.
    snmp_enabled: bool = False
    snmp_default_port: int = Field(default=161, ge=1, le=65535)
    snmp_default_timeout_seconds: int = Field(default=5, ge=1, le=60)
    snmp_default_retries: int = Field(default=1, ge=0, le=10)
    snmp_maximum_retries: int = Field(default=3, ge=0, le=10)
    snmp_minimum_polling_interval_seconds: int = Field(default=60, ge=30, le=86400)
    snmp_maximum_polling_interval_seconds: int = Field(default=86400, ge=60, le=604800)
    snmp_maximum_oids_per_request: int = Field(default=50, ge=1, le=1000)
    snmp_maximum_walk_rows: int = Field(default=1000, ge=1, le=100000)
    snmp_maximum_interfaces: int = Field(default=1000, ge=1, le=10000)
    snmp_metric_retention_days: int = Field(default=90, ge=1, le=3650)
    snmp_poll_run_retention_days: int = Field(default=180, ge=1, le=3650)
    snmp_interface_history_retention_days: int = Field(default=365, ge=1, le=3650)
    snmp_interface_missing_grace_polls: int = Field(default=2, ge=1, le=100)
    snmp_rate_max_gap_seconds: int = Field(default=3600, ge=30, le=604800)
    snmp_maximum_metrics_per_poll: int = Field(default=10000, ge=1, le=1000000)
    snmp_metric_query_maximum_days: int = Field(default=31, ge=1, le=3650)
    snmp_candidate_strong_match_threshold: int = Field(default=80, ge=0, le=100)
    snmp_candidate_probable_match_threshold: int = Field(default=60, ge=0, le=100)
    snmp_fill_missing_only_enrichment: bool = True
    snmp_collection_batch_size: int = Field(default=500, ge=10, le=10000)
    snmp_poll_concurrency: int = Field(default=5, ge=1, le=100)
    snmp_stale_run_timeout_seconds: int = Field(default=900, ge=60, le=86400)
    snmp_maximum_jitter_seconds: int = Field(default=120, ge=0, le=3600)
    snmp_cleanup_hour_utc: int = Field(default=3, ge=0, le=23)
    snmp_alert_flap_window_minutes: int = Field(default=30, ge=5, le=1440)
    snmp_alert_notification_threshold: Literal["info", "warning", "high", "critical"] = "warning"

    # Relational topology foundation; live discovery remains out of scope.
    topology_enabled: bool = True
    topology_maximum_nodes: int = Field(default=5000, ge=1, le=100000)
    topology_maximum_links: int = Field(default=10000, ge=1, le=200000)
    topology_maximum_graph_nodes: int = Field(default=2000, ge=1, le=10000)
    topology_maximum_graph_links: int = Field(default=5000, ge=1, le=50000)
    topology_maximum_traversal_depth: int = Field(default=20, ge=1, le=100)
    topology_maximum_snapshots: int = Field(default=100, ge=1, le=10000)
    topology_snapshot_retention_days: int = Field(default=365, ge=1, le=3650)
    topology_default_confidence_threshold: int = Field(default=60, ge=0, le=100)
    snmp_allow_legacy_protocols: bool = False
    snmp_allow_v1: bool = False
    snmp_v3_required_in_production: bool = True

    # Email Settings
    email_address: str
    email_password: str
    email_recipient: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    @model_validator(mode="after")
    def validate_production_security(self):
        if not self.debug and len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters outside development")
        if not 5 <= self.access_token_expire_minutes <= 1440:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 1440")
        if self.environment == "production" and self.debug:
            raise ValueError("DEBUG must be false in production")
        if any(not origin.startswith(("http://", "https://")) for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must contain absolute HTTP or HTTPS origins")
        if self.environment == "production" and any(not origin.startswith("https://") or "localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
            raise ValueError("Production CORS_ORIGINS must contain only production HTTPS origins")
        if self.environment == "production" and any(marker in self.secret_key.lower() for marker in ("replace", "change-me", "validation-only")):
            raise ValueError("Production SECRET_KEY still contains a placeholder value")
        if self.environment == "production" and any(marker in self.database_url.lower() for marker in ("replace", "change-me")):
            raise ValueError("Production DATABASE_URL still contains a placeholder value")
        if self.ad_default_page_size > self.ad_maximum_page_size:
            raise ValueError("AD_DEFAULT_PAGE_SIZE cannot exceed AD_MAXIMUM_PAGE_SIZE")
        if self.ad_minimum_sync_interval_minutes > self.ad_maximum_sync_interval_minutes:
            raise ValueError("AD minimum sync interval cannot exceed its maximum")
        if self.environment != "development" and self.ad_allow_insecure_ldap:
            raise ValueError("Insecure LDAP may only be enabled in development")
        if self.environment == "production" and not self.ad_tls_verification_required:
            raise ValueError("Active Directory TLS verification is required in production")
        if self.snmp_default_retries > self.snmp_maximum_retries:
            raise ValueError("SNMP default retries cannot exceed the configured maximum")
        if self.snmp_minimum_polling_interval_seconds > self.snmp_maximum_polling_interval_seconds:
            raise ValueError("SNMP minimum polling interval cannot exceed its maximum")
        if self.environment == "production" and self.snmp_allow_v1:
            raise ValueError("SNMPv1 cannot be enabled in production")
        return self


settings = Settings()
