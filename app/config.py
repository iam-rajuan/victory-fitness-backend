import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_mongodb_uri() -> str:
    value = (os.getenv("MONGODB_URI") or "").strip()
    if "<" in value or ">" in value:
        return ""
    return value


def _get_csv_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    app_name = os.getenv("APP_NAME", "Victory Fitness API")
    environment = os.getenv("ENVIRONMENT", "development")
    node_env = os.getenv("NODE_ENV", environment)
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _get_int("API_PORT", 8000)
    api_public_base_url = os.getenv("API_PUBLIC_BASE_URL", f"http://localhost:{api_port}").strip().rstrip("/")
    app_url = os.getenv("APP_URL", api_public_base_url).strip().rstrip("/")
    api_url = os.getenv("API_URL", api_public_base_url).strip().rstrip("/")
    slow_request_threshold_ms = _get_int("SLOW_REQUEST_THRESHOLD_MS", 800)

    mongodb_uri = _get_mongodb_uri()
    mongodb_configured = bool(mongodb_uri)
    mongodb_db = os.getenv("MONGODB_DB", "victory_fitness")
    mongodb_max_pool_size = _get_int("MONGODB_MAX_POOL_SIZE", 50)
    mongodb_min_pool_size = _get_int("MONGODB_MIN_POOL_SIZE", 1)
    database_url = os.getenv("DATABASE_URL", mongodb_uri).strip()
    redis_url = os.getenv("REDIS_URL", "").strip()

    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "change-this-to-a-long-random-secret")
    using_default_jwt_secret = jwt_secret_key == "change-this-to-a-long-random-secret"
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_secret = os.getenv("JWT_SECRET", jwt_secret_key).strip()
    session_secret = os.getenv("SESSION_SECRET", jwt_secret_key).strip()
    access_token_expire_minutes = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 10)
    session_token_expire_days = _get_int("SESSION_TOKEN_EXPIRE_DAYS", 30)

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = _get_int("SMTP_PORT", 587)
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username)
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "Victory Fitness")
    smtp_use_tls = _get_bool("SMTP_USE_TLS", True)

    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_meal_analysis_model = os.getenv("OPENAI_MEAL_ANALYSIS_MODEL", "gpt-4o-mini")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    vimeo_access_token = os.getenv("VIMEO_ACCESS_TOKEN", "").strip()

    coach_recent_message_limit = _get_int("COACH_RECENT_MESSAGE_LIMIT", 40)
    coach_archive_batch_size = _get_int("COACH_ARCHIVE_BATCH_SIZE", 20)
    aws_region = os.getenv("AWS_REGION", "").strip()
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_s3_bucket = os.getenv("AWS_S3_BUCKET", "").strip()
    aws_s3_prefix = os.getenv("AWS_S3_PREFIX", "coach-archives").strip().strip("/")

    frontend_origins = _get_csv_list(
        "FRONTEND_ORIGINS",
        "http://localhost:8081,http://localhost:5173",
    )
    frontend_origin = os.getenv("FRONTEND_ORIGIN", frontend_origins[0] if frontend_origins else "http://localhost:8081")
    frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", ".*")
    cookie_secure = _get_bool("COOKIE_SECURE", environment == "production")
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "none" if environment == "production" else "lax").strip().lower()
    admin_seed_enabled = _get_bool("ADMIN_SEED_ENABLED", True)
    admin_name = os.getenv("ADMIN_NAME", "Victory Admin").strip()
    admin_email = os.getenv("ADMIN_EMAIL", "admin@victoryfitness.com").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    wearable_token_encryption_key = os.getenv("WEARABLE_TOKEN_ENCRYPTION_KEY", "").strip()
    encryption_key = os.getenv("ENCRYPTION_KEY", wearable_token_encryption_key).strip()
    health_native_upload_secret = os.getenv("HEALTH_NATIVE_UPLOAD_SECRET", "").strip()
    webhook_signing_secret = os.getenv("WEBHOOK_SIGNING_SECRET", "").strip()
    wearable_scheduler_enabled = _get_bool("WEARABLE_SCHEDULER_ENABLED", True)
    wearable_scheduler_interval_minutes = _get_int("WEARABLE_SCHEDULER_INTERVAL_MINUTES", 30)
    wearable_scheduler_lookback_days = _get_int("WEARABLE_SCHEDULER_LOOKBACK_DAYS", 1)
    sync_queue_concurrency = _get_int("SYNC_QUEUE_CONCURRENCY", 5)
    sync_retry_attempts = _get_int("SYNC_RETRY_ATTEMPTS", 3)
    sync_retry_backoff_ms = _get_int("SYNC_RETRY_BACKOFF_MS", 5000)
    rate_limit_ttl = _get_int("RATE_LIMIT_TTL", 60)
    rate_limit_max = _get_int("RATE_LIMIT_MAX", 100)
    cors_origin = os.getenv("CORS_ORIGIN", "").strip()

    fitbit_client_id = os.getenv("FITBIT_CLIENT_ID", "").strip()
    fitbit_client_secret = os.getenv("FITBIT_CLIENT_SECRET", "").strip()
    fitbit_redirect_uri = os.getenv("FITBIT_REDIRECT_URI", "").strip()
    fitbit_auth_url = os.getenv("FITBIT_AUTH_URL", "https://www.fitbit.com/oauth2/authorize").strip()
    fitbit_token_url = os.getenv("FITBIT_TOKEN_URL", "https://api.fitbit.com/oauth2/token").strip()
    fitbit_api_base_url = os.getenv("FITBIT_API_BASE_URL", "https://api.fitbit.com").strip().rstrip("/")
    fitbit_scopes = _get_csv_list("FITBIT_SCOPES", "activity,heartrate,sleep,profile")

    garmin_enabled = _get_bool("GARMIN_ENABLED", False)
    garmin_client_id = os.getenv("GARMIN_CLIENT_ID", "").strip()
    garmin_client_secret = os.getenv("GARMIN_CLIENT_SECRET", "").strip()
    garmin_consumer_key = os.getenv("GARMIN_CONSUMER_KEY", "").strip()
    garmin_consumer_secret = os.getenv("GARMIN_CONSUMER_SECRET", "").strip()
    garmin_redirect_uri = os.getenv("GARMIN_REDIRECT_URI", "").strip()
    garmin_authorize_url = os.getenv("GARMIN_AUTHORIZE_URL", "").strip()
    garmin_token_url = os.getenv("GARMIN_TOKEN_URL", "").strip()
    garmin_api_base_url = os.getenv("GARMIN_API_BASE_URL", "").strip()
    garmin_daily_summary_path = os.getenv("GARMIN_DAILY_SUMMARY_PATH", "/wellness-api/rest/dailies").strip()
    garmin_scopes = _get_csv_list("GARMIN_SCOPES", "")
    garmin_webhook_secret = os.getenv("GARMIN_WEBHOOK_SECRET", "").strip()

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    google_project_id = os.getenv("GOOGLE_PROJECT_ID", "").strip()
    google_auth_uri = os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth").strip()
    google_token_uri = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token").strip()
    google_auth_provider_cert_url = os.getenv(
        "GOOGLE_AUTH_PROVIDER_CERT_URL",
        "https://www.googleapis.com/oauth2/v1/certs",
    ).strip()
    google_fit_redirect_uri = os.getenv("GOOGLE_FIT_REDIRECT_URI", "").strip()
    google_fit_api_base_url = os.getenv("GOOGLE_FIT_API_BASE_URL", "https://www.googleapis.com/fitness/v1").strip()
    google_fit_scopes = _get_csv_list(
        "GOOGLE_FIT_SCOPES",
        "https://www.googleapis.com/auth/fitness.activity.read,https://www.googleapis.com/auth/fitness.location.read,https://www.googleapis.com/auth/fitness.heart_rate.read",
    )


settings = Settings()
