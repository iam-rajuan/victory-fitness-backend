# Stripe Subscription Payments

The backend uses Stripe Checkout for subscription payment collection and a
Stripe webhook to activate the user's subscription after Stripe confirms
payment.

## Environment

Set these in `victory-fitness-backend/.env` and in production:

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CURRENCY=eur
STRIPE_CHECKOUT_SUCCESS_URL=http://localhost:8081/plan?checkout=success
STRIPE_CHECKOUT_CANCEL_URL=http://localhost:8081/plan?checkout=cancelled
```

For production, use the deployed app URLs for success and cancel.

## Local Webhook Testing

Run the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Forward Stripe webhooks to the backend:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Copy the `whsec_...` value printed by the Stripe CLI into
`STRIPE_WEBHOOK_SECRET`, then restart the backend.

## Flow

1. The app calls `POST /payments/stripe/checkout-session`.
2. Backend creates a Stripe Checkout Session in subscription mode.
3. The app opens the returned `checkout_url`.
4. Stripe sends `checkout.session.completed` to `/webhooks/stripe`.
5. Backend marks the user subscription active and stores Stripe IDs.

The webhook is the source of truth. Do not activate paid subscriptions directly
from the client.
