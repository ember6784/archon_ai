"""
OpenClaw Enterprise Configuration

Pydantic-based settings with environment variable support.
"""

from typing import Optional, List
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    # ==========================================================================
    # APPLICATION
    # ==========================================================================
    app_name: str = "OpenClaw Enterprise"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ==========================================================================
    # API
    # ==========================================================================
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # CORS
    cors_origins: List[str] = Field(default_factory=lambda: [
        "http://localhost:3000",
        "http://localhost:8000"
    ])
    cors_allow_credentials: bool = True

    # ==========================================================================
    # DATABASE
    # ==========================================================================
    database_url: str = "postgresql://postgres:postgres@localhost:5432/openclaw_enterprise"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # ==========================================================================
    # REDIS
    # ==========================================================================
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50

    # ==========================================================================
    # OPENCLAW GATEWAY
    # ==========================================================================
    openclaw_gateway_url: str = "ws://localhost:18789"
    openclaw_gateway_timeout: int = 30

    # ==========================================================================
    # LLM PROVIDERS
    # ==========================================================================
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    glm_api_key: Optional[str] = None

    # ==========================================================================
    # CIRCUIT BREAKER
    # ==========================================================================
    circuit_breaker_enabled: bool = True
    circuit_breaker_base_dir: str = "./data/circuit_breaker"

    # ==========================================================================
    # SIEGE MODE
    # ==========================================================================
    siege_mode_enabled: bool = True
    siege_mode_activation_hours: int = 5
    siege_mode_max_tasks: int = 50
    siege_mode_max_hours: int = 24

    # ==========================================================================
    # SAFETY
    # ==========================================================================
    safety_core_enabled: bool = True
    agency_templates_dir: str = "./mat/agency_templates"

    # ==========================================================================
    # AUDIT & COMPLIANCE
    # ==========================================================================
    audit_enabled: bool = True
    audit_retention_days: int = 2555  # 7 years
    audit_storage: str = "local"  # local, s3, gcs
    audit_path: str = "./data/audit"
    compliance_standards: List[str] = Field(default_factory=lambda: ["SOC2", "GDPR"])

    # ==========================================================================
    # MULTI-TENANCY
    # ==========================================================================
    multi_tenant_enabled: bool = True
    max_tenants: int = 1000
    default_tier: str = "professional"

    # ==========================================================================
    # SSO
    # ==========================================================================
    sso_enabled: bool = False
    sso_provider: str = "okta"  # okta, azure, google
    sso_client_id: Optional[str] = None
    sso_client_secret: Optional[str] = None
    sso_redirect_uri: str = "http://localhost:8000/auth/callback"
    sso_discovery_url: Optional[str] = None

    # ==========================================================================
    # STORAGE (S3/GCS)
    # ==========================================================================
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: Optional[str] = None

    gcs_credentials_path: Optional[str] = None
    gcs_bucket_name: Optional[str] = None

    # ==========================================================================
    # MONITORING
    # ==========================================================================
    metrics_enabled: bool = True
    metrics_port: int = 9090
    tracing_enabled: bool = False
    tracing_endpoint: str = "http://jaeger:4317"

    # ==========================================================================
    # ALERTS
    # ==========================================================================
    # SMTP
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_from: str = "noreply@openclaw-enterprise.com"
    alert_to: str = "admin@yourcompany.com"

    # Webhook
    webhook_url: Optional[str] = None

    # Telegram
    telegram_alert_chat_id: Optional[str] = None

    # ==========================================================================
    # CHANNELS
    # ==========================================================================
    telegram_bot_token: Optional[str] = None
    discord_bot_token: Optional[str] = None
    slack_bot_token: Optional[str] = None
    slack_app_token: Optional[str] = None

    # ==========================================================================
    # PROPERTIES
    # ==========================================================================
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def circuit_breaker_dir(self) -> Path:
        return self.base_dir / self.circuit_breaker_base_dir

    @property
    def audit_dir(self) -> Path:
        return self.base_dir / self.audit_path


# Global settings instance
settings = Settings()
