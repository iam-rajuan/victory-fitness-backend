from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.post("/admin/uploads/presign", response_model=AdminDirectUploadResponse)

async def admin_create_direct_upload(

    payload: AdminDirectUploadRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminDirectUploadResponse:

    try:

        folder_name, allowed_types = _get_direct_upload_target(payload.uploadType)

        return _create_presigned_media_upload(

            folder_name,

            str(admin_user["_id"]),

            payload.contentType,

            payload.fileName,

            allowed_types=allowed_types,

        )

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc
