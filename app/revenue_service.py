from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

from .database import (
    affiliate_conversions_collection,
    corporate_seat_assignments_collection,
    referral_rewards_collection,
    revenue_ledger_collection,
    users_collection,
)

REVENUE_SOURCE_LABELS = {
    "consumer_subscription": "Consumer subscriptions",
    "corporate_seat": "Corporate wellness seats",
    "coach_marketplace_fee": "Coach marketplace fee",
    "affiliate_commission": "Supplement affiliate commission",
    "referral_commission": "Referral reward programme",
}

RECURRING_REVENUE_SOURCES = {"consumer_subscription", "corporate_seat"}
REFERRAL_LEGEND_THRESHOLD = 11
REFERRAL_REVENUE_SHARE_PCT = 20
MARKETPLACE_PLATFORM_FEE_PCT = 20


def normalize_market_code(value: str | None) -> str:
    market = str(value or "").strip().upper()
    return market if market else "OTHER"


def referral_share_pct_for_count(successful_referrals: int) -> int:
    return REFERRAL_REVENUE_SHARE_PCT if successful_referrals >= REFERRAL_LEGEND_THRESHOLD else 0


def referral_legend_unlocked(successful_referrals: int) -> bool:
    return successful_referrals >= REFERRAL_LEGEND_THRESHOLD


def compute_marketplace_platform_fee(amount: float) -> float:
    return round(max(float(amount or 0), 0) * (MARKETPLACE_PLATFORM_FEE_PCT / 100.0), 2)


def build_referral_code(user: dict) -> str:
    name_seed = "".join(ch for ch in str(user.get("name") or "member").upper() if ch.isalnum())[:6] or "MEMBER"
    identifier = str(user.get("_id") or user.get("id") or "")[-6:].upper() or "000001"
    return f"{name_seed}-{identifier}"


async def ensure_user_referral_code(user: dict) -> str:
    existing_code = str((user.get("referral_program") or {}).get("code") or "").strip().upper()
    if existing_code:
        return existing_code
    code = build_referral_code(user)
    now = datetime.now(timezone.utc)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "referral_program.code": code,
                "referral_program.updated_at": now,
                "updated_at": now,
            }
        },
    )
    return code


async def record_revenue_entry(
    *,
    source: str,
    gross_amount: float,
    currency: str,
    market: str | None = None,
    net_amount: float | None = None,
    platform_fee_amount: float = 0,
    status: str = "success",
    user_id: str | None = None,
    organization_id: str | None = None,
    subscription_tier: str | None = None,
    billing_cycle: str | None = None,
    external_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    gross = round(max(float(gross_amount or 0), 0), 2)
    fee = round(max(float(platform_fee_amount or 0), 0), 2)
    recognized = round(max(float(net_amount if net_amount is not None else gross - fee), 0), 2)
    now = datetime.now(timezone.utc)
    doc = {
        "source": source,
        "label": REVENUE_SOURCE_LABELS.get(source, source.replace("_", " ").title()),
        "gross_amount": gross,
        "platform_fee_amount": fee,
        "recognized_amount": recognized,
        "currency": str(currency or "EUR").upper(),
        "market": normalize_market_code(market),
        "status": status,
        "user_id": str(user_id or "").strip() or None,
        "organization_id": str(organization_id or "").strip() or None,
        "subscription_tier": str(subscription_tier or "").strip().upper() or None,
        "billing_cycle": str(billing_cycle or "").strip().lower() or None,
        "external_ref": str(external_ref or "").strip() or None,
        "metadata": metadata or {},
        "created_at": now,
    }
    result = await revenue_ledger_collection.insert_one(doc)
    return str(result.inserted_id)


async def count_successful_referrals(referrer_user_id: str) -> int:
    return await referral_rewards_collection.count_documents(
        {"referrer_user_id": referrer_user_id, "status": "success"}
    )


async def grant_referral_reward(
    *,
    referrer_user_id: str,
    referred_user_id: str | None,
    amount: float,
    currency: str,
    market: str | None = None,
    source_subscription_tier: str | None = None,
    reward_type: str = "paid_conversion",
    external_ref: str | None = None,
) -> tuple[str, str | None]:
    now = datetime.now(timezone.utc)
    doc = {
        "referrer_user_id": referrer_user_id,
        "referred_user_id": referred_user_id,
        "amount": round(max(float(amount or 0), 0), 2),
        "currency": str(currency or "EUR").upper(),
        "market": normalize_market_code(market),
        "source_subscription_tier": str(source_subscription_tier or "").strip().upper() or None,
        "reward_type": reward_type,
        "status": "success",
        "external_ref": str(external_ref or "").strip() or None,
        "created_at": now,
    }
    result = await referral_rewards_collection.insert_one(doc)
    successful_referrals = await count_successful_referrals(referrer_user_id)
    share_pct = referral_share_pct_for_count(successful_referrals)
    legend = referral_legend_unlocked(successful_referrals)
    ledger_id = None
    if share_pct > 0 and amount > 0:
        ledger_id = await record_revenue_entry(
            source="referral_commission",
            gross_amount=amount,
            net_amount=amount,
            currency=currency,
            market=market,
            user_id=referrer_user_id,
            subscription_tier=source_subscription_tier,
            external_ref=external_ref or f"referral_reward:{result.inserted_id}",
            metadata={
                "reward_type": reward_type,
                "referred_user_id": referred_user_id,
                "share_pct": share_pct,
                "legend_unlocked": legend,
            },
        )
    await users_collection.update_one(
        {"_id": ObjectId(referrer_user_id)} if ObjectId.is_valid(referrer_user_id) else {"_id": referrer_user_id},
        {
            "$set": {
                "referral_program.successful_referrals": successful_referrals,
                "referral_program.legend_unlocked": legend,
                "referral_program.revenue_share_pct": share_pct,
                "referral_program.updated_at": now,
                "updated_at": now,
            }
        },
    )
    return str(result.inserted_id), ledger_id


async def maybe_grant_referral_reward_for_subscription(
    *,
    user: dict,
    amount: float,
    currency: str,
    subscription_tier: str,
    external_ref: str,
) -> str | None:
    referral_program = user.get("referral_program") if isinstance(user.get("referral_program"), dict) else {}
    referrer_user_id = str(referral_program.get("referred_by_user_id") or "").strip()
    if not referrer_user_id:
        return None
    existing = await referral_rewards_collection.find_one(
        {
            "referred_user_id": str(user.get("_id") or ""),
            "reward_type": "paid_conversion",
            "external_ref": external_ref,
        }
    )
    if existing:
        return str(existing.get("_id"))
    reward_id, _ = await grant_referral_reward(
        referrer_user_id=referrer_user_id,
        referred_user_id=str(user.get("_id") or ""),
        amount=round(max(float(amount or 0), 0) * (REFERRAL_REVENUE_SHARE_PCT / 100.0), 2),
        currency=currency,
        market=str(user.get("country_code") or ""),
        source_subscription_tier=subscription_tier,
        reward_type="paid_conversion",
        external_ref=external_ref,
    )
    return reward_id


async def referral_program_status(user: dict) -> dict[str, Any]:
    code = await ensure_user_referral_code(user)
    successful = await count_successful_referrals(str(user.get("_id") or ""))
    total_earned = 0.0
    rows = await referral_rewards_collection.find(
        {"referrer_user_id": str(user.get("_id") or ""), "status": "success"},
        {"amount": 1, "currency": 1},
    ).to_list(length=None)
    currency = "EUR"
    for row in rows:
        total_earned += float(row.get("amount") or 0)
        currency = str(row.get("currency") or currency).upper()
    return {
        "code": code,
        "successfulReferrals": successful,
        "legendUnlocked": referral_legend_unlocked(successful),
        "revenueSharePct": referral_share_pct_for_count(successful),
        "totalEarned": round(total_earned, 2),
        "currency": currency,
        "referredByCode": str((user.get("referral_program") or {}).get("referred_by_code") or "").strip() or None,
    }


async def claim_referral_code(user: dict, code: str) -> None:
    normalized_code = str(code or "").strip().upper()
    if not normalized_code:
        return
    if normalized_code == await ensure_user_referral_code(user):
        raise ValueError("You cannot use your own referral code")
    referrer = await users_collection.find_one({"referral_program.code": normalized_code}, {"_id": 1})
    if not referrer:
        raise ValueError("Referral code not found")
    now = datetime.now(timezone.utc)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "referral_program.referred_by_code": normalized_code,
                "referral_program.referred_by_user_id": str(referrer.get("_id") or ""),
                "referral_program.claimed_at": now,
                "updated_at": now,
            }
        },
    )


async def corporate_dashboard_snapshot(
    *,
    organization_id: str,
    workout_logs_collection,
    meal_analysis_entries_collection,
    coach_victor_threads_collection,
) -> dict[str, Any]:
    seats = await corporate_seat_assignments_collection.find(
        {"organization_id": organization_id, "status": "active"}
    ).to_list(length=None)
    user_ids = [str(item.get("user_id") or "") for item in seats if str(item.get("user_id") or "").strip()]
    total_seats = await corporate_seat_assignments_collection.count_documents({"organization_id": organization_id})
    if not user_ids:
        return {
            "totalSeats": total_seats,
            "activeSeats": 0,
            "employeesWithAnyActivity": 0,
            "anonymizedEngagementPct": 0.0,
            "marketBreakdown": {},
        }

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=30)
    activity_sets = []
    for collection, date_field in (
        (workout_logs_collection, "started_at"),
        (meal_analysis_entries_collection, "created_at"),
        (coach_victor_threads_collection, "created_at"),
    ):
        rows = await collection.find(
            {"user_id": {"$in": user_ids}, date_field: {"$gte": window_start, "$lte": now}},
            {"user_id": 1},
        ).to_list(length=None)
        activity_sets.extend(str(row.get("user_id") or "") for row in rows if str(row.get("user_id") or "").strip())
    active_user_ids = {value for value in activity_sets if value}
    users = await users_collection.find(
        {"_id": {"$in": [ObjectId(user_id) for user_id in user_ids if ObjectId.is_valid(user_id)]}},
        {"country_code": 1},
    ).to_list(length=None)
    market_breakdown: dict[str, int] = {}
    for user in users:
        code = normalize_market_code(str(user.get("country_code") or "OTHER"))
        market_breakdown[code] = market_breakdown.get(code, 0) + 1
    active_seats = len(user_ids)
    return {
        "totalSeats": total_seats,
        "activeSeats": active_seats,
        "employeesWithAnyActivity": len(active_user_ids),
        "anonymizedEngagementPct": round((len(active_user_ids) / active_seats) * 100, 1) if active_seats else 0.0,
        "marketBreakdown": market_breakdown,
    }
