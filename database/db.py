"""
RoofDraftAI database layer.
PostgreSQL (Neon) in production, SQLite locally.
"""

import json
import os
import re
import secrets
import sqlite3
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


def pg_run(sql, params=None):
    import psycopg2
    import psycopg2.extras

    statement = re.sub(r"\$\d+", "%s", sql)
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(statement, params or [])
            conn.commit()
            try:
                return [dict(row) for row in cur.fetchall()]
            except psycopg2.ProgrammingError:
                return []
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    db_path = os.path.join(os.path.dirname(__file__), "..", "roofdraft.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return None


def _sqlite_executescript(conn, script):
    conn.executescript(script)
    conn.commit()


def init_db():
    if USE_POSTGRES:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                plan VARCHAR(50) DEFAULT 'free',
                generations_this_month INTEGER DEFAULT 0,
                last_reset_month VARCHAR(7) DEFAULT '',
                is_admin BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                referred_by_code VARCHAR(50) DEFAULT NULL,
                affiliate_email VARCHAR(255) DEFAULT NULL,
                stripe_customer_id VARCHAR(255) DEFAULT NULL,
                subscription_id VARCHAR(255) DEFAULT NULL,
                subscription_status VARCHAR(50) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS generation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                tool_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_defaults (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                defaults_data JSONB DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS job_folders (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                color VARCHAR(7) DEFAULT '#C0392B',
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS saved_drafts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                folder_id INTEGER REFERENCES job_folders(id) ON DELETE SET NULL,
                tool_name VARCHAR(100),
                title VARCHAR(255),
                content TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS contact_messages (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255),
                message TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS promo_codes (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) UNIQUE NOT NULL,
                code_type VARCHAR(20) NOT NULL DEFAULT 'free_pro',
                is_active BOOLEAN DEFAULT TRUE,
                uses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                affiliate_email VARCHAR(255) DEFAULT NULL,
                commission_percent INTEGER DEFAULT NULL,
                notes VARCHAR(255) DEFAULT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS affiliate_commissions (
                id SERIAL PRIMARY KEY,
                affiliate_email VARCHAR(255) NOT NULL,
                referred_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                referred_user_email VARCHAR(255),
                promo_code VARCHAR(50),
                commission_percent INTEGER,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                notes VARCHAR(255) DEFAULT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS subscription_events (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                event_type VARCHAR(100),
                plan VARCHAR(50),
                stripe_event_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )
            """,
        ]
        for sql in statements:
            pg_run(sql)

        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS generations_this_month INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_reset_month VARCHAR(7) DEFAULT ''",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by_code VARCHAR(50) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS affiliate_email VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(255) DEFAULT NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT NULL",
        ]
        for sql in migrations:
            pg_run(sql)

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)",
            "CREATE INDEX IF NOT EXISTS idx_generation_logs_user ON generation_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_saved_drafts_user ON saved_drafts(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_saved_drafts_folder ON saved_drafts(folder_id)",
            "CREATE INDEX IF NOT EXISTS idx_job_folders_user ON job_folders(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_defaults_user ON user_defaults(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_subscription_events_user ON subscription_events(user_id)",
        ]
        for sql in indexes:
            pg_run(sql)

        try:
            pg_run(
                """
                INSERT INTO saved_drafts (user_id, folder_id, tool_name, title, content, created_at)
                SELECT d.user_id, d.folder_id, d.tool_name, d.title, d.result, d.created_at
                FROM drafts d
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM saved_drafts sd
                    WHERE sd.user_id = d.user_id
                      AND sd.title = d.title
                      AND sd.created_at = d.created_at
                )
                """
            )
        except Exception:
            pass

        pg_run(
            """
            INSERT INTO promo_codes (code, code_type, is_active, notes)
            VALUES ('ROOFER2025', 'free_pro', TRUE, 'Default launch promo code')
            ON CONFLICT (code) DO NOTHING
            """
        )
        return

    conn = get_db()
    _sqlite_executescript(
        conn,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            generations_this_month INTEGER DEFAULT 0,
            last_reset_month TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            referred_by_code TEXT DEFAULT NULL,
            affiliate_email TEXT DEFAULT NULL,
            stripe_customer_id TEXT DEFAULT NULL,
            subscription_id TEXT DEFAULT NULL,
            subscription_status TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            tool_name TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS user_defaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            defaults_data TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS job_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            color TEXT DEFAULT '#C0392B',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS saved_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            folder_id INTEGER REFERENCES job_folders(id) ON DELETE SET NULL,
            tool_name TEXT,
            title TEXT,
            content TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            code_type TEXT NOT NULL DEFAULT 'free_pro',
            is_active INTEGER DEFAULT 1,
            uses INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            affiliate_email TEXT DEFAULT NULL,
            commission_percent INTEGER DEFAULT NULL,
            notes TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS affiliate_commissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            affiliate_email TEXT NOT NULL,
            referred_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            referred_user_email TEXT,
            promo_code TEXT,
            commission_percent INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            notes TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS subscription_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            event_type TEXT,
            plan TEXT,
            stripe_event_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
        CREATE INDEX IF NOT EXISTS idx_generation_logs_user ON generation_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_saved_drafts_user ON saved_drafts(user_id);
        CREATE INDEX IF NOT EXISTS idx_saved_drafts_folder ON saved_drafts(folder_id);
        CREATE INDEX IF NOT EXISTS idx_job_folders_user ON job_folders(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_defaults_user ON user_defaults(user_id);
        CREATE INDEX IF NOT EXISTS idx_subscription_events_user ON subscription_events(user_id);
        """
    )

    try:
        conn.execute(
            """
            INSERT INTO saved_drafts (user_id, folder_id, tool_name, title, content, created_at)
            SELECT d.user_id, d.folder_id, d.tool_name, d.title, d.result, d.created_at
            FROM drafts d
            WHERE NOT EXISTS (
                SELECT 1
                FROM saved_drafts sd
                WHERE sd.user_id = d.user_id
                  AND sd.title = d.title
                  AND sd.created_at = d.created_at
            )
            """
        )
        conn.commit()
    except Exception:
        pass

    conn.execute(
        """
        INSERT OR IGNORE INTO promo_codes (code, code_type, is_active, notes)
        VALUES ('ROOFER2025', 'free_pro', 1, 'Default launch promo code')
        """
    )
    conn.commit()
    conn.close()


def hash_password(password):
    from werkzeug.security import generate_password_hash

    return generate_password_hash(password)


def verify_password(password, stored):
    from werkzeug.security import check_password_hash

    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def generate_token():
    return secrets.token_urlsafe(48)


def create_user(email, username, password):
    password_hash = hash_password(password)
    if USE_POSTGRES:
        rows = pg_run(
            "INSERT INTO users (email, username, password_hash) VALUES ($1, $2, $3) RETURNING id",
            [email, username, password_hash],
        )
        return rows[0]["id"] if rows else None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
        (email, username, password_hash),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def create_session(user_id):
    token = generate_token()
    if USE_POSTGRES:
        pg_run(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES ($1, $2, NOW() + INTERVAL '30 days')",
            [user_id, token],
        )
        return token

    conn = get_db()
    conn.execute(
        "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, datetime('now', '+30 days'))",
        (user_id, token),
    )
    conn.commit()
    conn.close()
    return token


def delete_session(token):
    if USE_POSTGRES:
        pg_run("DELETE FROM sessions WHERE token=$1", [token])
        return

    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()


def get_user_by_email(email, include_inactive=False):
    if USE_POSTGRES:
        sql = (
            "SELECT id, email, username, password_hash, plan, generations_this_month, "
            "last_reset_month, is_admin, is_active, referred_by_code, stripe_customer_id, "
            "subscription_id, subscription_status, created_at "
            "FROM users WHERE email=$1"
        )
        rows = pg_run(sql, [email])
        user = rows[0] if rows else None
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT id, email, username, password_hash, plan, generations_this_month, "
            "last_reset_month, is_admin, is_active, referred_by_code, stripe_customer_id, "
            "subscription_id, subscription_status, created_at FROM users WHERE email=?",
            (email,),
        ).fetchone()
        conn.close()
        user = row_to_dict(row)
    if not include_inactive and user and not bool(user.get("is_active")):
        return None
    return user


def get_user_by_id(user_id):
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, email, username, plan, generations_this_month, last_reset_month, "
            "is_admin, is_active, referred_by_code, stripe_customer_id, subscription_id, "
            "subscription_status, created_at FROM users WHERE id=$1",
            [user_id],
        )
        return rows[0] if rows else None

    conn = get_db()
    row = conn.execute(
        "SELECT id, email, username, plan, generations_this_month, last_reset_month, "
        "is_admin, is_active, referred_by_code, stripe_customer_id, subscription_id, "
        "subscription_status, created_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def get_user_by_token(token):
    if USE_POSTGRES:
        rows = pg_run(
            """
            SELECT u.id, u.email, u.username, u.plan, u.generations_this_month, u.last_reset_month,
                   u.is_admin, u.is_active, u.referred_by_code, u.stripe_customer_id,
                   u.subscription_id, u.subscription_status, u.created_at
            FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE s.token = $1 AND s.expires_at > NOW()
            """,
            [token],
        )
        return rows[0] if rows else None

    conn = get_db()
    row = conn.execute(
        """
        SELECT u.id, u.email, u.username, u.plan, u.generations_this_month, u.last_reset_month,
               u.is_admin, u.is_active, u.referred_by_code, u.stripe_customer_id,
               u.subscription_id, u.subscription_status, u.created_at
        FROM users u
        JOIN sessions s ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > datetime('now')
        """,
        (token,),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def log_generation(user_id, tool_name):
    if USE_POSTGRES:
        pg_run(
            "INSERT INTO generation_logs (user_id, tool_name) VALUES ($1, $2)",
            [user_id, tool_name],
        )
        pg_run(
            "UPDATE users SET generations_this_month = COALESCE(generations_this_month, 0) + 1 WHERE id = $1",
            [user_id],
        )
        return

    conn = get_db()
    conn.execute(
        "INSERT INTO generation_logs (user_id, tool_name) VALUES (?, ?)",
        (user_id, tool_name),
    )
    conn.execute(
        "UPDATE users SET generations_this_month = COALESCE(generations_this_month, 0) + 1 WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_monthly_count(user_id):
    if USE_POSTGRES:
        rows = pg_run("SELECT generations_this_month FROM users WHERE id=$1", [user_id])
        return rows[0]["generations_this_month"] if rows else 0

    conn = get_db()
    row = conn.execute("SELECT generations_this_month FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row_to_dict(row).get("generations_this_month", 0) if row else 0


def get_total_generations(user_id):
    if USE_POSTGRES:
        rows = pg_run("SELECT COUNT(*) AS cnt FROM generation_logs WHERE user_id=$1", [user_id])
        return rows[0]["cnt"] if rows else 0

    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS cnt FROM generation_logs WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row_to_dict(row).get("cnt", 0) if row else 0


def maybe_reset_monthly_count(user_id, current_month):
    user = get_user_by_id(user_id)
    if not user:
        return
    if user.get("last_reset_month") == current_month:
        return
    if USE_POSTGRES:
        pg_run(
            "UPDATE users SET generations_this_month=0, last_reset_month=$1 WHERE id=$2",
            [current_month, user_id],
        )
        return

    conn = get_db()
    conn.execute(
        "UPDATE users SET generations_this_month=0, last_reset_month=? WHERE id=?",
        (current_month, user_id),
    )
    conn.commit()
    conn.close()


def require_auth():
    from flask import request

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    try:
        return get_user_by_token(token)
    except Exception:
        return None


def get_defaults(user_id):
    if USE_POSTGRES:
        rows = pg_run("SELECT defaults_data FROM user_defaults WHERE user_id=$1", [user_id])
        if not rows:
            return {}
        raw = rows[0]["defaults_data"]
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return {}

    conn = get_db()
    row = conn.execute("SELECT defaults_data FROM user_defaults WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return {}
    raw = row_to_dict(row).get("defaults_data", "{}")
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        return {}


def save_defaults(user_id, new_data):
    existing = get_defaults(user_id)
    merged = {**existing, **new_data}
    encoded = json.dumps(merged)

    if USE_POSTGRES:
        pg_run(
            """
            INSERT INTO user_defaults (user_id, defaults_data, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET defaults_data = $2::jsonb, updated_at = NOW()
            """,
            [user_id, encoded],
        )
        return merged

    conn = get_db()
    conn.execute(
        """
        INSERT INTO user_defaults (user_id, defaults_data, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET defaults_data=excluded.defaults_data, updated_at=datetime('now')
        """,
        (user_id, encoded),
    )
    conn.commit()
    conn.close()
    return merged


def save_draft(user_id, tool_name, title, content, folder_id=None):
    if USE_POSTGRES:
        rows = pg_run(
            """
            INSERT INTO saved_drafts (user_id, folder_id, tool_name, title, content)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, user_id, folder_id, tool_name, title, content, created_at
            """,
            [user_id, folder_id, tool_name, title, content],
        )
        draft = rows[0] if rows else None
        if draft and draft.get("created_at") and not isinstance(draft["created_at"], str):
            draft["created_at"] = draft["created_at"].isoformat()
        return draft

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO saved_drafts (user_id, folder_id, tool_name, title, content) VALUES (?, ?, ?, ?, ?)",
        (user_id, folder_id, tool_name, title, content),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, user_id, folder_id, tool_name, title, content, created_at FROM saved_drafts WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    draft = row_to_dict(row)
    return draft


def get_drafts(user_id, folder_id=None):
    if USE_POSTGRES:
        if folder_id is None:
            rows = pg_run(
                """
                SELECT id, folder_id, tool_name, title, content, created_at
                FROM saved_drafts
                WHERE user_id = $1
                ORDER BY created_at DESC
                """,
                [user_id],
            )
        else:
            rows = pg_run(
                """
                SELECT id, folder_id, tool_name, title, content, created_at
                FROM saved_drafts
                WHERE user_id = $1 AND folder_id = $2
                ORDER BY created_at DESC
                """,
                [user_id, folder_id],
            )
        result = []
        for row in rows:
            item = dict(row)
            if item.get("created_at") and not isinstance(item["created_at"], str):
                item["created_at"] = item["created_at"].isoformat()
            result.append(item)
        return result

    conn = get_db()
    if folder_id is None:
        rows = conn.execute(
            "SELECT id, folder_id, tool_name, title, content, created_at FROM saved_drafts WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, folder_id, tool_name, title, content, created_at FROM saved_drafts WHERE user_id=? AND folder_id=? ORDER BY created_at DESC",
            (user_id, folder_id),
        ).fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def get_draft_by_id(user_id, draft_id):
    if USE_POSTGRES:
        rows = pg_run(
            """
            SELECT id, folder_id, tool_name, title, content, created_at
            FROM saved_drafts
            WHERE id = $1 AND user_id = $2
            """,
            [draft_id, user_id],
        )
        draft = rows[0] if rows else None
        if draft and draft.get("created_at") and not isinstance(draft["created_at"], str):
            draft["created_at"] = draft["created_at"].isoformat()
        return draft

    conn = get_db()
    row = conn.execute(
        "SELECT id, folder_id, tool_name, title, content, created_at FROM saved_drafts WHERE id=? AND user_id=?",
        (draft_id, user_id),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def delete_draft(user_id, draft_id):
    if USE_POSTGRES:
        pg_run("DELETE FROM saved_drafts WHERE id=$1 AND user_id=$2", [draft_id, user_id])
        return True

    conn = get_db()
    conn.execute("DELETE FROM saved_drafts WHERE id=? AND user_id=?", (draft_id, user_id))
    conn.commit()
    conn.close()
    return True


def move_draft(user_id, draft_id, folder_id="__unset__", title=None):
    if USE_POSTGRES:
        if folder_id != "__unset__" and title is not None:
            pg_run(
                "UPDATE saved_drafts SET folder_id=$1, title=$2 WHERE id=$3 AND user_id=$4",
                [folder_id, title, draft_id, user_id],
            )
        elif folder_id != "__unset__":
            pg_run(
                "UPDATE saved_drafts SET folder_id=$1 WHERE id=$2 AND user_id=$3",
                [folder_id, draft_id, user_id],
            )
        elif title is not None:
            pg_run(
                "UPDATE saved_drafts SET title=$1 WHERE id=$2 AND user_id=$3",
                [title, draft_id, user_id],
            )
        return True

    conn = get_db()
    if folder_id != "__unset__" and title is not None:
        conn.execute(
            "UPDATE saved_drafts SET folder_id=?, title=? WHERE id=? AND user_id=?",
            (folder_id, title, draft_id, user_id),
        )
    elif folder_id != "__unset__":
        conn.execute(
            "UPDATE saved_drafts SET folder_id=? WHERE id=? AND user_id=?",
            (folder_id, draft_id, user_id),
        )
    elif title is not None:
        conn.execute(
            "UPDATE saved_drafts SET title=? WHERE id=? AND user_id=?",
            (title, draft_id, user_id),
        )
    conn.commit()
    conn.close()
    return True


def get_folders(user_id):
    if USE_POSTGRES:
        rows = pg_run(
            """
            SELECT f.id, f.name, f.color, f.created_at, COUNT(d.id) AS draft_count
            FROM job_folders f
            LEFT JOIN saved_drafts d ON d.folder_id = f.id
            WHERE f.user_id = $1
            GROUP BY f.id
            ORDER BY f.created_at ASC
            """,
            [user_id],
        )
        result = []
        for row in rows:
            item = dict(row)
            if item.get("created_at") and not isinstance(item["created_at"], str):
                item["created_at"] = item["created_at"].isoformat()
            result.append(item)
        return result

    conn = get_db()
    rows = conn.execute(
        """
        SELECT f.id, f.name, f.color, f.created_at, COUNT(d.id) AS draft_count
        FROM job_folders f
        LEFT JOIN saved_drafts d ON d.folder_id = f.id
        WHERE f.user_id = ?
        GROUP BY f.id
        ORDER BY f.created_at ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def create_folder(user_id, name, color):
    if USE_POSTGRES:
        rows = pg_run(
            """
            INSERT INTO job_folders (user_id, name, color)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, name, color, created_at
            """,
            [user_id, name, color],
        )
        folder = rows[0] if rows else None
        if folder and folder.get("created_at") and not isinstance(folder["created_at"], str):
            folder["created_at"] = folder["created_at"].isoformat()
        return folder

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO job_folders (user_id, name, color) VALUES (?, ?, ?)",
        (user_id, name, color),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, user_id, name, color, created_at FROM job_folders WHERE id=?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def update_folder(user_id, folder_id, name):
    if USE_POSTGRES:
        rows = pg_run(
            """
            UPDATE job_folders SET name=$1
            WHERE id=$2 AND user_id=$3
            RETURNING id, user_id, name, color, created_at
            """,
            [name, folder_id, user_id],
        )
        folder = rows[0] if rows else None
        if folder and folder.get("created_at") and not isinstance(folder["created_at"], str):
            folder["created_at"] = folder["created_at"].isoformat()
        return folder

    conn = get_db()
    conn.execute("UPDATE job_folders SET name=? WHERE id=? AND user_id=?", (name, folder_id, user_id))
    conn.commit()
    row = conn.execute(
        "SELECT id, user_id, name, color, created_at FROM job_folders WHERE id=? AND user_id=?",
        (folder_id, user_id),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def delete_folder(user_id, folder_id):
    if USE_POSTGRES:
        pg_run("UPDATE saved_drafts SET folder_id=NULL WHERE folder_id=$1 AND user_id=$2", [folder_id, user_id])
        pg_run("DELETE FROM job_folders WHERE id=$1 AND user_id=$2", [folder_id, user_id])
        return True

    conn = get_db()
    conn.execute("UPDATE saved_drafts SET folder_id=NULL WHERE folder_id=? AND user_id=?", (folder_id, user_id))
    conn.execute("DELETE FROM job_folders WHERE id=? AND user_id=?", (folder_id, user_id))
    conn.commit()
    conn.close()
    return True


def save_contact_message(name, email, message):
    if USE_POSTGRES:
        rows = pg_run(
            "INSERT INTO contact_messages (name, email, message) VALUES ($1, $2, $3) RETURNING id",
            [name, email, message],
        )
        return rows[0]["id"] if rows else None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO contact_messages (name, email, message) VALUES (?, ?, ?)",
        (name, email, message),
    )
    conn.commit()
    message_id = cur.lastrowid
    conn.close()
    return message_id


def get_contact_messages():
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, name, email, message, created_at FROM contact_messages ORDER BY created_at DESC"
        )
        result = []
        for row in rows:
            item = dict(row)
            if item.get("created_at") and not isinstance(item["created_at"], str):
                item["created_at"] = item["created_at"].isoformat()
            result.append(item)
        return result

    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, email, message, created_at FROM contact_messages ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [row_to_dict(row) for row in rows]


def update_user_subscription(user_id, plan=None, stripe_customer_id=None, subscription_id=None, subscription_status=None):
    fields = []
    params = []
    if plan is not None:
        fields.append("plan = $%d" % (len(params) + 1) if USE_POSTGRES else "plan = ?")
        params.append(plan)
    if stripe_customer_id is not None:
        fields.append("stripe_customer_id = $%d" % (len(params) + 1) if USE_POSTGRES else "stripe_customer_id = ?")
        params.append(stripe_customer_id)
    if subscription_id is not None:
        fields.append("subscription_id = $%d" % (len(params) + 1) if USE_POSTGRES else "subscription_id = ?")
        params.append(subscription_id)
    if subscription_status is not None:
        fields.append("subscription_status = $%d" % (len(params) + 1) if USE_POSTGRES else "subscription_status = ?")
        params.append(subscription_status)
    if not fields:
        return

    if USE_POSTGRES:
        params.append(user_id)
        sql = "UPDATE users SET %s WHERE id = $%d" % (", ".join(fields), len(params))
        pg_run(sql, params)
        return

    params.append(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET %s WHERE id = ?" % ", ".join(fields), params)
    conn.commit()
    conn.close()


def get_user_by_stripe_customer_id(customer_id):
    if not customer_id:
        return None
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, email, username, plan, generations_this_month, is_admin, is_active, stripe_customer_id, subscription_id, subscription_status FROM users WHERE stripe_customer_id=$1",
            [customer_id],
        )
        return rows[0] if rows else None

    conn = get_db()
    row = conn.execute(
        "SELECT id, email, username, plan, generations_this_month, is_admin, is_active, stripe_customer_id, subscription_id, subscription_status FROM users WHERE stripe_customer_id=?",
        (customer_id,),
    ).fetchone()
    conn.close()
    return row_to_dict(row)


def record_subscription_event(user_id, event_type, plan, stripe_event_id):
    if USE_POSTGRES:
        pg_run(
            """
            INSERT INTO subscription_events (user_id, event_type, plan, stripe_event_id)
            VALUES ($1, $2, $3, $4)
            """,
            [user_id, event_type, plan, stripe_event_id],
        )
        return

    conn = get_db()
    conn.execute(
        "INSERT INTO subscription_events (user_id, event_type, plan, stripe_event_id) VALUES (?, ?, ?, ?)",
        (user_id, event_type, plan, stripe_event_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
