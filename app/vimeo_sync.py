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
        "duration",
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
    already_imported_count: int = 0
    remaining_to_import: int = 0
    synced_videos: list[dict[str, Any]] | None = None


@dataclass
class VimeoWorkoutImportOptions:
    folder_name: str = ""
    tag: str = "Strength"
    equipment: str = "Dumbbells"
    level: str = "Intermediate"
    use_vimeo_duration: bool = True
    visibility: str = "Draft"
    import_limit: int | None = 12


@dataclass
class VimeoWorkoutPreview:
    modules_synced: int = 0
    videos_available: int = 0
    already_imported_count: int = 0
    remaining_to_import: int = 0


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


def _normalize_import_label(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    return (cleaned or fallback)[:80]


def _folder_matches(container_name: str, requested_folder: str) -> bool:
    requested = re.sub(r"\s+", " ", str(requested_folder or "").strip()).lower()
    if not requested:
        return True

    candidate = re.sub(r"\s+", " ", str(container_name or "").strip()).lower()
    if not candidate:
        return False

    requested_parts = [part.strip() for part in requested.split("/") if part.strip()]
    requested_names = [requested, *(requested_parts[-1:] or [])]
    return any(name == candidate or name in candidate or candidate in name for name in requested_names)


def _resolve_duration_minutes(video: dict[str, Any], use_vimeo_duration: bool) -> int:
    if not use_vimeo_duration:
        return 0
    try:
        seconds = int(video.get("duration") or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return 0
    return max(1, round(seconds / 60))


def _resolve_duration_seconds(video: dict[str, Any], use_vimeo_duration: bool) -> int:
    if not use_vimeo_duration:
        return 0
    try:
        seconds = int(video.get("duration") or 0)
    except (TypeError, ValueError):
        seconds = 0
    return max(0, min(seconds, 86400))


def _resolve_workout_visibility(video: dict[str, Any]) -> str:
    status = str(video.get("status") or "").strip().lower()
    privacy = video.get("privacy")
    privacy_view = str(privacy.get("view") or "").strip().lower() if isinstance(privacy, dict) else ""
    if status and status not in {"available"}:
        return "Draft"
    if privacy_view in {"disable", "nobody", "password"}:
        return "Draft"
    return "Published"


def _resolve_import_visibility(options: VimeoWorkoutImportOptions, video: dict[str, Any]) -> str:
    requested_visibility = "Published" if options.visibility == "Published" else "Draft"
    provider_visibility = _resolve_workout_visibility(video)
    if requested_visibility == "Published" and provider_visibility == "Published":
        return "Published"
    return "Draft"


def _build_workout_document(
    *,
    video: dict[str, Any],
    module_name: str,
    source_type: str,
    source_uri: str,
    existing_workout: dict[str, Any] | None,
    options: VimeoWorkoutImportOptions,
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
        "tag": _normalize_import_label(options.tag, _normalize_vimeo_module_name(module_name, "Vimeo")),
        "equipment": _normalize_import_label(options.equipment, ""),
        "level": _normalize_import_label(options.level, ""),
        "duration_minutes": _resolve_duration_minutes(video, options.use_vimeo_duration),
        "duration_seconds": _resolve_duration_seconds(video, options.use_vimeo_duration),
        "visibility": _resolve_import_visibility(options, video),
        "thumbnail": _pick_vimeo_thumbnail(video),
        "description": str(video.get("description") or "").strip(),
        "vimeo_provider_visibility": _resolve_workout_visibility(video),
        "vimeo_source_type": source_type,
        "vimeo_source_uri": str(source_uri or "").strip(),
        "vimeo_video_uri": str(video.get("uri") or "").strip(),
        "vimeo_synced_at": now,
        "updated_at": now,
    }


async def _discover_vimeo_workouts(
    options: VimeoWorkoutImportOptions,
    now: datetime,
) -> tuple[dict[str, dict[str, Any]], int]:
    workout_documents_by_video_id: dict[str, dict[str, Any]] = {}
    containers: list[tuple[str, str, str]] = []
    for source_type, path in (("PROJECT", "/me/projects"), ("SHOWCASE", "/me/albums")):
        for container in await _fetch_vimeo_collection(path, fields=VIMEO_CONTAINER_FIELDS):
            container_uri = str(container.get("uri") or "").strip()
            if not container_uri:
                continue
            module_name = _normalize_vimeo_module_name(str(container.get("name") or "").strip(), source_type.title())
            if not _folder_matches(module_name, options.folder_name):
                continue
            containers.append((source_type, container_uri, module_name))

    for source_type, container_uri, module_name in containers:
        videos = await _fetch_vimeo_collection(f"{container_uri}/videos", fields=VIMEO_VIDEO_FIELDS)
        for video in videos:
            document = _build_workout_document(
                video=video,
                module_name=module_name,
                source_type=source_type,
                source_uri=container_uri,
                existing_workout=None,
                options=options,
                now=now,
            )
            if not document:
                continue
            workout_documents_by_video_id.setdefault(str(document["vimeo_id"]), document)

    if not options.folder_name:
        standalone_videos = await _fetch_vimeo_collection("/me/videos", fields=VIMEO_VIDEO_FIELDS)
        for video in standalone_videos:
            document = _build_workout_document(
                video=video,
                module_name="Vimeo",
                source_type="VIDEO",
                source_uri="/me/videos",
                existing_workout=None,
                options=options,
                now=now,
            )
            if not document:
                continue
            workout_documents_by_video_id.setdefault(str(document["vimeo_id"]), document)

    return workout_documents_by_video_id, len(containers)


async def preview_vimeo_workout_import(options: VimeoWorkoutImportOptions | None = None) -> VimeoWorkoutPreview:
    if not settings.vimeo_access_token:
        raise VimeoSyncError("Vimeo access token is not configured")
    from .database import workouts_collection

    options = options or VimeoWorkoutImportOptions()
    now = datetime.now(timezone.utc)
    workout_documents_by_video_id, modules_synced = await _discover_vimeo_workouts(options, now)
    video_ids = list(workout_documents_by_video_id.keys())
    already_imported_count = 0
    if video_ids:
        already_imported_count = await workouts_collection.count_documents({"vimeo_id": {"$in": video_ids}})
    return VimeoWorkoutPreview(
        modules_synced=modules_synced,
        videos_available=len(video_ids),
        already_imported_count=already_imported_count,
        remaining_to_import=max(len(video_ids) - already_imported_count, 0),
    )


async def sync_vimeo_workouts(options: VimeoWorkoutImportOptions | None = None) -> VimeoSyncSummary:
    if not settings.vimeo_access_token:
        raise VimeoSyncError("Vimeo access token is not configured")
    from .database import workouts_collection

    options = options or VimeoWorkoutImportOptions()
    summary = VimeoSyncSummary(synced_videos=[])
    now = datetime.now(timezone.utc)
    workout_documents_by_video_id, modules_synced = await _discover_vimeo_workouts(options, now)
    summary.modules_synced = modules_synced
    summary.videos_discovered = len(workout_documents_by_video_id)

    existing_workouts = await workouts_collection.find(
        {"vimeo_id": {"$in": list(workout_documents_by_video_id.keys())}}
    ).to_list(length=len(workout_documents_by_video_id))
    existing_workouts_by_video_id = {
        str(record.get("vimeo_id") or "").strip(): record
        for record in existing_workouts
        if str(record.get("vimeo_id") or "").strip()
    }
    summary.already_imported_count = len(existing_workouts_by_video_id)
    summary.remaining_to_import = max(summary.videos_discovered - summary.already_imported_count, 0)

    for video_id, document in list(workout_documents_by_video_id.items()):
        existing_workout = existing_workouts_by_video_id.get(video_id)
        if existing_workout:
            metadata_patch: dict[str, Any] = {
                "vimeo_provider_visibility": document.get("vimeo_provider_visibility"),
                "vimeo_source_type": document.get("vimeo_source_type"),
                "vimeo_source_uri": document.get("vimeo_source_uri"),
                "vimeo_video_uri": document.get("vimeo_video_uri"),
                "vimeo_synced_at": now,
                "updated_at": now,
            }
            if int(existing_workout.get("duration_seconds") or 0) <= 0 and int(document.get("duration_seconds") or 0) > 0:
                metadata_patch["duration_seconds"] = int(document.get("duration_seconds") or 0)
            if int(existing_workout.get("duration_minutes") or 0) <= 0 and int(document.get("duration_minutes") or 0) > 0:
                metadata_patch["duration_minutes"] = int(document.get("duration_minutes") or 0)
            if not str(existing_workout.get("thumbnail") or "").strip() and str(document.get("thumbnail") or "").strip():
                metadata_patch["thumbnail"] = str(document.get("thumbnail") or "").strip()
            await workouts_collection.update_one(
                {"_id": existing_workout["_id"]},
                {"$set": {key: value for key, value in metadata_patch.items() if value is not None}},
            )
            continue
        if options.import_limit and summary.synced_count >= options.import_limit:
            break
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
                "equipment": str(document.get("equipment") or "").strip(),
                "level": str(document.get("level") or "").strip(),
                "durationMinutes": int(document.get("duration_minutes") or 0),
                "durationSeconds": int(document.get("duration_seconds") or 0),
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
