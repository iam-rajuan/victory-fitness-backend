from fastapi import APIRouter

from ...core.legacy import *

router = APIRouter()

@router.get("/admin/subscription-plans", response_model=AdminSubscriptionPlanListResponse)

async def admin_list_subscription_plans(

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanListResponse:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    return AdminSubscriptionPlanListResponse(items=[AdminSubscriptionPlanItem(**item) for item in items])

@router.post("/admin/subscription-plans", response_model=AdminSubscriptionPlanItem, status_code=status.HTTP_201_CREATED)

async def admin_create_subscription_plan(

    payload: AdminSubscriptionPlanRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanItem:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    plan = _serialize_admin_subscription_plan_item(

        {

            "id": uuid4().hex,

            **payload.model_dump(),

        }

    )

    items.append(plan)

    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, items)

    return AdminSubscriptionPlanItem(**plan)

@router.patch("/admin/subscription-plans/{plan_id}", response_model=AdminSubscriptionPlanItem)

async def admin_update_subscription_plan(

    plan_id: str,

    payload: AdminSubscriptionPlanRequest,

    _: dict = Depends(_require_admin_user),

) -> AdminSubscriptionPlanItem:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    updated_plan: dict | None = None

    for index, item in enumerate(items):

        if item["id"] == plan_id:

            items[index] = _serialize_admin_subscription_plan_item({"id": plan_id, **payload.model_dump()})

            updated_plan = items[index]

            break

    if not updated_plan:

        raise HTTPException(status_code=404, detail="Subscription plan not found")

    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, items)

    return AdminSubscriptionPlanItem(**updated_plan)

@router.delete("/admin/subscription-plans/{plan_id}")

async def admin_delete_subscription_plan(

    plan_id: str,

    _: dict = Depends(_require_admin_user),

) -> dict[str, str]:

    items = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]

    next_items = [item for item in items if item["id"] != plan_id]

    if len(next_items) == len(items):

        raise HTTPException(status_code=404, detail="Subscription plan not found")

    await _replace_items_record(DASHBOARD_SUBSCRIPTION_PLANS_KEY, next_items)

    return {"status": "success", "message": "Subscription plan deleted"}
