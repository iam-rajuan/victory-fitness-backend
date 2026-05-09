import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name = os.getenv("APP_NAME", "Victory Fitness API")
    environment = os.getenv("ENVIRONMENT", "development")
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", "8000"))

    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
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

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:8081")
    frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", ".*")
    cookie_secure = _get_bool("COOKIE_SECURE", False)


settings = Settings()
