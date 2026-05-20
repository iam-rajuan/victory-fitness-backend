from __future__ import annotations

import asyncio
import logging
from typing import Any

from .adapters import get_provider_adapter


logger = logging.getLogger("victory_fitness.integrations.queue")

_queue_task: asyncio.Task | None = None
_queue_stop = asyncio.Event()
_job_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


async def enqueue_integration_job(job: dict[str, Any]) -> None:
    await _job_queue.put(dict(job))


async def _process_job(job: dict[str, Any]) -> None:
    from .service import _finish_sync_job, _record_sync_error, ingest_mobile_sync  # type: ignore[attr-defined]

    job_type = str(job.get("job_type") or "")
    provider = str(job.get("provider") or "")
    user_id = str(job.get("user_id") or "")
    job_id = str(job.get("job_id") or "") or None
    adapter = get_provider_adapter(provider)

    try:
        if job_type == "sync-provider-data":
            result = await adapter.sync(user_id)
            await _finish_sync_job(
                job_id,
                status_value="success",
                synced_records=int(result.get("inserted") or 0),
                skipped_duplicates=int(result.get("skipped") or 0),
                detail=f"{provider} sync completed.",
            )
            return
        if job_type == "refresh-provider-token":
            await adapter.refresh_token(user_id)
            await _finish_sync_job(job_id, status_value="success", detail=f"{provider} token refreshed.")
            return
        if job_type == "process-imported-health-data":
            normalized = await adapter.normalize(job.get("metrics") or [])
            result = await ingest_mobile_sync(
                user_id,
                provider,
                normalized,
                source_device=str(job.get("source_device") or ""),
                batch_id=str(job.get("batch_id") or "") or None,
                trigger=job_type,
            )
            await _finish_sync_job(
                job_id,
                status_value="success",
                synced_records=int(result.get("inserted") or 0),
                skipped_duplicates=int(result.get("skipped") or 0),
                detail="Imported health data processed.",
            )
            return
    except Exception as exc:
        await _finish_sync_job(job_id, status_value="failed", detail=str(exc))
        await _record_sync_error(user_id, provider, job_id=job_id, stage=job_type, detail=str(exc))
        logger.exception("integration_queue_job_failed provider=%s job_type=%s user_id=%s", provider, job_type, user_id)


async def _queue_loop() -> None:
    while not _queue_stop.is_set():
        try:
            job = await asyncio.wait_for(_job_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        try:
            await _process_job(job)
        finally:
            _job_queue.task_done()


async def start_integration_queue() -> None:
    global _queue_task
    if _queue_task is not None:
        return
    _queue_stop.clear()
    _queue_task = asyncio.create_task(_queue_loop())
    logger.info("integration_queue_started")


async def stop_integration_queue() -> None:
    global _queue_task
    if _queue_task is None:
        return
    _queue_stop.set()
    _queue_task.cancel()
    try:
        await _queue_task
    except asyncio.CancelledError:
        pass
    _queue_task = None
    logger.info("integration_queue_stopped")
