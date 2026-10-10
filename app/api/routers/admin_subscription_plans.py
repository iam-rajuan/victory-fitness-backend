from fastapi import APIRouter

from ...core.legacy import *
from ...dependencies import user_has_active_gold_trial

router = APIRouter()


def _subscription_overview_price_label(value: object, *, free_label: str = "Free", empty_label: str = "—") -> str:
    if value is None or str(value).strip() == "":
        return empty_label
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        return empty_label
    if amount <= 0:
        return free_label
    return f"€{amount}"


def _subscription_overview_tier_label(value: object) -> str:
    raw = str(value or "Subscription Plan").strip()
    if not raw:
        return "Subscription Plan"
    return " ".join(part.capitalize() for part in raw.replace("_", " ").split())


def _subscription_overview_user_plan_key(user: dict) -> str:
    if str(user.get("subscription_purchase_source") or "").strip() == PHASE_ONE_BETA_SUBSCRIPTION_SOURCE:
        return "GOLD_BETA"
    return _normalize_subscription_tier(
        user.get("subscription_tier")
        or user.get("subscription_role")
        or (user.get("subscription") or {}).get("tier")
    )


def _subscription_overview_user_plan_id(user: dict) -> str:
    return str(user.get("subscription_plan_id") or (user.get("subscription") or {}).get("plan_id") or "").strip()


def _subscription_overview_is_deleted(user: dict) -> bool:
    return bool(user.get("is_deleted") or user.get("deleted_at") or user.get("deletedAt"))


def _subscription_overview_monthly_value(user: dict, plan_by_tier: dict[str, dict]) -> float:
    if not bool(user.get("subscription_is_purchased") or (user.get("subscription") or {}).get("is_purchased")):
        return 0.0
    if not _subscription_has_active_access_window(user):
        return 0.0
    tier = _subscription_overview_user_plan_key(user)
    plan = plan_by_tier.get(tier) or {}
    cycle = _normalize_billing_cycle(
        user.get("subscription_billing_cycle") or (user.get("subscription") or {}).get("billing_cycle")
    )
    raw_amount = user.get("subscription_price_amount") or (user.get("subscription") or {}).get("price_amount")
    try:
        amount = float(raw_amount)
    except (TypeError, ValueError):
        price_key = "priceYearly" if cycle == "yearly" else "priceMonthly"
        try:
            amount = float(plan.get(price_key) or 0)
        except (TypeError, ValueError):
            amount = 0.0
    if amount <= 0:
        return 0.0
    return round(amount / 12.0, 2) if cycle == "yearly" else round(amount, 2)


async def _subscription_overview_ghana_warning() -> AdminSubscriptionMarketWarning:
    user_filter = {
        "is_admin": {"$ne": True},
        "$or": [
            {"country_code": "GH"},
            {"country": {"$regex": "^ghana$", "$options": "i"}},
        ],
    }
    registered_users = await users_collection.count_documents(user_filter)
    ledger_payments = await revenue_ledger_collection.count_documents(
        {
            "status": "success",
            "source": "consumer_subscription",
            "market": "GH",
            "recognized_amount": {"$gt": 0},
        }
    )
    event_payments = await payment_events_collection.count_documents(
        {
            "status": "success",
            "market": "GH",
            "amount": {"$gt": 0},
            "type": {"$in": ["subscription_started", "subscription_renewed"]},
        }
    )
    completed_payments = max(ledger_payments, event_payments)
    if registered_users > 0 and completed_payments == 0:
        message = (
            f"Ghana has {registered_users} registered user"
            f"{'' if registered_users == 1 else 's'} and no completed payment. "
            "Until one MoMo or card transaction clears, paid acquisition there should stay paused."
        )
    elif registered_users > 0:
        message = (
            f"Ghana has {registered_users} registered user"
            f"{'' if registered_users == 1 else 's'} and {completed_payments} completed payment"
            f"{'' if completed_payments == 1 else 's'}. Watch conversion quality before increasing spend."
        )
    else:
        message = "No Ghana registered users found yet. Keep market spend paused until the funnel has real signup volume."
    return AdminSubscriptionMarketWarning(
        message=message,
        actionLabel="Review payments",
        market="GH",
        registeredUsers=registered_users,
        completedPayments=completed_payments,
    )


async def _build_subscription_plan_overview() -> AdminSubscriptionOverviewResponse:
    now = datetime.now(timezone.utc)
    plans = [_serialize_admin_subscription_plan_item(item) for item in await _get_dashboard_subscription_plan_items()]
    plan_items = [AdminSubscriptionPlanItem(**item) for item in plans]
    app_plan_by_id = {item["id"]: _serialize_app_subscription_plan_item(item, now) for item in plans}
    plan_by_tier = {
        str(app_plan.get("subscriptionTier") or "").upper(): item
        for item in plans
        for app_plan in [app_plan_by_id[item["id"]]]
    }
    user_rows = await users_collection.find(
        {"is_admin": {"$ne": True}},
        {
            "subscription": 1,
            "subscription_tier": 1,
            "subscription_role": 1,
            "subscription_status": 1,
            "subscription_billing_cycle": 1,
            "subscription_is_purchased": 1,
            "subscription_purchase_source": 1,
            "subscription_plan_id": 1,
            "subscription_price_amount": 1,
            "subscription_expires_at": 1,
            "trial_tier_granted": 1,
            "trial_start_at": 1,
            "trial_end_at": 1,
            "gold_trial": 1,
            "country": 1,
            "country_code": 1,
            "is_deleted": 1,
            "deleted_at": 1,
        },
    ).to_list(length=None)
    enrolled_users = [user for user in user_rows if not _subscription_overview_is_deleted(user) and _subscription_overview_user_plan_key(user) != "NONE"]
    active_users = [user for user in enrolled_users if _subscription_has_active_access_window(user)]
    paying_users = [user for user in active_users if bool(user.get("subscription_is_purchased") or (user.get("subscription") or {}).get("is_purchased"))]
    mrr_by_tier: dict[str, float] = {}
    for user in paying_users:
        tier = _subscription_overview_user_plan_key(user)
        mrr_by_tier[tier] = round(mrr_by_tier.get(tier, 0.0) + _subscription_overview_monthly_value(user, plan_by_tier), 2)
    total_mrr = round(sum(mrr_by_tier.values()), 2)

    rows: list[AdminSubscriptionOverviewRow] = []
    for plan, plan_item in zip(plans, plan_items):
        app_plan = app_plan_by_id[plan["id"]]
        tier_key = str(app_plan.get("subscriptionTier") or "").upper()
        plan_id = str(plan.get("id") or "")
        enrolled = [
            user
            for user in enrolled_users
            if _subscription_overview_user_plan_key(user) == tier_key
            or (plan_id and _subscription_overview_user_plan_id(user) == plan_id)
        ]
        active_enrolled = [user for user in enrolled if _subscription_has_active_access_window(user)]
        purchased_enrolled = [
            user
            for user in enrolled
            if bool(user.get("subscription_is_purchased") or (user.get("subscription") or {}).get("is_purchased"))
        ]
        mrr = round(mrr_by_tier.get(tier_key, 0.0), 2)
        share = round((mrr / total_mrr) * 100, 1) if total_mrr > 0 else 0.0
        is_free_plan = (plan.get("priceYearly") == 0) and (plan.get("priceMonthly") == 0)
        price_yearly = "Application" if plan.get("isApplicationOnly") else _subscription_overview_price_label(plan.get("priceYearly"))
        price_monthly = "—" if plan.get("isApplicationOnly") or is_free_plan else _subscription_overview_price_label(plan.get("priceMonthly"), empty_label="—")
        rows.append(
            AdminSubscriptionOverviewRow(
                id=plan_id,
                planId=plan_id,
                tier=tier_key,
                label=_subscription_overview_tier_label(plan.get("tier")),
                priceYearly=price_yearly,
                priceMonthly=price_monthly,
                subscribers=len(enrolled),
                subscriberLabel=str(len(enrolled)),
                shareOfMrr=share,
                shareOfMrrLabel=f"{share:g}%",
                mrr=mrr,
                tone="good" if mrr > 0 else "warn",
                activeSubscribers=len(active_enrolled),
                payingSubscribers=len(purchased_enrolled),
                rawPlan=plan_item,
            )
        )

    active_gold_trials = [
        user
        for user in user_rows
        if not _subscription_overview_is_deleted(user)
        and str(user.get("subscription_purchase_source") or "").strip() != PHASE_ONE_BETA_SUBSCRIPTION_SOURCE
        and user_has_active_gold_trial(user, now)
    ]
    if active_gold_trials:
        rows.append(
            AdminSubscriptionOverviewRow(
                id="trial-gold",
                tier="GOLD",
                label="5-Day trial · Gold",
                priceYearly="Free",
                priceMonthly="—",
                subscribers=len(active_gold_trials),
                subscriberLabel=f"{len(active_gold_trials)} running",
                shareOfMrr=0,
                shareOfMrrLabel="0%",
                mrr=0,
                tone="warn",
                isTrial=True,
            )
        )

    top_tier = max(mrr_by_tier.items(), key=lambda item: item[1], default=("", 0.0))
    failed_renewals = await payment_events_collection.count_documents(
        {
            "$or": [
                {"status": {"$in": ["failed", "declined", "error"]}},
                {"type": {"$regex": "fail|declin", "$options": "i"}},
            ]
        }
    )
    arpu = round(total_mrr / len(paying_users), 2) if paying_users else 0.0
    stats = [
        AdminSubscriptionOverviewStat(key="MRR", value=f"€{total_mrr:,.0f}", note="Calculated from active purchased subscriptions"),
        AdminSubscriptionOverviewStat(key="PAYING", value=str(len(paying_users)), note="Active purchased subscribers"),
        AdminSubscriptionOverviewStat(key="ARPU", value=f"€{arpu:,.0f}", note="Monthly average per paying subscriber"),
        AdminSubscriptionOverviewStat(
            key="FAILED RENEWALS",
            value=str(failed_renewals),
            note="Failed or declined payment events",
        ),
    ]
    if top_tier[0] and total_mrr > 0:
        stats[1].note = f"{_subscription_overview_tier_label(top_tier[0])} is {round((top_tier[1] / total_mrr) * 100):g}% of MRR"

    paid_plans = [plan for plan in plans if not plan.get("isApplicationOnly") and (plan.get("priceYearly") or plan.get("priceMonthly"))]
    plan_count = len(plans)
    market_count = len(
        {
            str(user.get("country_code") or user.get("country") or "").strip().upper()
            for user in user_rows
            if str(user.get("country_code") or user.get("country") or "").strip()
        }
    )
    summary = f"{plan_count} live catalog plan{'' if plan_count == 1 else 's'} · {len(paid_plans)} paid · {market_count} market{'' if market_count == 1 else 's'} with registered users"
    return AdminSubscriptionOverviewResponse(
        plans=plan_items,
        rows=rows,
        stats=stats,
        warning=await _subscription_overview_ghana_warning(),
        summary=summary,
        totalMrr=total_mrr,
        payingSubscribers=len(paying_users),
    )

def _validate_subscription_plan_feature_access(payload: AdminSubscriptionPlanRequest) -> None:
    invalid_features = _find_invalid_plan_feature_access(payload.model_dump())
    if invalid_features:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown subscription feature keys: {', '.join(invalid_features)}",
        )

@router.get("/admin/subscription-features", response_model=AdminSubscriptionFeatureListResponse)
async def admin_list_subscription_features(
    _: dict = Depends(_require_admin_user),
) -> AdminSubscriptionFeatureListResponse:
    items = [AdminSubscriptionFeatureItem(**item) for item in _get_subscription_feature_catalog()]
    return AdminSubscriptionFeatureListResponse(items=items)


@router.get("/admin/subscription-plans/overview", response_model=AdminSubscriptionOverviewResponse)
async def admin_subscription_plan_overview(
    _: dict = Depends(_require_admin_user),
) -> AdminSubscriptionOverviewResponse:
    return await _build_subscription_plan_overview()

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
    _validate_subscription_plan_feature_access(payload)

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
    _validate_subscription_plan_feature_access(payload)

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

    await users_collection.update_many(
        {
            "subscription_status": "ACTIVE",
            "$or": [
                {"subscription_plan_id": plan_id},
                *(
                    [{"subscription_purchase_source": PHASE_ONE_BETA_SUBSCRIPTION_SOURCE}]
                    if plan_id == PHASE_ONE_BETA_PLAN_ID
                    else []
                ),
            ],
        },
        {
            "$set": {
                "subscription_access": updated_plan["featureAccess"],
                "subscription.access": updated_plan["featureAccess"],
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

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
