"""
RoofDraftAI job folders routes.
Pro plan only.
"""

import traceback

from flask import Blueprint, jsonify, request

from database.db import create_folder, delete_folder, get_folders, require_auth, update_folder

folders_bp = Blueprint("folders", __name__)

PRO_MESSAGE = "Job folders are available on the Pro plan. Upgrade to access this feature."


def require_pro_user():
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not (bool(user.get("is_admin")) or user.get("plan") == "pro"):
        return None, (jsonify({"error": PRO_MESSAGE}), 403)
    return user, None


@folders_bp.route("/api/folders", methods=["GET"])
def list_folders():
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        return jsonify({"folders": get_folders(user["id"]) or []})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@folders_bp.route("/api/folders", methods=["POST"])
def create_new_folder():
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        data = request.get_json() or {}
        name = str(data.get("name") or "").strip()[:255]
        color = str(data.get("color") or "#C0392B").strip()[:7] or "#C0392B"
        if not name:
            return jsonify({"error": "Folder name is required"}), 400
        folder = create_folder(user["id"], name, color)
        return jsonify({"folder": folder}), 201
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@folders_bp.route("/api/folders/<int:folder_id>", methods=["PATCH"])
def rename_folder(folder_id):
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        data = request.get_json() or {}
        name = str(data.get("name") or "").strip()[:255]
        if not name:
            return jsonify({"error": "Folder name is required"}), 400
        folder = update_folder(user["id"], folder_id, name)
        return jsonify({"folder": folder})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@folders_bp.route("/api/folders/<int:folder_id>", methods=["DELETE"])
def remove_folder(folder_id):
    try:
        user, error_response = require_pro_user()
        if error_response:
            return error_response
        delete_folder(user["id"], folder_id)
        return jsonify({"success": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
