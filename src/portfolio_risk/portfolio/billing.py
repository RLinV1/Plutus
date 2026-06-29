"""Subscription plans, daily prompt quotas, and Stripe billing.

Two concerns live here:

1. **Quotas** (always on): each Clerk user gets N AI prompts per UTC day based on
   their plan (free=5, pro=10, pro_max=20 by default). ``consume`` atomically
   increments the day's counter when under the limit; ``status`` reports usage.

2. **Stripe** (only when ``STRIPE_SECRET_KEY`` is set): Checkout to subscribe,
   the billing portal to manage/cancel, and a webhook that maps Stripe
   subscription events back onto the user's plan.

The ``anonymous`` user (local dev without Clerk) is never rate-limited.

IMPORTANT: never print to stdout — imported indirectly by the stdio MCP server.
Log to stderr only.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from .. import config
from .db import PromptUsageModel, UserPlanModel, session

log = logging.getLogger("portfolio_risk.portfolio.billing")
if not log.handlers:  # stderr only
    _h = logging.StreamHandler(stream=sys.stderr)
    _h.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)

_ACTIVE = ("active", "trialing")


class BillingError(Exception):
    """Raised for misconfiguration or Stripe failures (mapped to HTTP by routes)."""


def _today():
    return datetime.now(timezone.utc).date()


def _quota_exempt_dev(user_id: str) -> bool:
    """True only for the unauthenticated dev/test identity when auth is OFF.

    With auth ENABLED (production) this is always False — 'anonymous' can't even
    occur (api/auth.py returns 401 without a valid token), and if it somehow did
    it would be treated as a normal limited user. The quota fails closed.
    """
    return user_id == "anonymous" and not config.auth_enabled()


# --------------------------------------------------------------------------- #
# Plans + quota
# --------------------------------------------------------------------------- #
def get_plan(user_id: str) -> str:
    """The user's effective plan.

    'unlimited' when the user is in ``UNLIMITED_USER_IDS`` or has an 'unlimited'
    DB plan (admin-comped); otherwise their active paid plan; else 'free'.
    """
    if user_id in config.unlimited_user_ids():
        return "unlimited"
    with session() as s:
        row = s.query(UserPlanModel).filter_by(clerk_user_id=user_id).one_or_none()
        if row and row.status in _ACTIVE:
            if row.plan == "unlimited" or row.plan in config.plan_limits():
                return row.plan
    return "free"


def is_unlimited(user_id: str) -> bool:
    """Whether the user bypasses the daily quota (admin / comped / local dev)."""
    return _quota_exempt_dev(user_id) or get_plan(user_id) == "unlimited"


def limit_for(plan: str) -> int:
    limits = config.plan_limits()
    return limits.get(plan, limits["free"])


def _usage_today(user_id: str) -> int:
    with session() as s:
        row = (
            s.query(PromptUsageModel)
            .filter_by(clerk_user_id=user_id, day=_today())
            .one_or_none()
        )
        return row.count if row else 0


def get_status(user_id: str) -> dict:
    """Plan, today's usage, limit, and remaining — for the UI (no increment)."""
    plan = get_plan(user_id)
    unlimited = _quota_exempt_dev(user_id) or plan == "unlimited"
    if unlimited:
        return {
            "plan": plan,
            "used": 0,
            "limit": 0,
            "remaining": 0,
            "unlimited": True,
        }
    limit = limit_for(plan)
    used = _usage_today(user_id)
    return {
        "plan": plan,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "unlimited": False,
    }


def consume(user_id: str) -> dict:
    """Atomically consume one prompt if under the daily limit.

    Returns ``{allowed, plan, used, limit, remaining}``. The ``anonymous`` user
    (local dev / tests, no Clerk) is always allowed and never counted.
    """
    plan = get_plan(user_id)
    if _quota_exempt_dev(user_id) or plan == "unlimited":
        return {
            "allowed": True,
            "plan": plan,
            "used": 0,
            "limit": 0,
            "remaining": 0,
            "unlimited": True,
        }

    limit = limit_for(plan)
    today = _today()
    with session() as s:
        is_pg = s.get_bind().dialect.name == "postgresql"

        def _row():
            # SELECT ... FOR UPDATE locks the row on Postgres so concurrent
            # requests serialize and can't burst past the limit. SQLite serializes
            # writers itself (WAL + busy_timeout), so the lock isn't needed there.
            q = s.query(PromptUsageModel).filter_by(clerk_user_id=user_id, day=today)
            return (q.with_for_update().one_or_none() if is_pg else q.one_or_none())

        row = _row()
        if row is None:
            # First prompt of the day. Insert inside a savepoint so a concurrent
            # insert (unique day index) loses the race cleanly, then re-read it
            # under the lock instead of erroring.
            try:
                with s.begin_nested():
                    row = PromptUsageModel(clerk_user_id=user_id, day=today, count=0)
                    s.add(row)
                    s.flush()
            except IntegrityError:
                row = _row()

        used = row.count if row else 0
        if used >= limit:
            return {
                "allowed": False,
                "plan": plan,
                "used": used,
                "limit": limit,
                "remaining": 0,
            }
        row.count = used + 1
        return {
            "allowed": True,
            "plan": plan,
            "used": row.count,
            "limit": limit,
            "remaining": max(0, limit - row.count),
        }


def set_plan(
    user_id: str,
    plan: str,
    *,
    status: str = "active",
    customer_id: str | None = None,
    subscription_id: str | None = None,
    period_end: datetime | None = None,
) -> None:
    """Upsert the user's plan row (used by the Stripe webhook handlers)."""
    with session() as s:
        row = s.query(UserPlanModel).filter_by(clerk_user_id=user_id).one_or_none()
        if row is None:
            row = UserPlanModel(clerk_user_id=user_id)
            s.add(row)
        row.plan = plan
        row.status = status
        if customer_id:
            row.stripe_customer_id = customer_id
        if subscription_id is not None:
            row.stripe_subscription_id = subscription_id
        if period_end is not None:
            row.current_period_end = period_end


def _store_customer(user_id: str, customer_id: str) -> None:
    with session() as s:
        row = s.query(UserPlanModel).filter_by(clerk_user_id=user_id).one_or_none()
        if row is None:
            row = UserPlanModel(clerk_user_id=user_id, plan="free")
            s.add(row)
        row.stripe_customer_id = customer_id


def _customer_id(user_id: str) -> str | None:
    with session() as s:
        row = s.query(UserPlanModel).filter_by(clerk_user_id=user_id).one_or_none()
        return row.stripe_customer_id if row else None


def _user_for_customer(customer_id: str | None) -> str | None:
    if not customer_id:
        return None
    with session() as s:
        row = (
            s.query(UserPlanModel)
            .filter_by(stripe_customer_id=customer_id)
            .one_or_none()
        )
        return row.clerk_user_id if row else None


def _plan_for_price(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan, pid in config.stripe_price_ids().items():
        if pid and pid == price_id:
            return plan
    return None


# --------------------------------------------------------------------------- #
# Stripe
# --------------------------------------------------------------------------- #
def _stripe():
    key = config.stripe_secret_key()
    if not key:
        raise BillingError("Billing is not configured (no STRIPE_SECRET_KEY).")
    try:
        import stripe
    except ImportError as exc:  # pragma: no cover
        raise BillingError("The 'stripe' package is not installed.") from exc
    stripe.api_key = key
    return stripe


def _ensure_customer(user_id: str, stripe) -> str:
    existing = _customer_id(user_id)
    if existing:
        return existing
    cust = stripe.Customer.create(metadata={"clerk_user_id": user_id})
    _store_customer(user_id, cust.id)
    return cust.id


def create_checkout(user_id: str, plan: str) -> str:
    """Create a Stripe Checkout session and return its hosted URL."""
    price = config.stripe_price_ids().get(plan)
    if not price:
        raise BillingError(f"No Stripe price configured for plan '{plan}'.")
    stripe = _stripe()
    customer_id = _ensure_customer(user_id, stripe)
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price, "quantity": 1}],
        success_url=config.billing_success_url(),
        cancel_url=config.billing_cancel_url(),
        client_reference_id=user_id,
        metadata={"clerk_user_id": user_id, "plan": plan},
        subscription_data={"metadata": {"clerk_user_id": user_id, "plan": plan}},
        allow_promotion_codes=True,
    )
    return sess.url


def create_portal(user_id: str) -> str:
    """Create a Stripe billing-portal session so the user can manage/cancel."""
    stripe = _stripe()
    cid = _customer_id(user_id)
    if not cid:
        raise BillingError("No subscription to manage.")
    sess = stripe.billing_portal.Session.create(
        customer=cid, return_url=config.billing_cancel_url()
    )
    return sess.url


def _sync_subscription(sub: dict) -> None:
    """Reflect a Stripe subscription object onto the user's plan."""
    customer = sub.get("customer")
    user_id = _user_for_customer(customer) or (sub.get("metadata") or {}).get(
        "clerk_user_id"
    )
    if not user_id:
        log.warning("subscription %s has no resolvable user", sub.get("id"))
        return
    status = sub.get("status", "active")
    items = (sub.get("items") or {}).get("data") or []
    price_id = (items[0].get("price") or {}).get("id") if items else None
    plan = _plan_for_price(price_id) or (sub.get("metadata") or {}).get("plan", "free")
    period_end = sub.get("current_period_end")
    pe = (
        datetime.fromtimestamp(period_end, tz=timezone.utc).replace(tzinfo=None)
        if period_end
        else None
    )
    active = status in _ACTIVE
    set_plan(
        user_id,
        plan if active else "free",
        status=status,
        customer_id=customer,
        subscription_id=sub.get("id"),
        period_end=pe,
    )


def handle_webhook(payload: bytes, sig_header: str) -> None:
    """Verify (when a webhook secret is set) and process a Stripe event."""
    stripe = _stripe()
    secret = config.stripe_webhook_secret()
    if secret:
        # Verify the signature (raises on tampering / wrong secret). We discard
        # the returned StripeObject and re-parse the raw payload as plain dicts
        # below: newer stripe-python StripeObjects don't support ``.get()``, so
        # accessing fields off them raises ``AttributeError: get``.
        try:
            stripe.Webhook.construct_event(payload, sig_header, secret)
        except Exception as exc:  # noqa: BLE001 - signature/parse failures
            raise BillingError(f"Webhook signature verification failed: {exc}") from exc
    else:
        log.warning("processing Stripe webhook WITHOUT signature verification")

    # Operate on plain dicts so field access works regardless of stripe-python
    # version (the signature is already verified above when a secret is set).
    event = json.loads(payload)
    typ = event["type"]
    obj = event["data"]["object"]

    if typ == "checkout.session.completed":
        user_id = obj.get("client_reference_id") or (obj.get("metadata") or {}).get(
            "clerk_user_id"
        )
        plan = (obj.get("metadata") or {}).get("plan", "pro")
        if user_id:
            set_plan(
                user_id,
                plan,
                status="active",
                customer_id=obj.get("customer"),
                subscription_id=obj.get("subscription"),
            )
    elif typ in ("customer.subscription.created", "customer.subscription.updated"):
        _sync_subscription(obj)
    elif typ == "customer.subscription.deleted":
        user_id = _user_for_customer(obj.get("customer")) or (
            obj.get("metadata") or {}
        ).get("clerk_user_id")
        if user_id:
            set_plan(user_id, "free", status="canceled", subscription_id=None)
    else:
        log.info("ignoring Stripe event: %s", typ)
