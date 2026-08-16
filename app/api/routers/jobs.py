from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

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
    limit: int = Query(default=2, ge=1, le=10),
) -> dict[str, Any]:
    """Process durable MongoDB-backed nutrition jobs from a scheduler/cron call."""
    expected = str(getattr(settings, "cron_secret", "") or "").strip()
    supplied = str(authorization or "").replace("Bearer ", "", 1).strip()
    if not expected or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")

    processed = 0
    failed = 0
    for _ in range(limit):
        standard = await nutrition_plan_jobs_collection.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc)}},
            sort=[("created_at", 1)],
        )
        if standard:
            try:
                await _process_nutrition_plan_job(str(standard["_id"]), str(standard["user_id"]), standard.get("payload") or {}, str(standard.get("profile_hash") or ""))
                processed += 1
            except Exception:
                failed += 1
            continue

        progressive = await nutrition_progressive_plan_jobs_collection.find_one_and_update(
            {"status": "queued"},
            {"$set": {"status": "generating_monday", "updated_at": datetime.now(timezone.utc)}},
            sort=[("created_at", 1)],
        )
        if not progressive:
            break
        try:
            await _process_progressive_nutrition_plan_job(str(progressive["_id"]), str(progressive["user_id"]), progressive.get("payload") or {}, str(progressive.get("profile_hash") or ""))
            processed += 1
        except Exception:
            failed += 1
    return {"processed": processed, "failed": failed}
