import re
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from ..config import settings


def _configured_s3_region() -> str:
    return str(settings.aws_s3_region or settings.aws_region or "").strip()


@lru_cache(maxsize=4)
def get_s3_bucket_region() -> str:
    configured = _configured_s3_region()
    if not settings.aws_s3_bucket:
        return configured
    try:
        import boto3

        client = boto3.client(
            "s3",
            region_name=configured or settings.aws_region or None,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        response = client.get_bucket_location(Bucket=settings.aws_s3_bucket)
        region = str(response.get("LocationConstraint") or "us-east-1").strip()
        return region or configured
    except Exception:
        return configured


def build_s3_file_url(object_key: str) -> str:
    region = get_s3_bucket_region()
    return f"https://{settings.aws_s3_bucket}.s3.{region}.amazonaws.com/{str(object_key).lstrip('/')}"


def canonicalize_s3_url(url: str | None) -> str:
    value = str(url or "").strip()
    if not value or not settings.aws_s3_bucket:
        return value
    parsed = urlparse(value)
    host = parsed.netloc.lower().strip()
    expected_prefix = f"{settings.aws_s3_bucket}.s3."
    if not host.startswith(expected_prefix) or not host.endswith(".amazonaws.com"):
        return value
    canonical_host = f"{settings.aws_s3_bucket}.s3.{get_s3_bucket_region()}.amazonaws.com"
    if host == canonical_host.lower():
        return value
    return urlunparse(parsed._replace(netloc=canonical_host))


def canonicalize_s3_urls_in_html(html_content: str | None) -> str:
    value = str(html_content or "")
    if not value or not settings.aws_s3_bucket:
        return value
    pattern = re.compile(
        rf"https://{re.escape(settings.aws_s3_bucket)}\.s3\.[a-z0-9-]+\.amazonaws\.com/[^\s\"'<>]+",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: canonicalize_s3_url(match.group(0)), value)
