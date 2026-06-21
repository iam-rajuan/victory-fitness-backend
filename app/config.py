import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

# Keep local backend runs aligned with victory-fitness-backend/.env
# without overriding deployment environment variables.
load_dotenv(ENV_FILE, override=False)


def _get_str(name: str, default: str = "", *, strip_value: bool = True) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() if strip_value else value


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _has_placeholder(value: str) -> bool:
    return "<" in value or ">" in value


def _get_secret(name: str, default: str = "") -> str:
    value = _get_str(name, default)
    if _has_placeholder(value):
        return default if default else ""
    return value


def _get_mongodb_uri() -> str:
    return _get_secret("MONGODB_URI")


def _get_csv_list(name: str, default: str = "") -> list[str]:
    raw = _get_str(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_CORS_ORIGINS = [
    "https://victory-fitness-dashboard.vercel.app",
    "https://victory-fitness-app.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8081",
]
DEFAULT_CORS_ORIGIN_REGEX = (
    r"^https://"
    r"(victory-fitness-dashboard|victory-fitness-app|victory-fitness-backend)"
    r"(?:-[a-z0-9-]+)?"
    r"-miskatul-masabis-projects\.vercel\.app$"
)


def _get_cors_origins() -> tuple[str, bool, list[str], str | None]:
    raw_origin = _get_str("CORS_ORIGIN", _get_str("CORS_ORIGINS", "*")) or "*"
    raw_origin_regex = _get_str("CORS_ORIGIN_REGEX")
    allow_all_flag = _get_bool("CORS_ALLOW_ALL", False)

    if raw_origin_regex:
        return raw_origin, False, [], raw_origin_regex

    origins = [origin.strip() for origin in raw_origin.split(",") if origin.strip()]
    allow_all = allow_all_flag or "*" in origins
    if allow_all:
        return raw_origin, False, DEFAULT_CORS_ORIGINS, DEFAULT_CORS_ORIGIN_REGEX
    return raw_origin, False, origins, None


def _get_cookie_samesite(environment: str) -> str:
    default = "none" if environment == "production" else "lax"
    value = _get_str("COOKIE_SAMESITE", default).lower()
    return value if value in {"lax", "strict", "none"} else default


class Settings:
    def __init__(self) -> None:
        self.app_name = _get_str("APP_NAME", "Victory Fitness API")
        self.environment = _get_str("ENVIRONMENT", "development").lower()
        self.node_env = _get_str("NODE_ENV", self.environment)
        self.is_vercel = bool(os.getenv("VERCEL"))
        self.startup_jobs_enabled = _get_bool("STARTUP_JOBS_ENABLED", not self.is_vercel)
        self.slow_request_threshold_ms = _get_int("SLOW_REQUEST_THRESHOLD_MS", 800)

        self.mongodb_uri = _get_mongodb_uri()
        self.mongodb_configured = bool(self.mongodb_uri)
        self.mongodb_db = _get_str("MONGODB_DB", "victory_fitness")
        self.mongodb_max_pool_size = _get_int("MONGODB_MAX_POOL_SIZE", 50)
        self.mongodb_min_pool_size = _get_int("MONGODB_MIN_POOL_SIZE", 1)
        self.database_url = _get_str("DATABASE_URL", self.mongodb_uri)

        self.jwt_secret_key = _get_secret("JWT_SECRET_KEY", "change-this-to-a-long-random-secret")
        self.using_default_jwt_secret = self.jwt_secret_key == "change-this-to-a-long-random-secret"
        self.jwt_algorithm = _get_str("JWT_ALGORITHM", "HS256")
        self.jwt_secret = _get_secret("JWT_SECRET", self.jwt_secret_key)
        self.session_secret = _get_secret("SESSION_SECRET", self.jwt_secret_key)
        self.access_token_expire_minutes = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 10)
        self.session_token_expire_days = _get_int("SESSION_TOKEN_EXPIRE_DAYS", 30)

        self.cors_origin, self.cors_allow_all, self.cors_origins, self.cors_origin_regex = _get_cors_origins()
        self.cookie_secure = _get_bool("COOKIE_SECURE", self.environment == "production")
        self.cookie_samesite = _get_cookie_samesite(self.environment)

        self.smtp_host = _get_str("SMTP_HOST")
        self.smtp_port = _get_int("SMTP_PORT", 587)
        self.smtp_username = _get_str("SMTP_USERNAME")
        self.smtp_password = _get_secret("SMTP_PASSWORD")
        self.smtp_from_email = _get_str("SMTP_FROM_EMAIL", self.smtp_username)
        self.smtp_from_name = _get_str("SMTP_FROM_NAME", "Victory Fitness")
        self.smtp_use_tls = _get_bool("SMTP_USE_TLS", True)

        self.openai_api_key = _get_secret("OPENAI_API_KEY")
        self.openai_model = _get_str("OPENAI_MODEL", "gpt-5.5")
        self.openai_meal_analysis_model = _get_str("OPENAI_MEAL_ANALYSIS_MODEL", "gpt-4o-mini")
        self.anthropic_api_key = _get_secret("ANTHROPIC_API_KEY")
        self.anthropic_model = _get_str("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        self.vimeo_access_token = _get_secret("VIMEO_ACCESS_TOKEN")

        self.coach_recent_message_limit = _get_int("COACH_RECENT_MESSAGE_LIMIT", 40)
        self.coach_archive_batch_size = _get_int("COACH_ARCHIVE_BATCH_SIZE", 20)
        self.aws_region = _get_str("AWS_REGION")
        self.aws_access_key_id = _get_secret("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY")
        self.aws_s3_bucket = _get_str("AWS_S3_BUCKET")
        self.aws_s3_prefix = _get_str("AWS_S3_PREFIX", "coach-archives").strip("/")

        self.admin_seed_enabled = _get_bool("ADMIN_SEED_ENABLED", True)
        self.admin_name = _get_str("ADMIN_NAME", "Victory Admin")
        self.admin_email = _get_str("ADMIN_EMAIL", "admin@victoryfitness.com").lower()
        self.admin_password = _get_secret("ADMIN_PASSWORD")

        self.wearable_token_encryption_key = _get_secret("WEARABLE_TOKEN_ENCRYPTION_KEY")
        self.encryption_key = _get_secret("ENCRYPTION_KEY", self.wearable_token_encryption_key)
        self.health_native_upload_secret = _get_secret("HEALTH_NATIVE_UPLOAD_SECRET")
        self.webhook_signing_secret = _get_secret("WEBHOOK_SIGNING_SECRET")
        self.wearable_scheduler_enabled = _get_bool("WEARABLE_SCHEDULER_ENABLED", True)
        self.wearable_scheduler_interval_minutes = _get_int("WEARABLE_SCHEDULER_INTERVAL_MINUTES", 30)
        self.wearable_scheduler_lookback_days = _get_int("WEARABLE_SCHEDULER_LOOKBACK_DAYS", 1)
        self.sync_queue_concurrency = _get_int("SYNC_QUEUE_CONCURRENCY", 5)
        self.sync_retry_attempts = _get_int("SYNC_RETRY_ATTEMPTS", 3)
        self.sync_retry_backoff_ms = _get_int("SYNC_RETRY_BACKOFF_MS", 5000)
        self.rate_limit_ttl = _get_int("RATE_LIMIT_TTL", 60)
        self.rate_limit_max = _get_int("RATE_LIMIT_MAX", 100)

        self.fitbit_client_id = _get_secret("FITBIT_CLIENT_ID")
        self.fitbit_client_secret = _get_secret("FITBIT_CLIENT_SECRET")
        self.fitbit_redirect_uri = _get_str("FITBIT_REDIRECT_URI")
        self.fitbit_auth_url = _get_str("FITBIT_AUTH_URL", "https://www.fitbit.com/oauth2/authorize")
        self.fitbit_token_url = _get_str("FITBIT_TOKEN_URL", "https://api.fitbit.com/oauth2/token")
        self.fitbit_api_base_url = _get_str("FITBIT_API_BASE_URL", "https://api.fitbit.com").rstrip("/")
        self.fitbit_scopes = _get_csv_list("FITBIT_SCOPES", "activity,heartrate,sleep,profile")

        self.garmin_enabled = _get_bool("GARMIN_ENABLED", False)
        self.garmin_client_id = _get_secret("GARMIN_CLIENT_ID")
        self.garmin_client_secret = _get_secret("GARMIN_CLIENT_SECRET")
        self.garmin_consumer_key = _get_secret("GARMIN_CONSUMER_KEY")
        self.garmin_consumer_secret = _get_secret("GARMIN_CONSUMER_SECRET")
        self.garmin_redirect_uri = _get_str("GARMIN_REDIRECT_URI")
        self.garmin_authorize_url = _get_str("GARMIN_AUTHORIZE_URL")
        self.garmin_token_url = _get_str("GARMIN_TOKEN_URL")
        self.garmin_api_base_url = _get_str("GARMIN_API_BASE_URL")
        self.garmin_daily_summary_path = _get_str("GARMIN_DAILY_SUMMARY_PATH", "/wellness-api/rest/dailies")
        self.garmin_scopes = _get_csv_list("GARMIN_SCOPES")
        self.garmin_webhook_secret = _get_secret("GARMIN_WEBHOOK_SECRET")

        self.google_client_id = _get_secret("GOOGLE_CLIENT_ID")
        self.google_client_secret = _get_secret("GOOGLE_CLIENT_SECRET")
        self.google_project_id = _get_str("GOOGLE_PROJECT_ID")
        self.firebase_project_id = _get_str("FIREBASE_PROJECT_ID", self.google_project_id)
        self.firebase_auth_provider_cert_url = _get_str(
            "FIREBASE_AUTH_PROVIDER_CERT_URL",
            "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com",
        )
        self.google_auth_uri = _get_str("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth")
        self.google_token_uri = _get_str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
        self.google_auth_provider_cert_url = _get_str(
            "GOOGLE_AUTH_PROVIDER_CERT_URL",
            "https://www.googleapis.com/oauth2/v1/certs",
        )
        self.google_fit_redirect_uri = _get_str("GOOGLE_FIT_REDIRECT_URI")
        self.google_fit_api_base_url = _get_str("GOOGLE_FIT_API_BASE_URL", "https://www.googleapis.com/fitness/v1")
        self.google_fit_scopes = _get_csv_list(
            "GOOGLE_FIT_SCOPES",
            "https://www.googleapis.com/auth/fitness.activity.read,https://www.googleapis.com/auth/fitness.location.read,https://www.googleapis.com/auth/fitness.heart_rate.read",
        )


settings = Settings()
