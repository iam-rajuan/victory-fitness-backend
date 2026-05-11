import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_mongodb_uri() -> str:
    value = (os.getenv("MONGODB_URI") or "").strip()
    if "<" in value or ">" in value:
        return ""
    return value


class Settings:
    app_name = os.getenv("APP_NAME", "Victory Fitness API")
    environment = os.getenv("ENVIRONMENT", "development")
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", "8000"))

    mongodb_uri = _get_mongodb_uri()
    mongodb_configured = bool(mongodb_uri)
    mongodb_db = os.getenv("MONGODB_DB", "victory_fitness")

    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "change-this-to-a-long-random-secret")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10"))
    session_token_expire_days = int(os.getenv("SESSION_TOKEN_EXPIRE_DAYS", "30"))

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", smtp_username)
    smtp_from_name = os.getenv("SMTP_FROM_NAME", "Victory Fitness")
    smtp_use_tls = _get_bool("SMTP_USE_TLS", True)

    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    vimeo_access_token = os.getenv("VIMEO_ACCESS_TOKEN", "").strip()

    coach_recent_message_limit = int(os.getenv("COACH_RECENT_MESSAGE_LIMIT", "40"))
    coach_archive_batch_size = int(os.getenv("COACH_ARCHIVE_BATCH_SIZE", "20"))
    aws_region = os.getenv("AWS_REGION", "").strip()
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    aws_s3_bucket = os.getenv("AWS_S3_BUCKET", "").strip()
    aws_s3_prefix = os.getenv("AWS_S3_PREFIX", "coach-archives").strip().strip("/")

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:8081")
    frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", ".*")
    cookie_secure = _get_bool("COOKIE_SECURE", environment == "production")
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "none" if environment == "production" else "lax").strip().lower()
    admin_seed_enabled = _get_bool("ADMIN_SEED_ENABLED", True)
    admin_name = os.getenv("ADMIN_NAME", "Victory Admin").strip()
    admin_email = os.getenv("ADMIN_EMAIL", "admin@victoryfitness.com").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()


settings = Settings()
