from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/users/summary", response_model=AdminUserSummaryResponse)

async def admin_user_summary(

    year: int | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminUserSummaryResponse:

    return await _build_admin_user_summary_response(year)

@router.get("/admin/users", response_model=AdminUserListResponse)

async def admin_list_users(

    page: int = 1,

    limit: int = 10,

    query: str | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminUserListResponse:

    return await _build_admin_user_list_response(page=page, limit=limit, query=query)

@router.get("/admin/users/{user_id}", response_model=AdminUserDetailResponse)

async def admin_get_user(

    user_id: str,

    _: dict = Depends(_require_admin_user),

) -> AdminUserDetailResponse:

    try:

        object_id = ObjectId(user_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})

    if not record:

        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserDetailResponse(**_serialize_admin_user_record(record))

@router.patch("/admin/users/{user_id}", response_model=AdminUserDetailResponse)

async def admin_update_user(

    user_id: str,

    payload: AdminUserUpdateRequest,

    admin_user: dict = Depends(_require_admin_user),

) -> AdminUserDetailResponse:

    try:

        object_id = ObjectId(user_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})

    if not record:

        raise HTTPException(status_code=404, detail="User not found")

    update_doc: dict = {}

    if payload.fullName is not None:

        update_doc["name"] = payload.fullName.strip()

    if payload.email is not None:

        new_email = payload.email.lower()

        existing_user = await users_collection.find_one({"email": new_email, "_id": {"$ne": object_id}})

        if existing_user:

            raise HTTPException(status_code=409, detail="Email already exists")

        update_doc["email"] = new_email

    if payload.contactNumber is not None:

        update_doc["contact_number"] = payload.contactNumber.strip()

    if payload.country is not None:

        update_doc["country"] = payload.country.strip()

    if payload.profileImage is not None:

        update_doc["profile_image"] = payload.profileImage.strip()

    if payload.role is not None:

        normalized_role = payload.role.strip().lower()

        if normalized_role not in {"user", "trainer", "moderator", "admin"}:

            raise HTTPException(status_code=400, detail="Invalid role")

        if record["_id"] == admin_user["_id"] and normalized_role != "admin":

            raise HTTPException(status_code=400, detail="You cannot remove your own admin access")

        update_doc["role"] = normalized_role

        update_doc["is_admin"] = normalized_role == "admin"

    if payload.status is not None:

        normalized_status = payload.status.upper()

        update_doc["status"] = normalized_status

        update_doc["is_verified"] = normalized_status == "ACTIVE"

    if payload.isVerified is not None:

        update_doc["is_verified"] = payload.isVerified

        update_doc["status"] = "ACTIVE" if payload.isVerified else "PENDING"

    if not update_doc:

        return AdminUserDetailResponse(**_serialize_admin_user_record(record))

    update_doc["updated_at"] = datetime.now(timezone.utc)

    await users_collection.update_one({"_id": object_id}, {"$set": update_doc})

    updated_record = await users_collection.find_one({"_id": object_id})

    if not updated_record:

        raise HTTPException(status_code=404, detail="User not found")

    return AdminUserDetailResponse(**_serialize_admin_user_record(updated_record))

@router.delete("/admin/users/{user_id}")

async def admin_delete_user(

    user_id: str,

    admin_user: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    try:

        object_id = ObjectId(user_id)

    except Exception as exc:

        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    record = await users_collection.find_one({"_id": object_id, "is_admin": {"$ne": True}})

    if not record:

        raise HTTPException(status_code=404, detail="User not found")

    if record["_id"] == admin_user["_id"]:

        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    delete_result = await users_collection.delete_one({"_id": object_id, "is_admin": {"$ne": True}})

    if delete_result.deleted_count == 0:

        raise HTTPException(status_code=404, detail="User not found")

    return {"status": "success", "message": "User deleted"}
