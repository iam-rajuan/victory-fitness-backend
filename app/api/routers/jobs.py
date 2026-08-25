from fastapi import APIRouter

from ...core.legacy import *
from ...observability import record_observability_event
from ...retention_service import process_retention_jobs

router = APIRouter()


async def _claim_next_ai_job() -> tuple[str, dict[str, Any]] | None:
    standard = await nutrition_plan_jobs_collection.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
        sort=[("created_at", 1)],
    )
    if standard:
        return "standard", standard
    progressive = await nutrition_progressive_plan_jobs_collection.find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "generating_monday", "updated_at": datetime.now(timezone.utc)}},
        sort=[("created_at", 1)],
    )
    if progressive:
        return "progressive", progressive
    return None


async def _process_claimed_ai_job(job_type: str, record: dict[str, Any]) -> bool:
    timeout_seconds = max(int(getattr(settings, "ai_generation_timeout_seconds", 30) or 30), 1)
    if job_type == "standard":
        await asyncio.wait_for(
            _process_nutrition_plan_job(
                str(record["_id"]),
                str(record["user_id"]),
                record.get("payload") or {},
                str(record.get("profile_hash") or ""),
            ),
            timeout=timeout_seconds,
        )
        return True
    await asyncio.wait_for(
        _process_progressive_nutrition_plan_job(
            str(record["_id"]),
            str(record["user_id"]),
            record.get("payload") or {},
            str(record.get("profile_hash") or ""),
        ),
        timeout=timeout_seconds,
    )
    return True

@router.post("/jobs/trial-campaign")
async def run_trial_campaign(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")
    return await process_trial_campaign(
        users_collection,
        challenge_memberships_collection,
        challenges_collection,
        coach_victor_threads_collection,
        nutrition_plans_collection,
        meal_analysis_entries_collection,
        app_content_collection,
    )

@router.post("/jobs/nutrition")
async def run_nutrition_job_queue(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=10, ge=1, le=10),
) -> dict[str, Any]:
    """Process durable MongoDB-backed nutrition jobs from a scheduler/cron call."""
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")

    max_concurrency = max(int(getattr(settings, "ai_generation_job_concurrency", 10) or 10), 1)
    requested_limit = min(limit, max_concurrency)
    claimed: list[tuple[str, dict[str, Any]]] = []
    for _ in range(requested_limit):
        next_job = await _claim_next_ai_job()
        if not next_job:
            break
        claimed.append(next_job)

    results = await asyncio.gather(
        *(_process_claimed_ai_job(job_type, record) for job_type, record in claimed),
        return_exceptions=True,
    )
    processed = sum(1 for result in results if result is True)
    failed = sum(1 for result in results if isinstance(result, Exception))
    await record_observability_event(
        "ai_generation_jobs_processed",
        {
            "requested_limit": requested_limit,
            "claimed_jobs": len(claimed),
            "processed": processed,
            "failed": failed,
            "concurrency": max_concurrency,
            "timeout_seconds": int(getattr(settings, "ai_generation_timeout_seconds", 30) or 30),
        },
    )
    return {"processed": processed, "failed": failed, "claimed": len(claimed), "concurrency": max_concurrency}


@router.post("/jobs/retention")
async def run_retention_jobs(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")
    result = await process_retention_jobs()
    await record_observability_event(
        "retention_jobs_processed",
        {
            "weekly_digest_cron_utc": str(getattr(settings, "weekly_digest_cron_utc", "0 22 * * 0") or "0 22 * * 0"),
            **result,
        },
    )
    return result
