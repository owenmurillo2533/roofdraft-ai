"""
RoofDraft AI — Drafts Routes
Saved generations for paying customers.
"""
from flask import Blueprint, jsonify
from database.db import require_auth, get_drafts, get_draft_by_id, delete_draft

drafts_bp = Blueprint('drafts', __name__)

PAYING_PLANS = {'starter', 'pro'}


def require_paying(user):
    return bool(user.get('is_admin')) or user.get('plan', 'free') in PAYING_PLANS


@drafts_bp.route('/api/drafts', methods=['GET'])
def list_drafts():
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_paying(user):
        return jsonify({"error": "Saved drafts require a paid plan"}), 403

    drafts = get_drafts(user['id'])
    # Normalize datetime to string for JSON
    for d in drafts:
        if d.get('created_at') and not isinstance(d['created_at'], str):
            d['created_at'] = d['created_at'].isoformat()
    return jsonify({"drafts": drafts})


@drafts_bp.route('/api/drafts/<int:draft_id>', methods=['GET'])
def get_draft(draft_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_paying(user):
        return jsonify({"error": "Saved drafts require a paid plan"}), 403

    draft = get_draft_by_id(user['id'], draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    if draft.get('created_at') and not isinstance(draft['created_at'], str):
        draft['created_at'] = draft['created_at'].isoformat()
    return jsonify({"draft": draft})


@drafts_bp.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
def remove_draft(draft_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_paying(user):
        return jsonify({"error": "Saved drafts require a paid plan"}), 403

    delete_draft(user['id'], draft_id)
    return jsonify({"ok": True})
