"""
RoofDraft — Contact Route
Public endpoint — no auth required.
"""
import re
from flask import Blueprint, request, jsonify
from database.db import save_contact_message

contact_bp = Blueprint('contact', __name__)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@contact_bp.route('/api/contact', methods=['POST'])
def submit_contact():
    data = request.get_json() or {}
    name    = (data.get('name') or '').strip()[:255]
    email   = (data.get('email') or '').strip().lower()[:255]
    message = (data.get('message') or '').strip()[:5000]

    if not name or not email or not message:
        return jsonify({"error": "Name, email, and message are required"}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400

    try:
        save_contact_message(name, email, message)
        return jsonify({"ok": True})
    except Exception as e:
        print(f"[Contact] Error saving message: {e}")
        return jsonify({"error": "Failed to save message"}), 500
