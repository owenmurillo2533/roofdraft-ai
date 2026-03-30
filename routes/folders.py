"""
RoofDraft AI — Job Folders Routes
Pro plan only.
"""
from flask import Blueprint, request, jsonify
from database.db import require_auth, get_folders, create_folder, update_folder, delete_folder

folders_bp = Blueprint('folders', __name__)

PRO_PLANS = {'pro'}


def require_pro():
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not (bool(user.get('is_admin')) or user.get('plan', 'free') in PRO_PLANS):
        return None, (jsonify({"error": "Job folders are available on the Pro plan"}), 403)
    return user, None


@folders_bp.route('/api/folders', methods=['GET'])
def list_folders():
    user, err = require_pro()
    if err:
        return err
    folders = get_folders(user['id'])
    return jsonify({"folders": folders})


@folders_bp.route('/api/folders', methods=['POST'])
def new_folder():
    user, err = require_pro()
    if err:
        return err
    data = request.get_json() or {}
    name = str(data.get('name', '')).strip()[:255]
    color = str(data.get('color', '#C0392B')).strip()[:7]
    if not name:
        return jsonify({"error": "Folder name is required"}), 400
    folder_id = create_folder(user['id'], name, color)
    return jsonify({"folder": {"id": folder_id, "name": name, "color": color, "draft_count": 0}})


@folders_bp.route('/api/folders/<int:folder_id>', methods=['PATCH'])
def rename_folder(folder_id):
    user, err = require_pro()
    if err:
        return err
    data = request.get_json() or {}
    name = str(data.get('name', '')).strip()[:255]
    if not name:
        return jsonify({"error": "Folder name is required"}), 400
    update_folder(user['id'], folder_id, name)
    return jsonify({"ok": True})


@folders_bp.route('/api/folders/<int:folder_id>', methods=['DELETE'])
def remove_folder(folder_id):
    user, err = require_pro()
    if err:
        return err
    delete_folder(user['id'], folder_id)
    return jsonify({"ok": True})
