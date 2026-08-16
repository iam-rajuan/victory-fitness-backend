from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/audit-logs")
async def admin_list_audit_logs(
    limit: int = 50,
    skip: int = 0,
    action: str | None = None,
    resource: str | None = None,
    admin_email: str | None = Query(default=None, alias="adminEmail"),
    _: dict = Depends(_require_admin_user),
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 200))
    safe_skip = max(0, skip)

    query: dict[str, Any] = {}
    if action:
        query["action"] = action.strip()
    if resource:
        query["resource"] = resource.strip()
    if admin_email:
        query["admin_email"] = admin_email.strip()

    total = await admin_audit_logs_collection.count_documents(query)
    records = await (
        admin_audit_logs_collection
        .find(query, sort=[("created_at", -1)])
        .skip(safe_skip)
        .to_list(length=safe_limit)
    )
    items = [{
        "id": str(record.get("_id") or ""),
        "adminEmail": str(record.get("admin_email") or ""),
        "action": str(record.get("action") or ""),
        "resource": str(record.get("resource") or ""),
        "resourceId": str(record.get("resource_id") or ""),
        "details": record.get("details") or {},
        "createdAt": record.get("created_at"),
    } for record in records]
    return {
        "items": items,
        "total": total,
        "limit": safe_limit,
        "skip": safe_skip,
    }
