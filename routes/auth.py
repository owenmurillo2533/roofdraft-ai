"""
RoofDraftAI auth routes.
"""

import re
import traceback
from datetime import datetime

from flask import Blueprint, jsonify, request

from database.db import (
    USE_POSTGRES,
    create_session,
    create_user,
    delete_session,
    get_db,
    get_total_generations,
    get_user_by_email,
    get_user_by_id,
    maybe_reset_monthly_count,
    pg_run,
    require_auth,
    row_to_dict,
    verify_password,
)
from extensions import limiter

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _user_response(user):
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "plan": user.get("plan", "free"),
        "is_admin": bool(user.get("is_admin")),
        "is_active": bool(user.get("is_active", True)),
        "generations_this_month": int(user.get("generations_this_month") or 0),
        "total_generations": int(user.get("total_generations") or 0),
        "promo_code_used": user.get("referred_by_code"),
        "stripe_customer_id": user.get("stripe_customer_id"),
        "subscription_id": user.get("subscription_id"),
        "subscription_status": user.get("subscription_status"),
    }


def _with_usage(user):
    enriched = dict(user)
    enriched["total_generations"] = get_total_generations(enriched["id"])
    return enriched


def _lookup_promo_code(code):
    if not code:
        return None
    if USE_POSTGRES:
        rows = pg_run("SELECT * FROM promo_codes WHERE code=$1 AND is_active=TRUE", [code])
        return rows[0] if rows else None

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM promo_codes WHERE code=? AND is_active=1",
        (code,),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def _apply_promo_code(user_id, user_email, code):
    promo = _lookup_promo_code(code)
    if not promo:
        return {"ok": False, "error": "Invalid promo code"}, 400

    try:
        if promo["code_type"] == "free_pro":
            if USE_POSTGRES:
                pg_run(
                    "UPDATE users SET plan='pro', referred_by_code=$1 WHERE id=$2",
                    [code, user_id],
                )
                pg_run("UPDATE promo_codes SET uses=uses+1 WHERE code=$1", [code])
            else:
                conn = get_db()
                conn.execute(
                    "UPDATE users SET plan='pro', referred_by_code=? WHERE id=?",
                    (code, user_id),
                )
                conn.execute("UPDATE promo_codes SET uses=uses+1 WHERE code=?", (code,))
                conn.commit()
                conn.close()
            return {"ok": True, "message": "free_pro"}, 200

        if promo["code_type"] == "affiliate":
            affiliate_email = promo.get("affiliate_email") or ""
            commission_percent = promo.get("commission_percent") or 0
            if USE_POSTGRES:
                pg_run(
                    "UPDATE users SET referred_by_code=$1, affiliate_email=$2 WHERE id=$3",
                    [code, affiliate_email, user_id],
                )
                pg_run("UPDATE promo_codes SET uses=uses+1 WHERE code=$1", [code])
                pg_run(
                    """
                    INSERT INTO affiliate_commissions
                    (affiliate_email, referred_user_id, referred_user_email, promo_code, commission_percent, status)
                    VALUES ($1, $2, $3, $4, $5, 'pending')
                    """,
                    [affiliate_email, user_id, user_email, code, commission_percent],
                )
            else:
                conn = get_db()
                conn.execute(
                    "UPDATE users SET referred_by_code=?, affiliate_email=? WHERE id=?",
                    (code, affiliate_email, user_id),
                )
                conn.execute("UPDATE promo_codes SET uses=uses+1 WHERE code=?", (code,))
                conn.execute(
                    """
                    INSERT INTO affiliate_commissions
                    (affiliate_email, referred_user_id, referred_user_email, promo_code, commission_percent, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                    """,
                    (affiliate_email, user_id, user_email, code, commission_percent),
                )
                conn.commit()
                conn.close()
            return {"ok": True, "message": "affiliate"}, 200

        return {"ok": False, "error": "Unknown promo code type"}, 400
    except Exception:
        traceback.print_exc()
        return {"ok": False, "error": "Failed to apply promo code"}, 500


@auth_bp.route("/api/auth/register", methods=["POST"])
@limiter.limit("5 per hour")
def register():
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        promo_code = (data.get("promo_code") or "").strip().upper()

        if not email or not username or not password:
            return jsonify({"error": "Please fill in all required fields"}), 400
        if not EMAIL_RE.match(email):
            return jsonify({"error": "Please enter a valid email address"}), 400
        if not USERNAME_RE.match(username):
            return jsonify({"error": "Username can only contain letters, numbers, and underscores"}), 400
        if len(username) < 3 or len(username) > 30:
            return jsonify({"error": "Username must be between 3 and 30 characters"}), 400
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400

        existing = get_user_by_email(email, include_inactive=True)
        if existing:
            return jsonify({"error": "An account with that email already exists"}), 409

        if USE_POSTGRES:
            duplicate_username = pg_run("SELECT id FROM users WHERE username=$1", [username])
            if duplicate_username:
                return jsonify({"error": "That username is already taken"}), 409
        else:
            conn = get_db()
            duplicate_username = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            conn.close()
            if duplicate_username:
                return jsonify({"error": "That username is already taken"}), 409

        user_id = create_user(email, username, password)
        promo_message = None
        if promo_code:
            promo_result, promo_status = _apply_promo_code(user_id, email, promo_code)
            if promo_result.get("ok"):
                promo_message = "pro_applied" if promo_result.get("message") == "free_pro" else "affiliate_tracked"
            else:
                promo_message = "invalid"

        token = create_session(user_id)
        user = _with_usage(get_user_by_id(user_id))
        return jsonify({"token": token, "user": _user_response(user), "promo_message": promo_message}), 201
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@auth_bp.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per hour")
def login():
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            return jsonify({"error": "Please fill in all required fields"}), 400

        user = get_user_by_email(email, include_inactive=True)
        if not user or not verify_password(password, user["password_hash"]):
            return jsonify({"error": "Invalid email or password"}), 401
        if not bool(user.get("is_active", True)):
            return jsonify({"error": "This account has been deactivated. Contact support@roofdraftai.com"}), 403

        current_month = datetime.now().strftime("%Y-%m")
        maybe_reset_monthly_count(user["id"], current_month)
        token = create_session(user["id"])
        fresh_user = _with_usage(get_user_by_id(user["id"]))
        return jsonify({"token": token, "user": _user_response(fresh_user)})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            delete_session(auth_header[7:])
        return jsonify({"success": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        current_month = datetime.now().strftime("%Y-%m")
        maybe_reset_monthly_count(user["id"], current_month)
        fresh_user = _with_usage(get_user_by_id(user["id"]))
        return jsonify(_user_response(fresh_user))
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@auth_bp.route("/api/auth/apply-promo", methods=["POST"])
def apply_promo():
    try:
        user = require_auth()
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        data = request.get_json() or {}
        code = (data.get("code") or "").strip().upper()
        if not code:
            return jsonify({"error": "Promo code is required"}), 400
        result, status = _apply_promo_code(user["id"], user["email"], code)
        if not result.get("ok"):
            return jsonify({"error": result.get("error", "Invalid promo code")}), status
        updated_user = _with_usage(get_user_by_id(user["id"]))
        return jsonify({"user": _user_response(updated_user), "plan": updated_user.get("plan"), "message": result.get("message")})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
