from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Hasnet PrintHub API"
    env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/hasnet_printhub"

    secret_key: str
    access_token_expire_minutes: int = 60

    upload_max_mb: int = 10
    upload_artifact_ttl_hours: int = 24
    default_currency: str = "TZS"
    payment_provider: str = "mixx"
    payment_reconcile_enabled: bool = True
    payment_reconcile_interval_seconds: int = 30
    payment_reconcile_batch_limit: int = 25
    payment_reconcile_startup_delay_seconds: int = 5
    customer_pending_escalation_minutes: int = 10

    snippe_base_url: str = ""
    snippe_api_key: str = ""
    snippe_api_secret: str = ""
    snippe_webhook_secret: str = ""
    snippe_webhook_url: str = ""

    mixx_base_url: str = ""
    mixx_payment_path: str = ""
    mixx_api_key: str = ""
    mixx_user_id: str = ""
    mixx_biller_msisdn: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    alert_renotify_minutes: int = 30
    device_offline_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("payment_provider")
    @classmethod
    def normalize_payment_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"snippe", "mixx"}:
            raise ValueError("PAYMENT_PROVIDER must be either 'snippe' or 'mixx'.")
        return normalized

    @field_validator("payment_reconcile_interval_seconds")
    @classmethod
    def validate_reconcile_interval(cls, value: int) -> int:
        if value < 5:
            raise ValueError("PAYMENT_RECONCILE_INTERVAL_SECONDS must be >= 5.")
        return value

    @field_validator("payment_reconcile_batch_limit")
    @classmethod
    def validate_reconcile_batch_limit(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("PAYMENT_RECONCILE_BATCH_LIMIT must be between 1 and 100.")
        return value

    @field_validator("payment_reconcile_startup_delay_seconds")
    @classmethod
    def validate_reconcile_startup_delay(cls, value: int) -> int:
        if value < 0:
            raise ValueError("PAYMENT_RECONCILE_STARTUP_DELAY_SECONDS must be >= 0.")
        return value

    @field_validator("customer_pending_escalation_minutes")
    @classmethod
    def validate_pending_escalation_minutes(cls, value: int) -> int:
        if value < 1 or value > 1440:
            raise ValueError("CUSTOMER_PENDING_ESCALATION_MINUTES must be between 1 and 1440.")
        return value

    @field_validator("upload_artifact_ttl_hours")
    @classmethod
    def validate_upload_artifact_ttl_hours(cls, value: int) -> int:
        if value < 1 or value > 24 * 30:
            raise ValueError("UPLOAD_ARTIFACT_TTL_HOURS must be between 1 and 720.")
        return value


settings = Settings()
