"""
RoofDraft — Auth Routes
"""
import re
from flask import Blueprint, request, jsonify
from datetime import datetime

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
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


def _lookup_promo_code(code: str):
    """Return promo_codes row dict or None."""
    try:
        if USE_POSTGRES:
            rows = pg_run(
                "SELECT * FROM promo_codes WHERE code=$1 AND is_active=TRUE",
                [code]
            )
            return rows[0] if rows else None
        else:
            conn = get_db()
            row = conn.execute(
                "SELECT * FROM promo_codes WHERE code=? AND is_active=1",
                (code,)
            ).fetchone()
            conn.close()
            return row_to_dict(row)
    except Exception as e:
        print(f"[Promo] lookup error: {e}")
        return None


def _apply_promo_code(user_id: int, user_email: str, code: str):
    """
    Apply a promo code for a user. Returns (dict, status_code).
    dict has keys: ok, plan (if upgraded), message, user (optional).
    """
    if not code:
        return {"ok": False, "error": "No code provided"}, 400

    promo = _lookup_promo_code(code)
    if not promo:
        return {"ok": False, "error": "Invalid promo code"}, 400

    try:
        if promo['code_type'] == 'free_pro':
            # Upgrade user to pro
            if USE_POSTGRES:
                pg_run("UPDATE users SET plan='pro' WHERE id=$1", [user_id])
                # Increment uses
                pg_run("UPDATE promo_codes SET uses=uses+1 WHERE code=$1", [code])
                rows = pg_run(
                    "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=$1",
                    [user_id]
                )
                updated = rows[0] if rows else None
            else:
                conn = get_db()
                conn.execute("UPDATE users SET plan='pro' WHERE id=?", (user_id,))
                conn.execute("UPDATE promo_codes SET uses=uses+1 WHERE code=?", (code,))
                conn.commit()
                row = conn.execute(
                    "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=?",
                    (user_id,)
                ).fetchone()
                conn.close()
                updated = row_to_dict(row)

            return {
                "ok": True,
                "plan": "pro",
                "message": "free_pro",
                "user": _user_response(updated) if updated else None
            }, 200

        elif promo['code_type'] == 'affiliate':
            aff_email = promo.get('affiliate_email') or ''
            comm_pct = promo.get('commission_percent') or 0

            if USE_POSTGRES:
                # Set referred_by on user
                pg_run(
                    "UPDATE users SET referred_by_code=$1, affiliate_email=$2 WHERE id=$3",
                    [code, aff_email, user_id]
                )
                # Increment uses
                pg_run("UPDATE promo_codes SET uses=uses+1 WHERE code=$1", [code])
                # Insert affiliate_commissions row
                pg_run(
                    "INSERT INTO affiliate_commissions "
                    "(affiliate_email, referred_user_id, referred_user_email, promo_code, commission_percent, status) "
                    "VALUES ($1, $2, $3, $4, $5, 'pending')",
                    [aff_email, user_id, user_email, code, comm_pct]
                )
            else:
                conn = get_db()
                conn.execute(
                    "UPDATE users SET referred_by_code=?, affiliate_email=? WHERE id=?",
                    (code, aff_email, user_id)
                )
                conn.execute("UPDATE promo_codes SET uses=uses+1 WHERE code=?", (code,))
                conn.execute(
                    "INSERT INTO affiliate_commissions "
                    "(affiliate_email, referred_user_id, referred_user_email, promo_code, commission_percent, status) "
                    "VALUES (?, ?, ?, ?, ?, 'pending')",
                    (aff_email, user_id, user_email, code, comm_pct)
                )
                conn.commit()
                conn.close()

            return {
                "ok": True,
                "plan": None,
                "message": "affiliate",
            }, 200

        else:
            return {"ok": False, "error": "Unknown code type"}, 400

    except Exception as e:
        print(f"[Promo] apply error: {e}")
        import traceback; traceback.print_exc()
        return {"ok": False, "error": "Failed to apply promo code"}, 500


@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    promo_code = (data.get('promo_code') or '').strip().upper()

    if not email or not username or not password:
        return jsonify({"error": "Email, username and password are required"}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(username) > 50:
        return jsonify({"error": "Username must be 50 characters or less"}), 400

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

        user = {
            'id': user_id,
            'email': email,
            'username': username,
            'plan': 'free',
            'generations_this_month': 0,
            'is_admin': False,
        }

        promo_message = None
        if promo_code:
            promo_result, promo_status = _apply_promo_code(user_id, email, promo_code)
            if promo_result.get('ok'):
                if promo_result.get('message') == 'free_pro':
                    user['plan'] = 'pro'
                    promo_message = 'pro_applied'
                elif promo_result.get('message') == 'affiliate':
                    promo_message = 'affiliate_tracked'
            else:
                promo_message = 'invalid'

        return jsonify({
            "token": token,
            "user": _user_response(user),
            "promo_message": promo_message
        }), 201

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


@auth_bp.route('/api/auth/apply-promo', methods=['POST'])
def apply_promo():
    from database.db import require_auth
    user = require_auth()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json() or {}
    code = (data.get('code') or '').strip().upper()

    result, status = _apply_promo_code(user['id'], user['email'], code)

    if not result.get('ok'):
        return jsonify({"error": result.get('error', 'Invalid promo code')}), status

    # Re-fetch user to return updated data
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=$1",
            [user['id']]
        )
        updated = rows[0] if rows else user
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT id, email, username, plan, generations_this_month, is_admin FROM users WHERE id=?",
            (user['id'],)
        ).fetchone()
        conn.close()
        updated = row_to_dict(row) if row else user

    return jsonify({
        "user": _user_response(updated),
        "plan": updated.get('plan'),
        "message": result.get('message'),
    })
