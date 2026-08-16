from fastapi import APIRouter, Depends, Request

from ...core.legacy import _require_access_user
from ...models import (
    StripeCheckoutSessionRequest,
    StripeCheckoutSessionResponse,
    StripeWebhookResponse,
)
from ...services.stripe_payments import (
    construct_stripe_event,
    create_subscription_checkout_session,
    handle_stripe_event,
)


router = APIRouter()


@router.post("/payments/stripe/checkout-session", response_model=StripeCheckoutSessionResponse)
async def create_stripe_checkout_session(
    payload: StripeCheckoutSessionRequest,
    user: dict = Depends(_require_access_user),
) -> StripeCheckoutSessionResponse:
    return await create_subscription_checkout_session(user, payload)


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
async def stripe_webhook(request: Request) -> StripeWebhookResponse:
    event = await construct_stripe_event(request)
    await handle_stripe_event(event)
    return StripeWebhookResponse(received=True)
