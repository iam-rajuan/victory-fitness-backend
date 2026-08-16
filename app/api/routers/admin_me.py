from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/me", response_model=AdminProfileResponse)

async def get_admin_profile(admin_user: dict = Depends(_require_admin_user)) -> AdminProfileResponse:

    return AdminProfileResponse(**_serialize_admin_profile_record(admin_user))

@router.patch("/admin/me", response_model=AdminProfileResponse)

async def update_admin_profile(

    payload: UpdateAdminProfileRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminProfileResponse:

    update_doc: dict = {}

    if payload.fullName is not None:

        update_doc["name"] = payload.fullName.strip()

    if payload.country is not None:

        update_doc["country"] = payload.country.strip()

    if payload.contactNumber is not None:

        update_doc["contact_number"] = payload.contactNumber.strip()

    if not update_doc:

        return AdminProfileResponse(**_serialize_admin_profile_record(admin_user))

    update_doc["updated_at"] = datetime.now(timezone.utc)

    await users_collection.update_one({"_id": admin_user["_id"]}, {"$set": update_doc})

    updated_admin = await users_collection.find_one({"_id": admin_user["_id"]})

    if not updated_admin:

        raise HTTPException(status_code=404, detail="Admin user not found")

    await _sync_community_author_profile(updated_admin)

    return AdminProfileResponse(**_serialize_admin_profile_record(updated_admin))

@router.post("/admin/me/profile-image", response_model=ProfileImageUploadResponse)

async def upload_admin_profile_image(

    payload: ProfileImageUploadRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> ProfileImageUploadResponse:

    user_id = str(admin_user["_id"])

    logger.info("admin_profile_image_upload_attempt user_id=%s", user_id)

    try:

        image_url = await asyncio.to_thread(

            _upload_profile_image_to_s3,

            user_id,

            payload.image_base64,

            payload.mime_type,

            payload.file_name,

        )

    except RuntimeError as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await users_collection.update_one(

        {"_id": admin_user["_id"]},

        {

            "$set": {

                "profile_image": image_url,

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    updated_admin = await users_collection.find_one({"_id": admin_user["_id"]})

    if updated_admin:

        await _sync_community_author_profile(updated_admin)

    logger.info("admin_profile_image_upload_success user_id=%s", user_id)

    return ProfileImageUploadResponse(image_url=image_url)

@router.post("/admin/me/change-password")

async def change_admin_password(

    payload: AdminChangePasswordRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    current_hash = str(admin_user.get("password_hash") or "")

    if not current_hash or not verify_password(payload.current_password, current_hash):

        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if payload.current_password == payload.new_password:

        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    await users_collection.update_one(

        {"_id": admin_user["_id"]},

        {

            "$set": {

                "password_hash": hash_password(payload.new_password),

                "updated_at": datetime.now(timezone.utc),

            }

        },

    )

    return {"status": "success"}
