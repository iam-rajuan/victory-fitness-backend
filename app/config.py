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
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = _get_int("API_PORT", 8000)
    api_public_base_url = os.getenv("API_PUBLIC_BASE_URL", f"http://localhost:{api_port}").strip().rstrip("/")
    slow_request_threshold_ms = _get_int("SLOW_REQUEST_THRESHOLD_MS", 800)

    mongodb_uri = _get_mongodb_uri()
    mongodb_configured = bool(mongodb_uri)
    mongodb_db = os.getenv("MONGODB_DB", "victory_fitness")
    mongodb_max_pool_size = _get_int("MONGODB_MAX_POOL_SIZE", 50)
    mongodb_min_pool_size = _get_int("MONGODB_MIN_POOL_SIZE", 1)

    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "change-this-to-a-long-random-secret")
    using_default_jwt_secret = jwt_secret_key == "change-this-to-a-long-random-secret"
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
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
    wearable_scheduler_enabled = _get_bool("WEARABLE_SCHEDULER_ENABLED", True)
    wearable_scheduler_interval_minutes = _get_int("WEARABLE_SCHEDULER_INTERVAL_MINUTES", 30)
    wearable_scheduler_lookback_days = _get_int("WEARABLE_SCHEDULER_LOOKBACK_DAYS", 1)

    fitbit_client_id = os.getenv("FITBIT_CLIENT_ID", "").strip()
    fitbit_client_secret = os.getenv("FITBIT_CLIENT_SECRET", "").strip()
    fitbit_redirect_uri = os.getenv("FITBIT_REDIRECT_URI", "").strip()
    fitbit_scopes = _get_csv_list("FITBIT_SCOPES", "activity,heartrate,sleep,profile")

    garmin_client_id = os.getenv("GARMIN_CLIENT_ID", "").strip()
    garmin_client_secret = os.getenv("GARMIN_CLIENT_SECRET", "").strip()
    garmin_redirect_uri = os.getenv("GARMIN_REDIRECT_URI", "").strip()
    garmin_authorize_url = os.getenv("GARMIN_AUTHORIZE_URL", "").strip()
    garmin_token_url = os.getenv("GARMIN_TOKEN_URL", "").strip()
    garmin_api_base_url = os.getenv("GARMIN_API_BASE_URL", "").strip()
    garmin_daily_summary_path = os.getenv("GARMIN_DAILY_SUMMARY_PATH", "/wellness-api/rest/dailies").strip()
    garmin_scopes = _get_csv_list("GARMIN_SCOPES", "")
    garmin_webhook_secret = os.getenv("GARMIN_WEBHOOK_SECRET", "").strip()


settings = Settings()
