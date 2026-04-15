"""
RoofDraft — Stripe Routes
Handles checkout session creation and webhook processing.
"""
import os
import json
import stripe
from flask import Blueprint, request, jsonify
from database.db import require_auth, USE_POSTGRES, pg_run, get_db

stripe_bp = Blueprint('stripe', __name__)

STARTER_PRICE_ID = os.environ.get('STRIPE_STARTER_PRICE_ID', '')
PRO_PRICE_ID     = os.environ.get('STRIPE_PRO_PRICE_ID', '')
DOMAIN           = os.environ.get('YOUR_DOMAIN', 'https://roofdraftai.com')

PLAN_PRICES = {
    'starter': STARTER_PRICE_ID,
    'pro':     PRO_PRICE_ID,
}


def _get_stripe():
    key = os.environ.get('STRIPE_SECRET_KEY', '')
    if not key:
        return None
    stripe.api_key = key
    return stripe


@stripe_bp.route('/api/stripe/create-checkout-session', methods=['POST'])
def create_checkout_session():
    user = require_auth()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    s = _get_stripe()
    if not s:
        return jsonify({'error': 'Payments not configured'}), 503

    data = request.get_json() or {}
    plan = (data.get('plan') or '').strip().lower()

    if plan not in PLAN_PRICES:
        return jsonify({'error': 'Invalid plan. Must be starter or pro.'}), 400

    price_id = PLAN_PRICES[plan]
    if not price_id:
        return jsonify({'error': f'{plan.capitalize()} plan price not configured on server'}), 503

    try:
        session = s.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=f'{DOMAIN}/?checkout=success&plan={plan}',
            cancel_url=f'{DOMAIN}/?checkout=cancelled',
            customer_email=user['email'],
            client_reference_id=str(user['id']),
            metadata={'user_id': str(user['id']), 'plan': plan},
        )
        return jsonify({'url': session.url})
    except Exception as e:
        print(f'[Stripe] create-checkout-session error: {e}')
        import traceback; traceback.print_exc()
        return jsonify({'error': 'Failed to create checkout session — please try again'}), 500


@stripe_bp.route('/api/stripe/webhook', methods=['POST'])
def webhook():
    s = _get_stripe()
    if not s:
        return jsonify({'error': 'Stripe not configured'}), 503

    payload        = request.get_data()
    sig_header     = request.headers.get('Stripe-Signature', '')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    if not webhook_secret:
        print('[Stripe] STRIPE_WEBHOOK_SECRET not set — rejecting webhook')
        return jsonify({'error': 'Webhook not configured'}), 503

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        print(f'[Stripe] Webhook signature error: {e}')
        return jsonify({'error': 'Invalid signature'}), 400

    event_type = event.get('type', '')
    print(f'[Stripe] Webhook received: {event_type}')

    if event_type == 'checkout.session.completed':
        session  = event['data']['object']
        user_id  = session.get('client_reference_id')
        metadata = session.get('metadata') or {}
        plan     = metadata.get('plan', 'starter')
        if plan not in ('starter', 'pro'):
            plan = 'starter'

        if user_id:
            try:
                if USE_POSTGRES:
                    pg_run('UPDATE users SET plan=$1 WHERE id=$2', [plan, int(user_id)])
                else:
                    conn = get_db()
                    conn.execute('UPDATE users SET plan=? WHERE id=?', (plan, int(user_id)))
                    conn.commit()
                    conn.close()
                print(f'[Stripe] Upgraded user {user_id} to plan: {plan}')
            except Exception as e:
                print(f'[Stripe] Failed to update plan for user {user_id}: {e}')
                import traceback; traceback.print_exc()
        else:
            print('[Stripe] checkout.session.completed missing client_reference_id')

    elif event_type in ('customer.subscription.deleted', 'customer.subscription.updated'):
        # Future: handle cancellations / downgrades via subscription events
        print(f'[Stripe] Subscription event (unhandled): {event_type}')

    return jsonify({'received': True})
