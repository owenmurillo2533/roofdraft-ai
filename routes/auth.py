"""
RoofDraft AI — Auth Routes
"""
from flask import Blueprint, request, jsonify
from datetime import datetime
from database.db import (
    hash_password, verify_password, generate_token,
    USE_POSTGRES, pg_run, get_db, row_to_dict,
    create_user, create_session, get_user_by_token,
    maybe_reset_monthly_count
)

auth_bp = Blueprint('auth', __name__)


def _user_response(user):
    return {
        "id": user['id'],
        "email": user['email'],
        "username": user['username'],
        "plan": user.get('plan', 'free'),
        "generations_this_month": user.get('generations_this_month', 0),
        "is_admin": bool(user.get('is_admin', False)),
    }


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not email or not username or not password:
        return jsonify({"error": "Email, username and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400

    try:
        # Check duplicates
        if USE_POSTGRES:
            existing = pg_run(
                "SELECT id FROM users WHERE email=$1 OR username=$2",
                [email, username]
            )
        else:
            conn = get_db()
            existing = conn.execute(
                "SELECT id FROM users WHERE email=? OR username=?",
                (email, username)
            ).fetchone()
            conn.close()

        if existing:
            return jsonify({"error": "Email or username already taken"}), 409

        user_id = create_user(email, username, password)
        token = create_session(user_id)

        current_month = datetime.now().strftime('%Y-%m')
        user = {
            'id': user_id,
            'email': email,
            'username': username,
            'plan': 'free',
            'generations_this_month': 0,
            'is_admin': False,
        }
        return jsonify({"token": token, "user": _user_response(user)}), 201

    except Exception as e:
        print(f"[Register] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Registration failed — please try again"}), 500


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        if USE_POSTGRES:
            rows = pg_run(
                "SELECT id, email, username, password_hash, plan, generations_this_month, is_admin "
                "FROM users WHERE email=$1 AND is_active=TRUE",
                [email]
            )
            if not rows or not verify_password(password, rows[0]['password_hash']):
                return jsonify({"error": "Invalid email or password"}), 401
            user = rows[0]
        else:
            conn = get_db()
            row = conn.execute(
                "SELECT id, email, username, password_hash, plan, generations_this_month, is_admin "
                "FROM users WHERE email=? AND is_active=1",
                (email,)
            ).fetchone()
            conn.close()
            if not row or not verify_password(password, row['password_hash']):
                return jsonify({"error": "Invalid email or password"}), 401
            user = row_to_dict(row)

        # Reset monthly count if we're in a new month
        current_month = datetime.now().strftime('%Y-%m')
        maybe_reset_monthly_count(user['id'], current_month)

        token = create_session(user['id'])

        # Re-fetch user to get fresh count after potential reset
        if USE_POSTGRES:
            fresh = pg_run(
                "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=$1",
                [user['id']]
            )
            user = fresh[0] if fresh else user
        else:
            conn = get_db()
            row = conn.execute(
                "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=?",
                (user['id'],)
            ).fetchone()
            conn.close()
            if row:
                user = row_to_dict(row)

        return jsonify({"token": token, "user": _user_response(user)})

    except Exception as e:
        print(f"[Login] Error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Login failed — please try again"}), 500


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        try:
            if USE_POSTGRES:
                pg_run("DELETE FROM sessions WHERE token=$1", [token])
            else:
                conn = get_db()
                conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                conn.commit()
                conn.close()
        except Exception:
            pass
    return jsonify({"success": True})


@auth_bp.route('/api/auth/me', methods=['GET'])
def me():
    from database.db import require_auth
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    # Reset monthly count if new month
    current_month = datetime.now().strftime('%Y-%m')
    maybe_reset_monthly_count(user['id'], current_month)

    # Re-fetch fresh data
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=$1",
            [user['id']]
        )
        user = rows[0] if rows else user
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=?",
            (user['id'],)
        ).fetchone()
        conn.close()
        if row:
            user = row_to_dict(row)

    return jsonify(_user_response(user))
