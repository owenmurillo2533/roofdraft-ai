"""
RoofDraftAI contact routes.
"""

import re
import traceback

from flask import Blueprint, jsonify, request

from database.db import save_contact_message
from extensions import limiter

contact_bp = Blueprint("contact", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@contact_bp.route("/api/contact", methods=["POST"])
@limiter.limit("5 per hour")
def submit_contact():
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        message = (data.get("message") or "").strip()

        if not name or not email or not message:
            return jsonify({"error": "Name, email, and message are required"}), 400
        if not EMAIL_RE.match(email):
            return jsonify({"error": "Please enter a valid email address"}), 400

        save_contact_message(name, email, message)
        return jsonify({"success": True}), 201
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
