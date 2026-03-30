"""
RoofDraft AI — Admin Routes
Only accessible by users with is_admin = TRUE.
"""
from flask import Blueprint, jsonify
from database.db import require_auth, USE_POSTGRES, pg_run, get_db, row_to_dict

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
