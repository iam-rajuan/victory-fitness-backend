import secrets
import string

from fastapi import APIRouter

from ...core.legacy import *
from ...utils.country import derive_country_code

router = APIRouter()


def _generate_temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

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


@router.post("/admin/users", response_model=AdminUserDetailResponse, status_code=201)
async def admin_create_user(
    payload: AdminUserCreateRequest,
    _: dict = Depends(_require_admin_user),
) -> AdminUserDetailResponse:
    new_email = payload.email.lower().strip()
    existing_user = await users_collection.find_one({"email": new_email})
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already exists")

    normalized_role = payload.role.strip().lower()
    if normalized_role not in {"user", "trainer", "moderator"}:
        raise HTTPException(status_code=400, detail="Invalid role")

    normalized_status = payload.status.upper()
    now = datetime.now(timezone.utc)
    temporary_password = _generate_temporary_password()
    country = (payload.country or "").strip()
    derived_country_code = derive_country_code(country) if country else None
    document = {
        "name": payload.fullName.strip(),
        "email": new_email,
        "password_hash": hash_password(temporary_password),
        "role": normalized_role,
        "is_admin": False,
        "status": normalized_status,
        "is_verified": normalized_status == "ACTIVE",
        "contact_number": (payload.contactNumber or "").strip(),
        "country": country,
        "country_code": derived_country_code.upper() if derived_country_code else None,
        "profile_image": (payload.profileImage or "").strip(),
        "subscription_tier": "NONE",
        "subscription_status": "NONE",
        "admin_invited": True,
        "must_reset_password": True,
        "created_at": now,
        "updated_at": now,
    }
    result = await users_collection.insert_one(document)
    record = await users_collection.find_one({"_id": result.inserted_id})
    if not record:
        raise HTTPException(status_code=500, detail="User was created but could not be loaded")
    return AdminUserDetailResponse(**_serialize_admin_user_record(record))

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

        derived_country_code = derive_country_code(payload.country)

        update_doc["country_code"] = derived_country_code.upper() if derived_country_code else None

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
