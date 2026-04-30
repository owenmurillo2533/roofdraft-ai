"""
RoofDraftAI Stripe routes.
"""

import json
import os
import traceback

from flask import Blueprint, jsonify, request

from database.db import (
    get_user_by_stripe_customer_id,
    record_subscription_event,
    require_auth,
    update_user_subscription,
)
from extensions import limiter

stripe_bp = Blueprint("stripe", __name__)


def get_stripe_client():
    import stripe

    secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret_key:
        raise RuntimeError("Stripe is not configured")
    stripe.api_key = secret_key
    return stripe


@stripe_bp.route("/api/stripe/create-checkout-session", methods=["POST"])
@limiter.limit("20 per hour")
def create_checkout_session():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        stripe = get_stripe_client()
        data = request.get_json() or {}
        plan = (data.get("plan") or "pro").strip().lower() or "pro"
        price_id_map = {
            "starter": os.environ.get("STRIPE_STARTER_PRICE_ID", ""),
            "pro": os.environ.get("STRIPE_PRO_PRICE_ID", ""),
        }
        price_id = price_id_map.get(plan) or price_id_map.get("pro")
        if not price_id:
            return jsonify({"error": "Could not create checkout session. Please try again."}), 500

        domain = os.environ.get("YOUR_DOMAIN", "https://roofdraftai.com").rstrip("/")
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=user["email"],
            allow_promotion_codes=True,
            metadata={"user_id": str(user["id"]), "plan": plan},
            subscription_data={"trial_period_days": 7},
            success_url=f"{domain}/dashboard?upgrade=success&plan={plan}",
            cancel_url=f"{domain}/?upgrade=cancelled",
        )
        return jsonify({"checkout_url": session.url})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not create checkout session. Please try again."}), 500


@stripe_bp.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    try:
        stripe = get_stripe_client()
        payload = request.get_data()
        signature = request.headers.get("Stripe-Signature", "")
        webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

        if webhook_secret:
            try:
                event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
            except Exception:
                return jsonify({"error": "Invalid signature"}), 400
        else:
            event = json.loads(payload.decode("utf-8"))

        event_type = event.get("type", "")
        event_id = event.get("id")
        data_object = (event.get("data") or {}).get("object") or {}

        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata") or {}
            user_id = metadata.get("user_id")
            plan = (metadata.get("plan") or "pro").strip().lower() or "pro"
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")
            if user_id:
                update_user_subscription(
                    int(user_id),
                    plan=plan,
                    stripe_customer_id=customer_id,
                    subscription_id=subscription_id,
                    subscription_status="active",
                )
                record_subscription_event(int(user_id), event_type, plan, event_id)

        elif event_type == "customer.subscription.deleted":
            customer_id = data_object.get("customer")
            user = get_user_by_stripe_customer_id(customer_id)
            if user:
                update_user_subscription(
                    user["id"],
                    plan="free",
                    subscription_id=data_object.get("id"),
                    subscription_status="cancelled",
                )
                record_subscription_event(user["id"], event_type, "free", event_id)

        elif event_type == "customer.subscription.updated":
            customer_id = data_object.get("customer")
            user = get_user_by_stripe_customer_id(customer_id)
            if user:
                status = data_object.get("status")
                update_user_subscription(
                    user["id"],
                    subscription_id=data_object.get("id"),
                    subscription_status=status,
                )
                record_subscription_event(user["id"], event_type, user.get("plan"), event_id)

        return jsonify({"received": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"received": True})


@stripe_bp.route("/api/stripe/create-portal-session", methods=["POST"])
def create_portal_session():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        if not user.get("stripe_customer_id"):
            return jsonify({"error": "No active subscription found"}), 400

        stripe = get_stripe_client()
        domain = os.environ.get("YOUR_DOMAIN", "https://roofdraftai.com").rstrip("/")
        session = stripe.billing_portal.Session.create(
            customer=user["stripe_customer_id"],
            return_url=f"{domain}/dashboard",
        )
        return jsonify({"portal_url": session.url})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Could not open billing portal. Please contact support."}), 500
