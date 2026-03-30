"""
RoofDraft AI — User Defaults Routes
Saved company profile and proposal defaults for paying customers.
"""
from flask import Blueprint, request, jsonify
from database.db import require_auth, get_defaults, save_defaults

defaults_bp = Blueprint('defaults', __name__)

PAYING_PLANS = {'starter', 'pro'}


def is_paying(user):
    return bool(user.get('is_admin')) or user.get('plan', 'free') in PAYING_PLANS


@defaults_bp.route('/api/defaults', methods=['GET'])
def get_user_defaults():
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = get_defaults(user['id'])
    return jsonify({"defaults": data})


@defaults_bp.route('/api/defaults', methods=['POST'])
def save_user_defaults():
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not is_paying(user):
        return jsonify({"error": "Saved defaults require a Starter or Pro plan"}), 403

    new_data = request.get_json() or {}

    # Only allow known fields — no arbitrary data storage
    allowed = {
        'company_name', 'contractor_name', 'contractor_phone',
        'contractor_email', 'license_number', 'warranty_labor',
        'warranty_materials', 'payment_terms', 'completion_days',
        'common_materials',
    }
    filtered = {k: v for k, v in new_data.items() if k in allowed}

    # Validate common_materials is a list of strings, max 5
    if 'common_materials' in filtered:
        mats = filtered['common_materials']
        if not isinstance(mats, list):
            filtered['common_materials'] = []
        else:
            filtered['common_materials'] = [str(m)[:500] for m in mats[:5]]

    saved = save_defaults(user['id'], filtered)
    return jsonify({"defaults": saved})
