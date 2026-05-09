import json
from datetime import datetime, timezone
from typing import Any

from .config import settings


def s3_archive_enabled() -> bool:
    return bool(
        settings.aws_s3_bucket
        and settings.aws_region
        and settings.aws_access_key_id
        and settings.aws_secret_access_key
    )


def build_archive_record(
    user_id: str,
    thread_id: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    if not messages:
        raise ValueError("Cannot archive an empty message batch")

    created_at = datetime.now(timezone.utc)
    record = {
        "user_id": user_id,
        "thread_id": thread_id,
        "message_count": len(messages),
        "from_created_at": messages[0]["created_at"],
        "to_created_at": messages[-1]["created_at"],
        "created_at": created_at,
    }

    if s3_archive_enabled():
        s3_key = _upload_archive_to_s3(user_id, thread_id, created_at, messages)
        record.update(
            {
                "storage_backend": "s3",
                "s3_bucket": settings.aws_s3_bucket,
                "s3_key": s3_key,
            }
        )
    else:
        record.update(
            {
                "storage_backend": "mongodb",
                "payload": messages,
            }
        )

    return record


def hydrate_archive_messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    storage_backend = record.get("storage_backend", "mongodb")
    if storage_backend == "mongodb":
        payload = record.get("payload")
        return payload if isinstance(payload, list) else []

    if storage_backend == "s3":
        return _load_archive_from_s3(record)

    return []


def store_thread_snapshot(
    user_id: str,
    thread_id: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    if not s3_archive_enabled():
        raise RuntimeError("AWS S3 is not configured for thread snapshots")

    created_at = datetime.now(timezone.utc)
    s3_key = _upload_snapshot_to_s3(user_id, thread_id, created_at, messages)
    return {
        "storage_backend": "s3_snapshot",
        "s3_bucket": settings.aws_s3_bucket,
        "s3_key": s3_key,
        "message_count": len(messages),
        "created_at": created_at,
    }


def load_thread_snapshot(bucket: str, key: str) -> list[dict[str, Any]]:
    return _load_messages_from_s3(bucket, key)


def _upload_archive_to_s3(
    user_id: str,
    thread_id: str,
    created_at: datetime,
    messages: list[dict[str, Any]],
) -> str:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 coach archives") from exc

    s3_key = (
        f"{settings.aws_s3_prefix}/{user_id}/{thread_id}/"
        f"{created_at.strftime('%Y-%m-%dT%H-%M-%SZ')}.json"
    )
    payload = json.dumps(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "created_at": created_at.isoformat(),
            "messages": [_serialize_message(message) for message in messages],
        }
    ).encode("utf-8")

    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )
    client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=s3_key,
        Body=payload,
        ContentType="application/json",
    )
    return s3_key


def _upload_snapshot_to_s3(
    user_id: str,
    thread_id: str,
    created_at: datetime,
    messages: list[dict[str, Any]],
) -> str:
    client = _build_s3_client()
    s3_key = (
        f"{settings.aws_s3_prefix}/{user_id}/{thread_id}/snapshots/"
        f"{created_at.strftime('%Y-%m-%dT%H-%M-%SZ')}.json"
    )
    payload = json.dumps(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "created_at": created_at.isoformat(),
            "messages": [_serialize_message(message) for message in messages],
        }
    ).encode("utf-8")
    client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=s3_key,
        Body=payload,
        ContentType="application/json",
    )
    return s3_key


def _load_archive_from_s3(record: dict[str, Any]) -> list[dict[str, Any]]:
    s3_bucket = str(record.get("s3_bucket") or settings.aws_s3_bucket)
    s3_key = str(record.get("s3_key") or "")
    if not s3_bucket or not s3_key:
        return []

    return _load_messages_from_s3(s3_bucket, s3_key)


def _load_messages_from_s3(s3_bucket: str, s3_key: str) -> list[dict[str, Any]]:
    client = _build_s3_client()
    response = client.get_object(Bucket=s3_bucket, Key=s3_key)
    body = response["Body"].read().decode("utf-8")
    payload = json.loads(body)
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []

    hydrated: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        hydrated_message = dict(message)
        created_at = hydrated_message.get("created_at")
        if isinstance(created_at, str):
            try:
                hydrated_message["created_at"] = datetime.fromisoformat(created_at)
            except ValueError:
                hydrated_message["created_at"] = created_at
        hydrated.append(hydrated_message)

    return hydrated


def _build_s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 coach archives") from exc

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(message)
    created_at = serialized.get("created_at")
    if isinstance(created_at, datetime):
        serialized["created_at"] = created_at.astimezone(timezone.utc).isoformat()
    return serialized
