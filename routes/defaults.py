"""
RoofDraftAI user defaults routes.
Starter and Pro plans only.
"""

import traceback

from flask import Blueprint, jsonify, request

from database.db import get_defaults, require_auth, save_defaults

defaults_bp = Blueprint("defaults", __name__)

PAYING_PLANS = {"starter", "pro"}
ALLOWED_FIELDS = {
    "company_name",
    "contractor_name",
    "contractor_phone",
    "contractor_email",
    "company_website",
    "service_area",
    "company_address",
    "license_number",
    "warranty_labor",
    "warranty_materials",
    "default_warranty_notes",
    "payment_terms",
    "default_financing_note",
    "default_cleanup_language",
    "default_proposal_tone",
    "default_weather_delay_note",
    "completion_days",
    "review_link",
    "common_materials",
}


def is_paying(user):
    return bool(user.get("is_admin")) or user.get("plan", "free") in PAYING_PLANS


@defaults_bp.route("/api/defaults", methods=["GET"])
def get_user_defaults():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify({"defaults": get_defaults(user["id"]) or {}})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@defaults_bp.route("/api/defaults", methods=["POST"])
def save_user_defaults():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        if not is_paying(user):
            return jsonify({"error": "Saved defaults require a Starter or Pro plan"}), 403

        payload = request.get_json() or {}
        filtered = {key: value for key, value in payload.items() if key in ALLOWED_FIELDS}
        if "common_materials" in filtered:
            materials = filtered["common_materials"]
            if not isinstance(materials, list):
                filtered["common_materials"] = []
            else:
                filtered["common_materials"] = [str(item).strip()[:500] for item in materials[:5] if str(item).strip()]

        saved = save_defaults(user["id"], filtered)
        return jsonify({"defaults": saved})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
