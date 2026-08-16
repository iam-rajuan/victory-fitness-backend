from fastapi import APIRouter, Depends

from ...core.legacy import _require_admin_user
from ...models import DashboardOverviewResponse
from ...services.admin_dashboard import build_admin_dashboard_overview


router = APIRouter()


@router.get("/admin/dashboard/overview", response_model=DashboardOverviewResponse)
async def admin_dashboard_overview(
    year: int | None = None,
    _: dict = Depends(_require_admin_user),
) -> DashboardOverviewResponse:
    return await build_admin_dashboard_overview(year)
