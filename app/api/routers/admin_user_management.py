from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/user-management", response_model=AdminUserManagementOverviewResponse)

async def admin_user_management_overview(

    page: int = 1,

    limit: int = 10,

    query: str | None = None,

    year: int | None = None,

    _: dict = Depends(_require_admin_user),

) -> AdminUserManagementOverviewResponse:

    summary, table = await asyncio.gather(

        _build_admin_user_summary_response(year),

        _build_admin_user_list_response(page=page, limit=limit, query=query),

    )

    return AdminUserManagementOverviewResponse(summary=summary, table=table)
