"""
RoofDraftAI drafts routes.
Pro plan only.
"""

import traceback

from flask import Blueprint, jsonify, request

from database.db import delete_draft, get_draft_by_id, get_drafts, move_draft, require_auth, save_draft

drafts_bp = Blueprint("drafts", __name__)

PRO_MESSAGE = "Job folders are available on the Pro plan. Upgrade to access this feature."


def require_pro_user():
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not (bool(user.get("is_admin")) or user.get("plan") == "pro"):
        return None, (jsonify({"error": PRO_MESSAGE}), 403)
    return user, None


@drafts_bp.route("/api/drafts", methods=["GET"])
def list_drafts():
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        folder_id = request.args.get("folder_id")
        if folder_id not in (None, ""):
            try:
                folder_id = int(folder_id)
            except (ValueError, TypeError):
                folder_id = None
        drafts = get_drafts(user["id"], folder_id=folder_id)
        return jsonify({"drafts": drafts or []})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@drafts_bp.route("/api/drafts", methods=["POST"])
def create_draft():
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        data = request.get_json() or {}
        tool_name = str(data.get("tool_name") or "").strip()[:100]
        title = str(data.get("title") or "").strip()[:255]
        content = str(data.get("content") or "").strip()
        source_data = data.get("source_data") if isinstance(data.get("source_data"), dict) else {}
        folder_id = data.get("folder_id")
        if folder_id not in (None, ""):
            try:
                folder_id = int(folder_id)
            except (ValueError, TypeError):
                folder_id = None
        else:
            folder_id = None
        if not tool_name or not title or not content:
            return jsonify({"error": "tool_name, title, and content are required"}), 400
        draft = save_draft(user["id"], tool_name, title, content, folder_id, source_data=source_data)
        return jsonify({"draft": draft}), 201
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@drafts_bp.route("/api/drafts/<int:draft_id>", methods=["GET"])
def get_draft(draft_id):
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        draft = get_draft_by_id(user["id"], draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404
        return jsonify({"draft": draft})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@drafts_bp.route("/api/drafts/<int:draft_id>", methods=["PATCH"])
def update_draft(draft_id):
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        data = request.get_json() or {}
        folder_id = data.get("folder_id", "__unset__")
        title = data.get("title")
        if folder_id not in ("__unset__", None, ""):
            try:
                folder_id = int(folder_id)
            except (ValueError, TypeError):
                folder_id = None
        elif folder_id in ("", None):
            folder_id = None
        if title is not None:
            title = str(title).strip()[:255]
        move_draft(user["id"], draft_id, folder_id=folder_id, title=title)
        draft = get_draft_by_id(user["id"], draft_id)
        return jsonify({"draft": draft})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@drafts_bp.route("/api/drafts/<int:draft_id>", methods=["DELETE"])
def remove_draft(draft_id):
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        delete_draft(user["id"], draft_id)
        return jsonify({"success": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
