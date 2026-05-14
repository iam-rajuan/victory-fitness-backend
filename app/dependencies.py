from bson import ObjectId
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .database import users_collection
from .security import decode_token


bearer_scheme = HTTPBearer(auto_error=False)


async def get_verified_user(authorization: str | None) -> dict:
    token = (authorization or "").replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await get_verified_user_from_access_token(token)


async def get_verified_user_from_access_token(token: str) -> dict:
    try:
        data = decode_token(token, "access")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    try:
        user_id = ObjectId(data["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc

    user = await users_collection.find_one({"_id": user_id, "is_verified": True})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid access token")

    return user


async def require_access_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")

    return await get_verified_user(f"Bearer {token}")


async def require_admin_user(user: dict = Security(require_access_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
