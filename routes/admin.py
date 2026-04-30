"""
RoofDraftAI admin routes.
"""

import traceback

from flask import Blueprint, jsonify, request

from database.db import USE_POSTGRES, get_contact_messages, get_db, pg_run, require_auth, row_to_dict

admin_bp = Blueprint("admin", __name__)

PLAN_PRICE = {"starter": 49, "pro": 79}
ALLOWED_PLANS = {"free", "starter", "pro"}


def require_admin():
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not bool(user.get("is_admin")):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return user, None


def fetch_admin_stats_payload():
    if USE_POSTGRES:
        overview = {
            "total_users": pg_run("SELECT COUNT(*) AS cnt FROM users")[0]["cnt"],
            "active_users_this_month": pg_run(
                "SELECT COUNT(*) AS cnt FROM users WHERE created_at >= date_trunc('month', NOW())"
            )[0]["cnt"],
            "total_generations": pg_run("SELECT COUNT(*) AS cnt FROM generation_logs")[0]["cnt"],
            "generations_today": pg_run("SELECT COUNT(*) AS cnt FROM generation_logs WHERE created_at >= CURRENT_DATE")[0]["cnt"],
        }
        plan_counts_rows = pg_run("SELECT plan, COUNT(*) AS cnt FROM users GROUP BY plan")
        plan_counts = {row["plan"]: row["cnt"] for row in plan_counts_rows}
        overview["estimated_mrr"] = (plan_counts.get("starter", 0) * 49) + (plan_counts.get("pro", 0) * 79)

        users = pg_run(
            """
            SELECT u.id, u.username, u.email, u.plan, u.is_active, u.is_admin, u.created_at,
                   u.generations_this_month, COUNT(gl.id) AS total_generations
            FROM users u
            LEFT JOIN generation_logs gl ON gl.user_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at DESC
            """
        )
        for user in users:
            if user.get("created_at") and not isinstance(user["created_at"], str):
                user["created_at"] = user["created_at"].isoformat()

        tool_usage_rows = pg_run(
            "SELECT tool_name, COUNT(*) AS count FROM generation_logs GROUP BY tool_name ORDER BY count DESC"
        )
        tool_usage = {row["tool_name"]: row["count"] for row in tool_usage_rows}

        recent_activity = pg_run(
            """
            SELECT gl.id, gl.tool_name, gl.created_at, u.username
            FROM generation_logs gl
            JOIN users u ON u.id = gl.user_id
            ORDER BY gl.created_at DESC
            LIMIT 20
            """
        )
        for item in recent_activity:
            if item.get("created_at") and not isinstance(item["created_at"], str):
                item["created_at"] = item["created_at"].isoformat()

        promo_codes = pg_run(
            """
            SELECT id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
            FROM promo_codes
            ORDER BY created_at DESC
            """
        )
        for promo in promo_codes:
            if promo.get("created_at") and not isinstance(promo["created_at"], str):
                promo["created_at"] = promo["created_at"].isoformat()
    else:
        conn = get_db()
        overview = {
            "total_users": row_to_dict(conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone())["cnt"],
            "active_users_this_month": row_to_dict(
                conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m','now')").fetchone()
            )["cnt"],
            "total_generations": row_to_dict(conn.execute("SELECT COUNT(*) AS cnt FROM generation_logs").fetchone())["cnt"],
            "generations_today": row_to_dict(
                conn.execute("SELECT COUNT(*) AS cnt FROM generation_logs WHERE date(created_at)=date('now')").fetchone()
            )["cnt"],
        }
        plan_counts_rows = conn.execute("SELECT plan, COUNT(*) AS cnt FROM users GROUP BY plan").fetchall()
        plan_counts = {row_to_dict(row)["plan"]: row_to_dict(row)["cnt"] for row in plan_counts_rows}
        overview["estimated_mrr"] = (plan_counts.get("starter", 0) * 49) + (plan_counts.get("pro", 0) * 79)

        users = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT u.id, u.username, u.email, u.plan, u.is_active, u.is_admin, u.created_at,
                       u.generations_this_month, COUNT(gl.id) AS total_generations
                FROM users u
                LEFT JOIN generation_logs gl ON gl.user_id = u.id
                GROUP BY u.id
                ORDER BY u.created_at DESC
                """
            ).fetchall()
        ]
        tool_usage_rows = conn.execute(
            "SELECT tool_name, COUNT(*) AS count FROM generation_logs GROUP BY tool_name ORDER BY count DESC"
        ).fetchall()
        tool_usage = {row_to_dict(row)["tool_name"]: row_to_dict(row)["count"] for row in tool_usage_rows}
        recent_activity = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT gl.id, gl.tool_name, gl.created_at, u.username
                FROM generation_logs gl
                JOIN users u ON u.id = gl.user_id
                ORDER BY gl.created_at DESC
                LIMIT 20
                """
            ).fetchall()
        ]
        promo_codes = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
                FROM promo_codes
                ORDER BY created_at DESC
                """
            ).fetchall()
        ]
        conn.close()

    return {
        "overview": overview,
        "plan_counts": plan_counts,
        "users": users,
        "tool_usage": tool_usage,
        "recent_activity": recent_activity,
        "promo_codes": promo_codes,
        "contact_messages": get_contact_messages(),
    }


@admin_bp.route("/api/admin/stats", methods=["GET"])
def admin_stats():
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        return jsonify(fetch_admin_stats_payload())
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/users", methods=["GET"])
def admin_users():
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        return jsonify({"users": fetch_admin_stats_payload()["users"]})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/contacts", methods=["GET"])
def admin_contacts():
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        return jsonify({"messages": get_contact_messages()})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/promo-codes", methods=["GET"])
def list_promo_codes():
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        return jsonify({"codes": fetch_admin_stats_payload()["promo_codes"]})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/users/<int:user_id>/plan", methods=["PATCH"])
def update_user_plan(user_id):
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        plan = (data.get("plan") or "").strip().lower()
        if plan not in ALLOWED_PLANS:
            return jsonify({"error": "Plan must be free, starter, or pro"}), 400
        if USE_POSTGRES:
            rows = pg_run(
                "UPDATE users SET plan=$1 WHERE id=$2 RETURNING id, username, email, plan, is_active, is_admin, generations_this_month, created_at",
                [plan, user_id],
            )
            user = rows[0] if rows else None
        else:
            conn = get_db()
            conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id))
            conn.commit()
            row = conn.execute(
                "SELECT id, username, email, plan, is_active, is_admin, generations_this_month, created_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            conn.close()
            user = row_to_dict(row)
        return jsonify({"user": user})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/users/<int:user_id>/toggle-active", methods=["PATCH"])
def toggle_user_active(user_id):
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        if USE_POSTGRES:
            rows = pg_run(
                """
                UPDATE users
                SET is_active = NOT COALESCE(is_active, TRUE)
                WHERE id = $1
                RETURNING id, username, email, plan, is_active, is_admin, generations_this_month, created_at
                """,
                [user_id],
            )
            user = rows[0] if rows else None
        else:
            conn = get_db()
            existing = conn.execute("SELECT is_active FROM users WHERE id=?", (user_id,)).fetchone()
            next_value = 0 if row_to_dict(existing).get("is_active") else 1
            conn.execute("UPDATE users SET is_active=? WHERE id=?", (next_value, user_id))
            conn.commit()
            row = conn.execute(
                "SELECT id, username, email, plan, is_active, is_admin, generations_this_month, created_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            conn.close()
            user = row_to_dict(row)
        return jsonify({"user": user})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/promo-codes/create", methods=["POST"])
def create_promo_code():
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        code = (data.get("code") or "").strip().upper()
        code_type = (data.get("code_type") or "").strip().lower()
        affiliate_email = (data.get("affiliate_email") or "").strip().lower() or None
        commission_percent = data.get("commission_percent")

        if not code:
            return jsonify({"error": "Code name is required"}), 400
        if code_type not in {"free_pro", "affiliate"}:
            return jsonify({"error": "code_type must be free_pro or affiliate"}), 400
        if code_type == "affiliate":
            if not affiliate_email:
                return jsonify({"error": "Affiliate email is required for affiliate codes"}), 400
            try:
                commission_percent = int(commission_percent)
            except (TypeError, ValueError):
                return jsonify({"error": "Commission percent is required for affiliate codes"}), 400

        if USE_POSTGRES:
            rows = pg_run(
                """
                INSERT INTO promo_codes (code, code_type, affiliate_email, commission_percent)
                VALUES ($1, $2, $3, $4)
                RETURNING id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
                """,
                [code, code_type, affiliate_email, commission_percent],
            )
            promo_code = rows[0] if rows else None
        else:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO promo_codes (code, code_type, affiliate_email, commission_percent) VALUES (?, ?, ?, ?)",
                (code, code_type, affiliate_email, commission_percent),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
                FROM promo_codes WHERE id=?
                """,
                (cur.lastrowid,),
            ).fetchone()
            conn.close()
            promo_code = row_to_dict(row)
        return jsonify({"code": promo_code}), 201
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/promo-codes/<int:promo_code_id>/toggle", methods=["PATCH"])
def toggle_promo_code(promo_code_id):
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        if USE_POSTGRES:
            rows = pg_run(
                """
                UPDATE promo_codes
                SET is_active = NOT COALESCE(is_active, TRUE)
                WHERE id = $1
                RETURNING id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
                """,
                [promo_code_id],
            )
            promo_code = rows[0] if rows else None
        else:
            conn = get_db()
            existing = conn.execute("SELECT is_active FROM promo_codes WHERE id=?", (promo_code_id,)).fetchone()
            next_value = 0 if row_to_dict(existing).get("is_active") else 1
            conn.execute("UPDATE promo_codes SET is_active=? WHERE id=?", (next_value, promo_code_id))
            conn.commit()
            row = conn.execute(
                """
                SELECT id, code, code_type, uses, is_active, affiliate_email, commission_percent, created_at
                FROM promo_codes WHERE id=?
                """,
                (promo_code_id,),
            ).fetchone()
            conn.close()
            promo_code = row_to_dict(row)
        return jsonify({"code": promo_code})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@admin_bp.route("/api/admin/promo-codes/<int:promo_code_id>", methods=["DELETE"])
def delete_promo_code(promo_code_id):
    try:
        _, error_response = require_admin()
        if error_response:
            return error_response
        if USE_POSTGRES:
            pg_run("DELETE FROM promo_codes WHERE id=$1", [promo_code_id])
        else:
            conn = get_db()
            conn.execute("DELETE FROM promo_codes WHERE id=?", (promo_code_id,))
            conn.commit()
            conn.close()
        return jsonify({"success": True})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500
