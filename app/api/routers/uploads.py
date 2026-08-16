from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/uploads/presign", response_model=AdminDirectUploadResponse)

async def create_direct_upload(

    payload: AdminDirectUploadRequest,

    user: dict = Depends(_require_community_access_user),

) -> AdminDirectUploadResponse:

    if payload.uploadType != "COMMUNITY_VIDEO":

        raise HTTPException(status_code=400, detail="Unsupported upload type")

    try:

        folder_name, allowed_types = _get_direct_upload_target(payload.uploadType)

        return _create_presigned_media_upload(

            folder_name,

            str(user["_id"]),

            payload.contentType,

            payload.fileName,

            allowed_types=allowed_types,

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"Direct upload initialization failed: {exc}") from exc
