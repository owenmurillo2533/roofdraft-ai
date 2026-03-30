"""
RoofDraft AI — Drafts Routes
Saved generations for paying customers. Job folder features are Pro-only.
"""
from flask import Blueprint, jsonify, request
from database.db import (
    require_auth, get_drafts, get_draft_by_id, delete_draft,
    save_draft, move_draft
)

drafts_bp = Blueprint('drafts', __name__)

PAYING_PLANS = {'starter', 'pro'}
PRO_PLANS = {'pro'}


def require_paying(user):
    return bool(user.get('is_admin')) or user.get('plan', 'free') in PAYING_PLANS


def require_pro(user):
    return bool(user.get('is_admin')) or user.get('plan', 'free') in PRO_PLANS


@drafts_bp.route('/api/drafts', methods=['GET'])
def list_drafts():
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_paying(user):
        return jsonify({"error": "Saved drafts require a paid plan"}), 403

    folder_id = request.args.get('folder_id')
    if folder_id is not None:
        try:
            folder_id = int(folder_id)
        except (ValueError, TypeError):
            folder_id = None

    drafts = get_drafts(user['id'], folder_id=folder_id)
    for d in drafts:
        if d.get('created_at') and not isinstance(d['created_at'], str):
            d['created_at'] = d['created_at'].isoformat()
    return jsonify({"drafts": drafts})


@drafts_bp.route('/api/drafts', methods=['POST'])
def create_draft():
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_pro(user):
        return jsonify({"error": "Job folders are available on the Pro plan"}), 403

    data = request.get_json() or {}
    tool_name = str(data.get('tool_name', '')).strip()[:100]
    title = str(data.get('title', 'Untitled')).strip()[:255]
    content = str(data.get('content', '')).strip()
    folder_id = data.get('folder_id')
    if folder_id is not None:
        try:
            folder_id = int(folder_id)
        except (ValueError, TypeError):
            folder_id = None

    if not content:
        return jsonify({"error": "Content is required"}), 400

    draft_id = save_draft(user['id'], tool_name, title, content, folder_id)
    return jsonify({"draft": {"id": draft_id, "title": title, "tool_name": tool_name, "folder_id": folder_id}})


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


@drafts_bp.route('/api/drafts/<int:draft_id>', methods=['PATCH'])
def update_draft(draft_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_pro(user):
        return jsonify({"error": "Job folders are available on the Pro plan"}), 403

    data = request.get_json() or {}
    folder_id = data.get('folder_id', '__unset__')
    title = data.get('title')

    # Convert folder_id: None means unfile, int means assign, '__unset__' means don't change
    if folder_id != '__unset__' and folder_id is not None:
        try:
            folder_id = int(folder_id)
        except (ValueError, TypeError):
            folder_id = None

    if title is not None:
        title = str(title).strip()[:255]

    move_draft(user['id'], draft_id, folder_id=folder_id, title=title)
    return jsonify({"ok": True})


@drafts_bp.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
def remove_draft(draft_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    if not require_paying(user):
        return jsonify({"error": "Saved drafts require a paid plan"}), 403

    delete_draft(user['id'], draft_id)
    return jsonify({"ok": True})
