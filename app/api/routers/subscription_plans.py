from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/subscription-plans", response_model=AppSubscriptionPlanListResponse)

async def list_subscription_plans() -> AppSubscriptionPlanListResponse:

    items = [_serialize_app_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    return AppSubscriptionPlanListResponse(items=[AppSubscriptionPlanItem(**item) for item in items])
