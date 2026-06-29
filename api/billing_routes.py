"""Billing + quota endpoints: usage status, Stripe checkout/portal, webhook.

All user-scoped routes resolve the caller via ``get_user_id`` (Clerk JWT). The
webhook is intentionally unauthenticated — it's verified by Stripe's signature.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from portfolio_risk import config
from portfolio_risk.portfolio import billing

from .auth import get_user_id

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/status")
def status(user_id: str = Depends(get_user_id)) -> dict:
    """Current plan, today's usage, and whether upgrades are purchasable."""
    st = billing.get_status(user_id)
    st["billing_enabled"] = config.billing_enabled()
    st["limits"] = config.plan_limits()
    return st


@router.post("/checkout")
def checkout(payload: dict, user_id: str = Depends(get_user_id)) -> dict:
    """Start a Stripe Checkout for a paid plan; returns the hosted URL."""
    plan = (payload or {}).get("plan", "")
    if plan not in ("pro", "pro_max"):
        raise HTTPException(status_code=400, detail="Invalid plan.")
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Sign in to upgrade.")
    try:
        return {"url": billing.create_checkout(user_id, plan)}
    except billing.BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/portal")
def portal(user_id: str = Depends(get_user_id)) -> dict:
    """Open the Stripe billing portal to manage/cancel a subscription."""
    if user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Sign in to manage billing.")
    try:
        return {"url": billing.create_portal(user_id)}
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    """Stripe subscription lifecycle events -> plan updates."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        billing.handle_webhook(payload, sig)
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"received": True}
