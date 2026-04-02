"""
RoofDraft — Admin Routes
Only accessible by users with is_admin = TRUE.
"""
from flask import Blueprint, jsonify, request
from database.db import require_auth, USE_POSTGRES, pg_run, get_db, row_to_dict, get_contact_messages

admin_bp = Blueprint('admin', __name__)

PLAN_PRICE = {'starter': 49, 'pro': 79}


def require_admin():
    user = require_auth()
    if not user:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    if not bool(user.get('is_admin')):
        return None, (jsonify({"error": "Forbidden"}), 403)
    return user, None


@admin_bp.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    _, err = require_admin()
    if err:
        return err

    if USE_POSTGRES:
        # Users by plan
        plan_rows = pg_run(
            "SELECT plan, COUNT(*) AS cnt FROM users GROUP BY plan"
        )
        plan_counts = {r['plan']: r['cnt'] for r in plan_rows}

        # Total users
        total_rows = pg_run("SELECT COUNT(*) AS cnt FROM users")
        total_users = total_rows[0]['cnt'] if total_rows else 0

        # New users this month
        new_rows = pg_run(
            "SELECT COUNT(*) AS cnt FROM users "
            "WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())"
        )
        new_this_month = new_rows[0]['cnt'] if new_rows else 0

        # Total all-time generations
        gen_rows = pg_run("SELECT COUNT(*) AS cnt FROM generation_logs")
        total_gens = gen_rows[0]['cnt'] if gen_rows else 0

        # Generations this month
        gen_month_rows = pg_run(
            "SELECT COUNT(*) AS cnt FROM generation_logs "
            "WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())"
        )
        gens_this_month = gen_month_rows[0]['cnt'] if gen_month_rows else 0

        # Generations by tool (all time)
        tool_rows = pg_run(
            "SELECT tool_name, COUNT(*) AS cnt FROM generation_logs GROUP BY tool_name ORDER BY cnt DESC"
        )
        gens_by_tool = {r['tool_name']: r['cnt'] for r in tool_rows}

    else:
        conn = get_db()
        plan_rows = conn.execute("SELECT plan, COUNT(*) AS cnt FROM users GROUP BY plan").fetchall()
        plan_counts = {row_to_dict(r)['plan']: row_to_dict(r)['cnt'] for r in plan_rows}

        total_users = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        total_users = row_to_dict(total_users)['cnt'] if total_users else 0

        new_this_month = conn.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()
        new_this_month = row_to_dict(new_this_month)['cnt'] if new_this_month else 0

        total_gens = conn.execute("SELECT COUNT(*) AS cnt FROM generation_logs").fetchone()
        total_gens = row_to_dict(total_gens)['cnt'] if total_gens else 0

        gens_this_month = conn.execute(
            "SELECT COUNT(*) AS cnt FROM generation_logs WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()
        gens_this_month = row_to_dict(gens_this_month)['cnt'] if gens_this_month else 0

        tool_rows = conn.execute(
            "SELECT tool_name, COUNT(*) AS cnt FROM generation_logs GROUP BY tool_name ORDER BY cnt DESC"
        ).fetchall()
        gens_by_tool = {row_to_dict(r)['tool_name']: row_to_dict(r)['cnt'] for r in tool_rows}

        conn.close()

    # Estimated MRR
    mrr = sum(
        PLAN_PRICE.get(plan, 0) * count
        for plan, count in plan_counts.items()
    )

    return jsonify({
        "total_users": total_users,
        "new_this_month": new_this_month,
        "plan_counts": plan_counts,
        "total_generations": total_gens,
        "generations_this_month": gens_this_month,
        "generations_by_tool": gens_by_tool,
        "estimated_mrr": mrr,
    })


@admin_bp.route('/api/admin/users', methods=['GET'])
def admin_users():
    _, err = require_admin()
    if err:
        return err

    if USE_POSTGRES:
        rows = pg_run(
            """SELECT u.id, u.email, u.username, u.plan, u.is_admin,
                      u.generations_this_month, u.is_active, u.created_at,
                      COUNT(gl.id) AS total_generations
               FROM users u
               LEFT JOIN generation_logs gl ON gl.user_id = u.id
               GROUP BY u.id
               ORDER BY u.created_at DESC"""
        )
        users = []
        for r in rows:
            r = dict(r)
            if r.get('created_at') and not isinstance(r['created_at'], str):
                r['created_at'] = r['created_at'].isoformat()
            users.append(r)
    else:
        conn = get_db()
        rows = conn.execute(
            """SELECT u.id, u.email, u.username, u.plan, u.is_admin,
                      u.generations_this_month, u.is_active, u.created_at,
                      COUNT(gl.id) AS total_generations
               FROM users u
               LEFT JOIN generation_logs gl ON gl.user_id = u.id
               GROUP BY u.id
               ORDER BY u.created_at DESC"""
        ).fetchall()
        users = [row_to_dict(r) for r in rows]
        conn.close()

    return jsonify({"users": users})


@admin_bp.route('/api/admin/contacts', methods=['GET'])
def admin_contacts():
    _, err = require_admin()
    if err:
        return err
    messages = get_contact_messages()
    return jsonify({"messages": messages})


# ---------------------------------------------------------------------------
# Promo Code Management
# ---------------------------------------------------------------------------

@admin_bp.route('/api/admin/promo-codes', methods=['GET'])
def list_promo_codes():
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            rows = pg_run(
                "SELECT id, code, code_type, is_active, uses, created_at, "
                "affiliate_email, commission_percent, notes "
                "FROM promo_codes ORDER BY created_at DESC"
            )
            codes = []
            for r in rows:
                r = dict(r)
                if r.get('created_at') and not isinstance(r['created_at'], str):
                    r['created_at'] = r['created_at'].isoformat()
                codes.append(r)
        else:
            conn = get_db()
            rows = conn.execute(
                "SELECT id, code, code_type, is_active, uses, created_at, "
                "affiliate_email, commission_percent, notes "
                "FROM promo_codes ORDER BY created_at DESC"
            ).fetchall()
            codes = [row_to_dict(r) for r in rows]
            conn.close()
        return jsonify({"codes": codes})
    except Exception as e:
        print(f"[Admin] list promo codes error: {e}")
        return jsonify({"error": "Failed to load promo codes"}), 500


@admin_bp.route('/api/admin/promo-codes/create', methods=['POST'])
def create_promo_code():
    _, err = require_admin()
    if err:
        return err

    data = request.get_json() or {}
    code = (data.get('code') or '').strip().upper()
    code_type = (data.get('code_type') or '').strip()
    affiliate_email = (data.get('affiliate_email') or '').strip().lower() or None
    commission_percent = data.get('commission_percent')
    notes = (data.get('notes') or '').strip() or None

    if not code:
        return jsonify({"error": "Code name is required"}), 400
    if code_type not in ('free_pro', 'affiliate'):
        return jsonify({"error": "code_type must be 'free_pro' or 'affiliate'"}), 400
    if code_type == 'affiliate':
        if not affiliate_email:
            return jsonify({"error": "Affiliate email is required for affiliate codes"}), 400
        if commission_percent is None:
            return jsonify({"error": "Commission percent is required for affiliate codes"}), 400
        try:
            commission_percent = int(commission_percent)
            if not (1 <= commission_percent <= 100):
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({"error": "Commission percent must be a whole number between 1 and 100"}), 400

    try:
        if USE_POSTGRES:
            # Check for duplicate
            existing = pg_run("SELECT id FROM promo_codes WHERE code=$1", [code])
            if existing:
                return jsonify({"error": f"Code '{code}' already exists"}), 409
            rows = pg_run(
                "INSERT INTO promo_codes (code, code_type, is_active, uses, affiliate_email, commission_percent, notes) "
                "VALUES ($1, $2, TRUE, 0, $3, $4, $5) RETURNING id, code, code_type, is_active, uses, created_at, "
                "affiliate_email, commission_percent, notes",
                [code, code_type, affiliate_email, commission_percent, notes]
            )
            new_code = dict(rows[0]) if rows else {}
            if new_code.get('created_at') and not isinstance(new_code['created_at'], str):
                new_code['created_at'] = new_code['created_at'].isoformat()
        else:
            conn = get_db()
            existing = conn.execute("SELECT id FROM promo_codes WHERE code=?", (code,)).fetchone()
            if existing:
                conn.close()
                return jsonify({"error": f"Code '{code}' already exists"}), 409
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO promo_codes (code, code_type, is_active, uses, affiliate_email, commission_percent, notes) "
                "VALUES (?, ?, 1, 0, ?, ?, ?)",
                (code, code_type, affiliate_email, commission_percent, notes)
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, code, code_type, is_active, uses, created_at, affiliate_email, commission_percent, notes "
                "FROM promo_codes WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            conn.close()
            new_code = row_to_dict(row) or {}

        return jsonify({"code": new_code, "message": "Code created successfully."}), 201

    except Exception as e:
        print(f"[Admin] create promo code error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"error": "Failed to create promo code"}), 500


@admin_bp.route('/api/admin/promo-codes/<int:code_id>', methods=['DELETE'])
def delete_promo_code(code_id):
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            pg_run("DELETE FROM promo_codes WHERE id=$1", [code_id])
        else:
            conn = get_db()
            conn.execute("DELETE FROM promo_codes WHERE id=?", (code_id,))
            conn.commit()
            conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[Admin] delete promo code error: {e}")
        return jsonify({"error": "Failed to delete promo code"}), 500


@admin_bp.route('/api/admin/promo-codes/<int:code_id>/toggle', methods=['PATCH'])
def toggle_promo_code(code_id):
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            rows = pg_run(
                "UPDATE promo_codes SET is_active = NOT is_active WHERE id=$1 "
                "RETURNING id, code, is_active",
                [code_id]
            )
            result = rows[0] if rows else {}
        else:
            conn = get_db()
            row = conn.execute("SELECT is_active FROM promo_codes WHERE id=?", (code_id,)).fetchone()
            if not row:
                conn.close()
                return jsonify({"error": "Code not found"}), 404
            current = row_to_dict(row)['is_active']
            new_val = 0 if current else 1
            conn.execute("UPDATE promo_codes SET is_active=? WHERE id=?", (new_val, code_id))
            conn.commit()
            row = conn.execute("SELECT id, code, is_active FROM promo_codes WHERE id=?", (code_id,)).fetchone()
            conn.close()
            result = row_to_dict(row) or {}
        return jsonify({"code": result})
    except Exception as e:
        print(f"[Admin] toggle promo code error: {e}")
        return jsonify({"error": "Failed to toggle promo code"}), 500


@admin_bp.route('/api/admin/affiliates', methods=['GET'])
def list_affiliates():
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            rows = pg_run(
                """SELECT p.id, p.code, p.affiliate_email, p.commission_percent, p.uses,
                          COUNT(ac.id) AS total_referred,
                          COUNT(CASE WHEN ac.status='pending' THEN 1 END) AS pending_count
                   FROM promo_codes p
                   LEFT JOIN affiliate_commissions ac ON ac.promo_code = p.code
                   WHERE p.code_type = 'affiliate'
                   GROUP BY p.id, p.code, p.affiliate_email, p.commission_percent, p.uses
                   ORDER BY p.created_at DESC"""
            )
            affiliates = [dict(r) for r in rows]
        else:
            conn = get_db()
            rows = conn.execute(
                """SELECT p.id, p.code, p.affiliate_email, p.commission_percent, p.uses,
                          COUNT(ac.id) AS total_referred,
                          COUNT(CASE WHEN ac.status='pending' THEN 1 END) AS pending_count
                   FROM promo_codes p
                   LEFT JOIN affiliate_commissions ac ON ac.promo_code = p.code
                   WHERE p.code_type = 'affiliate'
                   GROUP BY p.id, p.code, p.affiliate_email, p.commission_percent, p.uses
                   ORDER BY p.created_at DESC"""
            ).fetchall()
            affiliates = [row_to_dict(r) for r in rows]
            conn.close()
        return jsonify({"affiliates": affiliates})
    except Exception as e:
        print(f"[Admin] list affiliates error: {e}")
        return jsonify({"error": "Failed to load affiliates"}), 500


@admin_bp.route('/api/admin/affiliates/<affiliate_email>/commissions', methods=['GET'])
def affiliate_commissions(affiliate_email):
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            rows = pg_run(
                """SELECT ac.id, ac.referred_user_email, ac.promo_code, ac.commission_percent,
                          ac.status, ac.created_at, u.plan AS user_plan
                   FROM affiliate_commissions ac
                   LEFT JOIN users u ON u.id = ac.referred_user_id
                   WHERE ac.affiliate_email=$1
                   ORDER BY ac.created_at DESC""",
                [affiliate_email]
            )
            commissions = []
            for r in rows:
                r = dict(r)
                if r.get('created_at') and not isinstance(r['created_at'], str):
                    r['created_at'] = r['created_at'].isoformat()
                commissions.append(r)
        else:
            conn = get_db()
            rows = conn.execute(
                """SELECT ac.id, ac.referred_user_email, ac.promo_code, ac.commission_percent,
                          ac.status, ac.created_at, u.plan AS user_plan
                   FROM affiliate_commissions ac
                   LEFT JOIN users u ON u.id = ac.referred_user_id
                   WHERE ac.affiliate_email=?
                   ORDER BY ac.created_at DESC""",
                (affiliate_email,)
            ).fetchall()
            commissions = [row_to_dict(r) for r in rows]
            conn.close()
        return jsonify({"commissions": commissions})
    except Exception as e:
        print(f"[Admin] affiliate commissions error: {e}")
        return jsonify({"error": "Failed to load commissions"}), 500


@admin_bp.route('/api/admin/commissions/<int:commission_id>/mark-paid', methods=['PATCH'])
def mark_commission_paid(commission_id):
    _, err = require_admin()
    if err:
        return err

    try:
        if USE_POSTGRES:
            pg_run(
                "UPDATE affiliate_commissions SET status='paid' WHERE id=$1",
                [commission_id]
            )
        else:
            conn = get_db()
            conn.execute(
                "UPDATE affiliate_commissions SET status='paid' WHERE id=?",
                (commission_id,)
            )
            conn.commit()
            conn.close()
        return jsonify({"success": True})
    except Exception as e:
        print(f"[Admin] mark paid error: {e}")
        return jsonify({"error": "Failed to mark commission as paid"}), 500
