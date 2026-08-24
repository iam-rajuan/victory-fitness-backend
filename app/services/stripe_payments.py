from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import stripe
from bson import ObjectId
from fastapi import HTTPException, Request

from ..config import settings
from ..core.legacy import (
    _normalize_billing_cycle,
    _normalize_subscription_tier,
    _record_analytics_event,
    _resolve_subscription_access,
    _resolve_subscription_checkout_plan,
    _trial_outcome_for_subscription,
    notify_user,
)
from ..database import payment_events_collection, users_collection
from ..models import StripeCheckoutSessionRequest, StripeCheckoutSessionResponse


STRIPE_CHECKOUT_COMPLETED = "checkout.session.completed"
STRIPE_INVOICE_PAID = "invoice.paid"
STRIPE_SUBSCRIPTION_DELETED = "customer.subscription.deleted"
STRIPE_SUBSCRIPTION_UPDATED = "customer.subscription.updated"


def _require_stripe_configured() -> None:
    if settings.phase_one_beta_enabled or not settings.stripe_payments_enabled:
        raise HTTPException(
            status_code=503,
            detail="Stripe payments are temporarily disabled during the Phase 1 beta campaign",
        )
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")


def _safe_redirect_url(value: str | None, fallback: str) -> str:
    url = str(value or fallback or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Checkout redirect URLs must be absolute HTTP(S) URLs")
    return url


def _to_stripe_amount(value: object) -> int:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Selected plan does not have a valid price") from exc
    cents = int(round(amount * 100))
    if cents <= 0:
        raise HTTPException(status_code=400, detail="Selected plan does not have a payable price")
    return cents


async def _ensure_stripe_customer(user: dict) -> str:
    existing_customer_id = str(user.get("stripe_customer_id") or "").strip()
    if existing_customer_id:
        return existing_customer_id

    def create_customer() -> stripe.Customer:
        stripe.api_key = settings.stripe_secret_key
        return stripe.Customer.create(
            email=str(user.get("email") or "").strip() or None,
            name=str(user.get("name") or "").strip() or None,
            metadata={"user_id": str(user["_id"])},
        )

    customer = await asyncio.to_thread(create_customer)
    customer_id = str(customer.id)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"stripe_customer_id": customer_id, "updated_at": datetime.now(timezone.utc)}},
    )
    return customer_id


async def create_subscription_checkout_session(
    user: dict,
    payload: StripeCheckoutSessionRequest,
) -> StripeCheckoutSessionResponse:
    _require_stripe_configured()

    tier = _normalize_subscription_tier(payload.subscription_tier)
    billing_cycle = _normalize_billing_cycle(payload.billing_cycle)
    plan = await _resolve_subscription_checkout_plan(tier, billing_cycle, payload.plan_id)
    if not plan or plan["price"] is None:
        raise HTTPException(status_code=400, detail="Selected plan cannot be purchased with Stripe Checkout")

    customer_id = await _ensure_stripe_customer(user)
    unit_amount = _to_stripe_amount(plan["price"])
    interval = "month" if billing_cycle == "monthly" else "year"
    success_url = _safe_redirect_url(payload.success_url, settings.stripe_checkout_success_url)
    cancel_url = _safe_redirect_url(payload.cancel_url, settings.stripe_checkout_cancel_url)
    metadata = {
        "user_id": str(user["_id"]),
        "subscription_tier": tier,
        "billing_cycle": billing_cycle,
        "plan_id": str(plan["plan_id"]),
    }

    def create_session() -> stripe.checkout.Session:
        stripe.api_key = settings.stripe_secret_key
        return stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=str(user["_id"]),
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            line_items=[
                {
                    "price_data": {
                        "currency": settings.stripe_currency,
                        "unit_amount": unit_amount,
                        "product_data": {
                            "name": str(plan["title"] or f"Victory {tier.title()}"),
                            "metadata": {"plan_id": str(plan["plan_id"]), "subscription_tier": tier},
                        },
                        "recurring": {"interval": interval},
                    },
                    "quantity": 1,
                }
            ],
            metadata=metadata,
            subscription_data={"metadata": metadata},
        )

    session = await asyncio.to_thread(create_session)
    checkout_url = str(session.url or "")
    if not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe did not return a checkout URL")

    return StripeCheckoutSessionResponse(checkout_url=checkout_url, session_id=str(session.id))


def _extract_event_object(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    obj = data.get("object") if isinstance(data.get("object"), dict) else {}
    return obj


async def construct_stripe_event(request: Request) -> dict[str, Any]:
    _require_stripe_configured()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")

    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        return stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook payload") from exc
    except stripe.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature") from exc


async def handle_stripe_event(event: dict[str, Any]) -> None:
    if not settings.stripe_payments_enabled:
        return
    event_id = str(event.get("id") or "")
    if event_id and await payment_events_collection.find_one({"stripe_event_id": event_id}):
        return

    event_type = str(event.get("type") or "")
    obj = _extract_event_object(event)

    if event_type == STRIPE_CHECKOUT_COMPLETED:
        await _handle_checkout_completed(event_id, obj)
        return

    if event_type == STRIPE_INVOICE_PAID:
        await _record_stripe_payment_event(event_id, event_type, obj, status="success")
        return

    if event_type in {STRIPE_SUBSCRIPTION_DELETED, STRIPE_SUBSCRIPTION_UPDATED}:
        await _handle_subscription_event(event_id, event_type, obj)
        return

    await _record_stripe_payment_event(event_id, event_type, obj, status="ignored")


async def _handle_checkout_completed(event_id: str, session: dict[str, Any]) -> None:
    metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    user_id = str(metadata.get("user_id") or session.get("client_reference_id") or "").strip()
    tier = _normalize_subscription_tier(metadata.get("subscription_tier"))
    billing_cycle = _normalize_billing_cycle(metadata.get("billing_cycle"))
    plan_id = str(metadata.get("plan_id") or "").strip()

    if not user_id or tier == "NONE":
        await _record_stripe_payment_event(event_id, STRIPE_CHECKOUT_COMPLETED, session, status="ignored")
        return

    try:
        object_id = ObjectId(user_id)
    except Exception:
        await _record_stripe_payment_event(event_id, STRIPE_CHECKOUT_COMPLETED, session, status="ignored")
        return

    user = await users_collection.find_one({"_id": object_id})
    if not user:
        await _record_stripe_payment_event(event_id, STRIPE_CHECKOUT_COMPLETED, session, status="ignored")
        return
    if str(user.get("subscription_purchase_source") or "").strip() == "beta_trial":
        await _record_stripe_payment_event(event_id, STRIPE_CHECKOUT_COMPLETED, session, status="ignored", user_id=user_id, tier=tier)
        return

    amount_total = session.get("amount_total")
    amount = (float(amount_total) / 100.0) if amount_total is not None else None
    now = datetime.now(timezone.utc)
    try:
        checkout_plan = await _resolve_subscription_checkout_plan(tier, billing_cycle, plan_id)
        feature_access = checkout_plan["feature_access"] if checkout_plan else _resolve_subscription_access(tier)
    except HTTPException:
        feature_access = _resolve_subscription_access(tier)
    update_doc = _build_active_subscription_doc(
        existing_user=user,
        tier=tier,
        billing_cycle=billing_cycle,
        now=now,
        plan_id=plan_id,
        amount=amount,
        feature_access=feature_access,
        stripe_customer_id=str(session.get("customer") or user.get("stripe_customer_id") or ""),
        stripe_subscription_id=str(session.get("subscription") or ""),
    )

    await users_collection.update_one({"_id": object_id}, {"$set": update_doc})
    updated_user = await users_collection.find_one({"_id": object_id})
    if updated_user:
        await notify_user(
            users_collection,
            updated_user,
            f"{tier.title().replace('_', ' ')} plan activated",
            "Your Victory Fitness plan is active and your included features are ready.",
            "subscription_activated",
            {"type": "subscription", "tier": tier, "route": "/profile"},
        )

    await _record_stripe_payment_event(
        event_id,
        STRIPE_CHECKOUT_COMPLETED,
        session,
        status="success",
        user_id=user_id,
        tier=tier,
        amount=amount,
        billing_cycle=billing_cycle,
    )


async def _handle_subscription_event(event_id: str, event_type: str, subscription: dict[str, Any]) -> None:
    metadata = subscription.get("metadata") if isinstance(subscription.get("metadata"), dict) else {}
    user_id = str(metadata.get("user_id") or "").strip()
    if not user_id:
        await _record_stripe_payment_event(event_id, event_type, subscription, status="ignored")
        return

    try:
        object_id = ObjectId(user_id)
    except Exception:
        await _record_stripe_payment_event(event_id, event_type, subscription, status="ignored")
        return

    stripe_status = str(subscription.get("status") or "").lower()
    existing_user = await users_collection.find_one({"_id": object_id})
    if existing_user and str(existing_user.get("subscription_purchase_source") or "").strip() == "beta_trial":
        await _record_stripe_payment_event(event_id, event_type, subscription, status="ignored", user_id=user_id)
        return
    if event_type == STRIPE_SUBSCRIPTION_DELETED or stripe_status in {"canceled", "unpaid", "incomplete_expired"}:
        await users_collection.update_one(
            {"_id": object_id, "stripe_subscription_id": str(subscription.get("id") or "")},
            {
                "$set": {
                    "subscription_status": "CANCELLED",
                    "subscription_is_purchased": False,
                    "subscription_purchase_source": "stripe",
                    "subscription_access": [],
                    "subscription.access": [],
                    "subscription.status": "CANCELLED",
                    "subscription.is_purchased": False,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    await _record_stripe_payment_event(event_id, event_type, subscription, status=stripe_status or "received", user_id=user_id)


def _build_active_subscription_doc(
    *,
    existing_user: dict,
    tier: str,
    billing_cycle: str,
    now: datetime,
    plan_id: str,
    amount: float | None,
    feature_access: list[str],
    stripe_customer_id: str,
    stripe_subscription_id: str,
) -> dict[str, Any]:
    update_doc: dict[str, Any] = {
        "subscription_tier": tier,
        "subscription_role": tier,
        "subscription_status": "ACTIVE",
        "subscription_billing_cycle": billing_cycle,
        "subscription_is_purchased": True,
        "subscription_purchase_source": "stripe",
        "subscription_plan_id": plan_id,
        "subscription_price_amount": amount,
        "subscription_access": feature_access,
        "subscription": {
            "tier": tier,
            "role": tier,
            "status": "ACTIVE",
            "billing_cycle": billing_cycle,
            "is_purchased": True,
            "purchase_source": "stripe",
            "access": feature_access,
            "started_at": existing_user.get("subscription_started_at") or now,
            "confirmed_at": now,
        },
        "subscription_confirmed_at": now,
        "subscription_started_at": existing_user.get("subscription_started_at") or now,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "updated_at": now,
    }
    trial_outcome = _trial_outcome_for_subscription(tier, True)
    if trial_outcome and existing_user.get("trial_start_at"):
        update_doc["trial_outcome"] = trial_outcome
        update_doc["trial_outcome_at"] = now
    return update_doc


async def _record_stripe_payment_event(
    event_id: str,
    event_type: str,
    obj: dict[str, Any],
    *,
    status: str,
    user_id: str | None = None,
    tier: str | None = None,
    amount: float | None = None,
    billing_cycle: str | None = None,
) -> None:
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    resolved_user_id = user_id or str(metadata.get("user_id") or obj.get("client_reference_id") or "").strip() or None
    resolved_tier = tier or str(metadata.get("subscription_tier") or "").strip().upper() or None
    amount_value = amount
    if amount_value is None and obj.get("amount_paid") is not None:
        amount_value = float(obj["amount_paid"]) / 100.0
    if amount_value is None and obj.get("amount_total") is not None:
        amount_value = float(obj["amount_total"]) / 100.0

    doc = {
        "stripe_event_id": event_id or None,
        "stripe_object_id": str(obj.get("id") or "") or None,
        "user_id": resolved_user_id,
        "amount": amount_value,
        "currency": str(obj.get("currency") or settings.stripe_currency).upper(),
        "type": event_type,
        "tier": resolved_tier,
        "billing_cycle": billing_cycle or str(metadata.get("billing_cycle") or ""),
        "market": None,
        "status": status,
        "created_at": datetime.now(timezone.utc),
    }
    await payment_events_collection.insert_one(doc)
    if resolved_user_id and status == "success":
        await _record_analytics_event(
            "payment_subscription_started",
            user_id=resolved_user_id,
            details={"amount": amount_value, "currency": doc["currency"], "tier": resolved_tier, "source": "stripe"},
        )
