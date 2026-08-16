from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/ai/meal-analysis", response_model=MealImageAnalysisResponse)

async def analyze_meal_image(

    payload: MealImageAnalysisRequest,

    user: dict = Depends(_require_meal_analysis_access_user),

) -> MealImageAnalysisResponse:

    user_id = str(user["_id"])

    logger.info("meal_image_analyze_attempt user_id=%s file_name=%s", user_id, payload.file_name or "")

    try:
        payload_data = payload.model_dump()
        if payload.image_base64:
            result = generate_meal_image_analysis(payload_data)
        else:
            extracted_text = payload.text_content
            if not extracted_text and payload.document_base64:
                extracted_text = _extract_meal_analysis_document_text(
                    payload.document_base64,
                    payload.mime_type,
                    payload.file_name,
                )
            if not extracted_text or not extracted_text.strip():
                raise HTTPException(status_code=422, detail="The uploaded document did not contain readable meal text.")

            result = generate_meal_document_analysis({
                "text_content": extracted_text.strip(),
                "file_name": payload.file_name,
            })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except RuntimeError as exc:

        raise HTTPException(status_code=502, detail=f"Meal image analysis unavailable: {exc}") from exc

    created_at = datetime.now(timezone.utc)

    saved_result = {

        **result.data,

        "file_name": payload.file_name,

        "created_at": created_at,

    }

    insert_result = await meal_analysis_entries_collection.insert_one(

        {

            "user_id": user_id,

            "analysis": saved_result,

            "created_at": created_at,

            "updated_at": created_at,

        }

    )

    saved_result["analysis_id"] = str(insert_result.inserted_id)

    logger.info("meal_image_analyze_success user_id=%s", user_id)

    return MealImageAnalysisResponse(**saved_result)

@router.get("/ai/meal-analysis", response_model=MealImageAnalysisListResponse)

async def list_meal_analyses(

    user: dict = Depends(_require_meal_analysis_access_user),

) -> MealImageAnalysisListResponse:

    user_id = str(user["_id"])

    records = await meal_analysis_entries_collection.find(

        {"user_id": user_id},

        sort=[("created_at", -1)],

    ).to_list(length=100)

    analyses: list[MealImageAnalysisResponse] = []

    for record in records:

        analysis_data = dict(record.get("analysis") or {})

        analysis_data["analysis_id"] = str(record["_id"])

        if not analysis_data.get("created_at"):

            analysis_data["created_at"] = record.get("created_at")

        analyses.append(MealImageAnalysisResponse(**analysis_data))

    return MealImageAnalysisListResponse(analyses=analyses)
