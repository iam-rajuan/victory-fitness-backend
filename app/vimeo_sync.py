from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import settings
logger = logging.getLogger("victory-fitness.vimeo")

VIMEO_API_BASE_URL = "https://api.vimeo.com"
VIMEO_CONTAINER_FIELDS = "uri,name,metadata.connections.videos.total"
VIMEO_VIDEO_FIELDS = ",".join(
    [
        "uri",
        "name",
        "description",
        "link",
        "embed.html",
        "status",
        "privacy.view",
        "pictures.sizes",
        "created_time",
        "modified_time",
        "release_time",
    ]
)


class VimeoSyncError(RuntimeError):
    pass


@dataclass
class VimeoSyncSummary:
    synced_count: int = 0
    modules_synced: int = 0
    videos_discovered: int = 0
    synced_videos: list[dict[str, Any]] | None = None


def get_vimeo_status() -> str:
    return "CONFIGURED" if settings.vimeo_access_token else "MISSING"


def _build_vimeo_api_url(path: str, query: dict[str, Any] | None = None) -> str:
    normalized_path = str(path or "").strip()
    if normalized_path.startswith("http://") or normalized_path.startswith("https://"):
        return normalized_path
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    url = f"{VIMEO_API_BASE_URL}{normalized_path}"
    if query:
        query_string = urllib.parse.urlencode(
            {key: value for key, value in query.items() if value not in (None, "", [])}
        )
        if query_string:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query_string}"
    return url


async def _fetch_vimeo_json(url: str) -> dict[str, Any]:
    if not settings.vimeo_access_token:
        raise VimeoSyncError("Vimeo access token is not configured")

    request = urllib.request.Request(
        _build_vimeo_api_url(url),
        headers={
            "Authorization": f"bearer {settings.vimeo_access_token}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4",
            "User-Agent": "VictoryFitnessBackend/1.0",
        },
        method="GET",
    )

    def _do_request() -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.warning("vimeo_sync_http_error status=%s detail=%s", exc.code, detail[:500])
            raise VimeoSyncError(f"Vimeo API request failed with status {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VimeoSyncError("Vimeo API is unavailable") from exc

    return await asyncio.to_thread(_do_request)


async def _fetch_vimeo_collection(path: str, *, fields: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_url = _build_vimeo_api_url(path, {"per_page": 100, "fields": fields})

    while next_url:
        payload = await _fetch_vimeo_json(next_url)
        data = payload.get("data")
        if isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
        paging = payload.get("paging")
        next_path = paging.get("next") if isinstance(paging, dict) else None
        next_url = _build_vimeo_api_url(next_path) if next_path else ""

    return items


def _extract_vimeo_video_id(video: dict[str, Any]) -> str:
    for candidate in (
        str(video.get("uri") or "").strip(),
        str(video.get("link") or "").strip(),
        str(((video.get("embed") or {}) if isinstance(video.get("embed"), dict) else {}).get("html") or "").strip(),
    ):
        match = re.search(r"/videos?/(\d+)", candidate)
        if match:
            return match.group(1)
        match = re.search(r"player\.vimeo\.com/video/(\d+)", candidate)
        if match:
            return match.group(1)
        match = re.search(r"vimeo\.com/(\d+)", candidate)
        if match:
            return match.group(1)
    return ""


def _build_vimeo_embed_url(video_id: str) -> str:
    return (
        f"https://player.vimeo.com/video/{video_id}"
        "?autoplay=0&title=0&byline=0&portrait=0&playsinline=1&dnt=1"
    )


def _pick_vimeo_thumbnail(video: dict[str, Any]) -> str:
    pictures = video.get("pictures")
    sizes = pictures.get("sizes") if isinstance(pictures, dict) else None
    if isinstance(sizes, list):
        for item in reversed(sizes):
            if not isinstance(item, dict):
                continue
            link = str(item.get("link") or item.get("link_with_play_button") or "").strip()
            if link:
                return link[:500]
    return ""


def _normalize_vimeo_module_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(name or "").strip())
    if not cleaned:
        cleaned = fallback
    return cleaned[:80]


def _resolve_workout_visibility(video: dict[str, Any]) -> str:
    status = str(video.get("status") or "").strip().lower()
    privacy = video.get("privacy")
    privacy_view = str(privacy.get("view") or "").strip().lower() if isinstance(privacy, dict) else ""
    if status and status not in {"available"}:
        return "Draft"
    if privacy_view in {"disable", "nobody", "password"}:
        return "Draft"
    return "Published"


def _resolve_synced_visibility(existing_workout: dict[str, Any] | None, video: dict[str, Any]) -> str:
    if existing_workout:
        current_visibility = str(existing_workout.get("visibility") or "").strip()
        if current_visibility in {"Published", "Draft"}:
            return current_visibility
    return "Draft"


def _build_workout_document(
    *,
    video: dict[str, Any],
    module_name: str,
    source_type: str,
    source_uri: str,
    existing_workout: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any] | None:
    video_id = _extract_vimeo_video_id(video)
    if not video_id:
        return None

    title = str(video.get("name") or "").strip() or f"{module_name} Workout"
    return {
        "title": title[:160],
        "vimeo_id": video_id,
        "video_url": _build_vimeo_embed_url(video_id),
        "video_source": "VIMEO",
        "tag": _normalize_vimeo_module_name(module_name, "Vimeo"),
        "visibility": _resolve_synced_visibility(existing_workout, video),
        "thumbnail": _pick_vimeo_thumbnail(video),
        "description": str(video.get("description") or "").strip(),
        "vimeo_provider_visibility": _resolve_workout_visibility(video),
        "vimeo_source_type": source_type,
        "vimeo_source_uri": str(source_uri or "").strip(),
        "vimeo_video_uri": str(video.get("uri") or "").strip(),
        "vimeo_synced_at": now,
        "updated_at": now,
    }


async def sync_vimeo_workouts() -> VimeoSyncSummary:
    if not settings.vimeo_access_token:
        raise VimeoSyncError("Vimeo access token is not configured")
    from .database import workouts_collection

    summary = VimeoSyncSummary(synced_videos=[])
    now = datetime.now(timezone.utc)
    workout_documents_by_video_id: dict[str, dict[str, Any]] = {}

    containers: list[tuple[str, str, str]] = []
    for source_type, path in (("PROJECT", "/me/projects"), ("SHOWCASE", "/me/albums")):
        for container in await _fetch_vimeo_collection(path, fields=VIMEO_CONTAINER_FIELDS):
            container_uri = str(container.get("uri") or "").strip()
            if not container_uri:
                continue
            module_name = _normalize_vimeo_module_name(str(container.get("name") or "").strip(), source_type.title())
            containers.append((source_type, container_uri, module_name))

    summary.modules_synced = len(containers)

    for source_type, container_uri, module_name in containers:
        videos = await _fetch_vimeo_collection(f"{container_uri}/videos", fields=VIMEO_VIDEO_FIELDS)
        for video in videos:
            document = _build_workout_document(
                video=video,
                module_name=module_name,
                source_type=source_type,
                source_uri=container_uri,
                existing_workout=None,
                now=now,
            )
            if not document:
                continue
            workout_documents_by_video_id.setdefault(str(document["vimeo_id"]), document)

    standalone_videos = await _fetch_vimeo_collection("/me/videos", fields=VIMEO_VIDEO_FIELDS)
    for video in standalone_videos:
        document = _build_workout_document(
            video=video,
            module_name="Vimeo",
            source_type="VIDEO",
            source_uri="/me/videos",
            existing_workout=None,
            now=now,
        )
        if not document:
            continue
        workout_documents_by_video_id.setdefault(str(document["vimeo_id"]), document)

    summary.videos_discovered = len(workout_documents_by_video_id)

    existing_workouts = await workouts_collection.find(
        {"vimeo_id": {"$in": list(workout_documents_by_video_id.keys())}}
    ).to_list(length=len(workout_documents_by_video_id))
    existing_workouts_by_video_id = {
        str(record.get("vimeo_id") or "").strip(): record
        for record in existing_workouts
        if str(record.get("vimeo_id") or "").strip()
    }

    for video_id, document in list(workout_documents_by_video_id.items()):
        existing_workout = existing_workouts_by_video_id.get(video_id)
        document["visibility"] = _resolve_synced_visibility(existing_workout, document)
        await workouts_collection.update_one(
            {"vimeo_id": video_id},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        summary.synced_count += 1
        summary.synced_videos.append(
            {
                "title": str(document.get("title") or "").strip(),
                "vimeoId": video_id,
                "tag": str(document.get("tag") or "").strip(),
                "visibility": str(document.get("visibility") or "Draft").strip() or "Draft",
                "providerVisibility": str(document.get("vimeo_provider_visibility") or "Draft").strip() or "Draft",
                "alreadyInLibrary": existing_workout is not None,
            }
        )

    logger.info(
        "vimeo_sync_complete synced_count=%s modules_synced=%s videos_discovered=%s",
        summary.synced_count,
        summary.modules_synced,
        summary.videos_discovered,
    )
    return summary
