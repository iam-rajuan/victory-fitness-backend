from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from ...database import (
    affiliate_conversions_collection,
    coach_victor_threads_collection,
    corporate_accounts_collection,
    corporate_seat_assignments_collection,
    marketplace_orders_collection,
    meal_analysis_entries_collection,
    users_collection,
    workout_logs_collection,
)
from ...models import (
    AdminAffiliateConversionRequest,
    AdminCorporateAccountItem,
    AdminCorporateAccountListResponse,
    AdminCorporateAccountRequest,
    AdminCorporateDashboardResponse,
    AdminCorporateSeatAssignmentRequest,
    AdminCorporateSeatAssignmentResponse,
    AdminMarketplaceOrderRequest,
    AdminReferralRewardRequest,
    AdminRevenueActionResponse,
    ReferralProgramClaimRequest,
    ReferralProgramStatusResponse,
)
from ...revenue_service import (
    claim_referral_code,
    compute_marketplace_platform_fee,
    corporate_dashboard_snapshot,
    grant_referral_reward,
    record_revenue_entry,
    referral_program_status,
)
from ...core.legacy import _record_analytics_event, _require_access_user, _require_admin_user

router = APIRouter()


@router.get("/admin/revenue/corporate-accounts", response_model=AdminCorporateAccountListResponse)
async def admin_list_corporate_accounts(_: dict = Depends(_require_admin_user)) -> AdminCorporateAccountListResponse:
    rows = await corporate_accounts_collection.find({}).sort("created_at", -1).to_list(length=None)
    items: list[AdminCorporateAccountItem] = []
    for row in rows:
        active_seats = await corporate_seat_assignments_collection.count_documents(
            {"organization_id": str(row.get("_id")), "status": "active"}
        )
        items.append(
            AdminCorporateAccountItem(
                id=str(row.get("_id")),
                name=str(row.get("name") or ""),
                status=str(row.get("status") or "active"),
                billingCurrency=str(row.get("billing_currency") or "EUR"),
                seatPriceMonthly=float(row.get("seat_price_monthly") or 0),
                seatPriceYearly=float(row.get("seat_price_yearly") or 0),
                hrDashboardEnabled=bool(row.get("hr_dashboard_enabled", True)),
                activeSeats=active_seats,
                createdAt=row.get("created_at") or datetime.now(timezone.utc),
            )
        )
    return AdminCorporateAccountListResponse(items=items)


@router.post("/admin/revenue/corporate-accounts", response_model=AdminCorporateAccountItem, status_code=status.HTTP_201_CREATED)
async def admin_create_corporate_account(
    payload: AdminCorporateAccountRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminCorporateAccountItem:
    now = datetime.now(timezone.utc)
    doc = {
        "name": str(payload.name).strip(),
        "status": payload.status,
        "billing_currency": str(payload.billingCurrency or "EUR").upper(),
        "seat_price_monthly": float(payload.seatPriceMonthly or 0),
        "seat_price_yearly": float(payload.seatPriceYearly or 0),
        "hr_dashboard_enabled": bool(payload.hrDashboardEnabled),
        "created_at": now,
        "updated_at": now,
        "created_by": str(admin.get("_id") or ""),
    }
    result = await corporate_accounts_collection.insert_one(doc)
    await _record_analytics_event("corporate_account_created", user_id=str(admin.get("_id") or ""), details={"organization_id": str(result.inserted_id)})
    return AdminCorporateAccountItem(
        id=str(result.inserted_id),
        name=doc["name"],
        status=doc["status"],
        billingCurrency=doc["billing_currency"],
        seatPriceMonthly=doc["seat_price_monthly"],
        seatPriceYearly=doc["seat_price_yearly"],
        hrDashboardEnabled=doc["hr_dashboard_enabled"],
        activeSeats=0,
        createdAt=now,
    )


@router.post("/admin/revenue/corporate-accounts/{organization_id}/seats", response_model=AdminCorporateSeatAssignmentResponse)
async def admin_assign_corporate_seat(
    organization_id: str,
    payload: AdminCorporateSeatAssignmentRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminCorporateSeatAssignmentResponse:
    if not ObjectId.is_valid(organization_id):
        raise HTTPException(status_code=404, detail="Corporate account not found")
    organization = await corporate_accounts_collection.find_one({"_id": ObjectId(organization_id)})
    if not organization:
        raise HTTPException(status_code=404, detail="Corporate account not found")
    user_filter = {"_id": ObjectId(payload.userId)} if ObjectId.is_valid(payload.userId) else {"_id": payload.userId}
    member = await users_collection.find_one(user_filter)
    if not member:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await corporate_seat_assignments_collection.find_one(
        {"organization_id": organization_id, "user_id": payload.userId}
    )
    price = float(
        organization.get("seat_price_yearly") if payload.billingCycle == "yearly" else organization.get("seat_price_monthly") or 0
    )
    now = datetime.now(timezone.utc)
    update_doc = {
        "organization_id": organization_id,
        "user_id": payload.userId,
        "billing_cycle": payload.billingCycle,
        "status": payload.status,
        "amount": price,
        "currency": str(organization.get("billing_currency") or "EUR").upper(),
        "updated_at": now,
        "created_by": str(admin.get("_id") or ""),
    }
    if existing:
        await corporate_seat_assignments_collection.update_one({"_id": existing["_id"]}, {"$set": update_doc})
        seat_id = str(existing["_id"])
    else:
        update_doc["created_at"] = now
        result = await corporate_seat_assignments_collection.insert_one(update_doc)
        seat_id = str(result.inserted_id)

    await users_collection.update_one(
        user_filter,
        {
            "$set": {
                "corporate_membership.organization_id": organization_id,
                "corporate_membership.organization_name": str(organization.get("name") or ""),
                "corporate_membership.status": payload.status,
                "corporate_membership.billing_cycle": payload.billingCycle,
                "corporate_membership.updated_at": now,
                "updated_at": now,
            }
        },
    )

    ledger_id = None
    if payload.status == "active" and (not existing or str(existing.get("status") or "") != "active" or str(existing.get("billing_cycle") or "") != payload.billingCycle):
        ledger_id = await record_revenue_entry(
            source="corporate_seat",
            gross_amount=price,
            net_amount=price,
            currency=update_doc["currency"],
            market=str(member.get("country_code") or ""),
            user_id=payload.userId,
            organization_id=organization_id,
            billing_cycle=payload.billingCycle,
            external_ref=f"corporate_seat:{organization_id}:{payload.userId}:{payload.billingCycle}:{seat_id}",
            metadata={"organization_name": str(organization.get("name") or "")},
        )
    await _record_analytics_event(
        "corporate_seat_assigned",
        user_id=str(admin.get("_id") or ""),
        details={"organization_id": organization_id, "member_user_id": payload.userId, "billing_cycle": payload.billingCycle},
    )
    return AdminCorporateSeatAssignmentResponse(
        seatId=seat_id,
        organizationId=organization_id,
        userId=payload.userId,
        billingCycle=payload.billingCycle,
        status=payload.status,
        amount=price,
        currency=update_doc["currency"],
        createdAt=existing.get("created_at") if existing else now,
    )


@router.get("/admin/revenue/corporate-accounts/{organization_id}/dashboard", response_model=AdminCorporateDashboardResponse)
async def admin_corporate_dashboard(
    organization_id: str,
    _: dict = Depends(_require_admin_user),
) -> AdminCorporateDashboardResponse:
    if not ObjectId.is_valid(organization_id):
        raise HTTPException(status_code=404, detail="Corporate account not found")
    organization = await corporate_accounts_collection.find_one({"_id": ObjectId(organization_id)})
    if not organization:
        raise HTTPException(status_code=404, detail="Corporate account not found")
    snapshot = await corporate_dashboard_snapshot(
        organization_id=organization_id,
        workout_logs_collection=workout_logs_collection,
        meal_analysis_entries_collection=meal_analysis_entries_collection,
        coach_victor_threads_collection=coach_victor_threads_collection,
    )
    return AdminCorporateDashboardResponse(
        organizationId=organization_id,
        organizationName=str(organization.get("name") or ""),
        totalSeats=int(snapshot["totalSeats"]),
        activeSeats=int(snapshot["activeSeats"]),
        employeesWithAnyActivity=int(snapshot["employeesWithAnyActivity"]),
        anonymizedEngagementPct=float(snapshot["anonymizedEngagementPct"]),
        marketBreakdown=dict(snapshot["marketBreakdown"]),
        lastUpdated=datetime.now(timezone.utc),
    )


@router.post("/admin/revenue/marketplace/orders", response_model=AdminRevenueActionResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_marketplace_order(
    payload: AdminMarketplaceOrderRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminRevenueActionResponse:
    now = datetime.now(timezone.utc)
    platform_fee = compute_marketplace_platform_fee(payload.amount)
    doc = {
        "coach_name": payload.coachName.strip(),
        "coach_user_id": str(payload.coachUserId or "").strip() or None,
        "customer_user_id": str(payload.customerUserId or "").strip() or None,
        "description": str(payload.description or "").strip(),
        "amount": float(payload.amount),
        "currency": str(payload.currency or "EUR").upper(),
        "market": str(payload.market or "OTHER").upper(),
        "status": payload.status,
        "platform_fee_amount": platform_fee,
        "coach_payout_amount": round(float(payload.amount) - platform_fee, 2),
        "created_at": now,
        "created_by": str(admin.get("_id") or ""),
    }
    result = await marketplace_orders_collection.insert_one(doc)
    ledger_id = None
    if payload.status == "paid":
        ledger_id = await record_revenue_entry(
            source="coach_marketplace_fee",
            gross_amount=float(payload.amount),
            net_amount=platform_fee,
            platform_fee_amount=platform_fee,
            currency=doc["currency"],
            market=doc["market"],
            user_id=doc["customer_user_id"],
            external_ref=f"marketplace_order:{result.inserted_id}",
            metadata={"coach_name": doc["coach_name"], "coach_payout_amount": doc["coach_payout_amount"]},
        )
    await _record_analytics_event("marketplace_order_recorded", user_id=str(admin.get("_id") or ""), details={"order_id": str(result.inserted_id)})
    return AdminRevenueActionResponse(id=str(result.inserted_id), ledgerId=ledger_id)


@router.post("/admin/revenue/affiliate/conversions", response_model=AdminRevenueActionResponse, status_code=status.HTTP_201_CREATED)
async def admin_record_affiliate_conversion(
    payload: AdminAffiliateConversionRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminRevenueActionResponse:
    if not payload.disclosureAccepted:
        raise HTTPException(status_code=400, detail="Affiliate conversions require disclosure confirmation")
    now = datetime.now(timezone.utc)
    doc = {
        "partner_name": payload.partnerName.strip(),
        "product_name": payload.productName.strip(),
        "amount": float(payload.amount),
        "currency": str(payload.currency or "EUR").upper(),
        "market": str(payload.market or "OTHER").upper(),
        "attributed_user_id": str(payload.attributedUserId or "").strip() or None,
        "click_id": str(payload.clickId or "").strip() or None,
        "disclosure_accepted": True,
        "created_at": now,
        "created_by": str(admin.get("_id") or ""),
    }
    result = await affiliate_conversions_collection.insert_one(doc)
    ledger_id = await record_revenue_entry(
        source="affiliate_commission",
        gross_amount=float(payload.amount),
        net_amount=float(payload.amount),
        currency=doc["currency"],
        market=doc["market"],
        user_id=doc["attributed_user_id"],
        external_ref=f"affiliate_conversion:{result.inserted_id}",
        metadata={"partner_name": doc["partner_name"], "product_name": doc["product_name"], "click_id": doc["click_id"]},
    )
    await _record_analytics_event("affiliate_conversion_recorded", user_id=str(admin.get("_id") or ""), details={"conversion_id": str(result.inserted_id)})
    return AdminRevenueActionResponse(id=str(result.inserted_id), ledgerId=ledger_id)


@router.post("/admin/revenue/referrals/rewards", response_model=AdminRevenueActionResponse, status_code=status.HTTP_201_CREATED)
async def admin_grant_referral_reward(
    payload: AdminReferralRewardRequest,
    admin: dict = Depends(_require_admin_user),
) -> AdminRevenueActionResponse:
    reward_id, ledger_id = await grant_referral_reward(
        referrer_user_id=payload.referrerUserId,
        referred_user_id=payload.referredUserId,
        amount=float(payload.amount),
        currency=payload.currency,
        market=payload.market,
        source_subscription_tier=payload.sourceSubscriptionTier,
        reward_type="manual_reward",
        external_ref=f"manual_referral_reward:{payload.referrerUserId}:{payload.referredUserId or 'none'}:{datetime.now(timezone.utc).isoformat()}",
    )
    await _record_analytics_event("referral_reward_granted", user_id=str(admin.get("_id") or ""), details={"reward_id": reward_id})
    return AdminRevenueActionResponse(id=reward_id, ledgerId=ledger_id)


@router.get("/me/referral-program", response_model=ReferralProgramStatusResponse)
async def get_me_referral_program(user: dict = Depends(_require_access_user)) -> ReferralProgramStatusResponse:
    return ReferralProgramStatusResponse(**(await referral_program_status(user)))


@router.post("/me/referral-program/claim-code", response_model=ReferralProgramStatusResponse)
async def claim_me_referral_code(
    payload: ReferralProgramClaimRequest,
    user: dict = Depends(_require_access_user),
) -> ReferralProgramStatusResponse:
    try:
        await claim_referral_code(user, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated = await users_collection.find_one({"_id": user["_id"]}) or user
    return ReferralProgramStatusResponse(**(await referral_program_status(updated)))
