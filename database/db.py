"""
RoofDraft AI — Database Layer
PostgreSQL (Neon) in production, SQLite locally.
"""

import os
import re
import secrets
import sqlite3
import traceback as _tb
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


# ---------------------------------------------------------------------------
# Core DB helpers
# ---------------------------------------------------------------------------

def pg_run(sql, params=None):
    """Execute SQL against Neon PostgreSQL via psycopg2."""
    import psycopg2
    import psycopg2.extras
    psql = re.sub(r'\$\d+', '%s', sql)
    preview = psql[:120].replace('\n', ' ')
    print(f"[DB] pg_run: {preview}")
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
    except Exception as e:
        print(f"[DB] CONNECT FAILED: {e}")
        raise
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(psql, params or [])
            conn.commit()
            try:
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            except psycopg2.ProgrammingError:
                return []
    except Exception as e:
        conn.rollback()
        print(f"[DB] pg_run ERROR on '{preview}': {e}")
        _tb.print_exc()
        raise
    finally:
        conn.close()


def get_db():
    """SQLite connection for local dev."""
    db_path = os.path.join(os.path.dirname(__file__), '..', 'roofdraft.db')
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


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_db():
    if USE_POSTGRES:
        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                plan VARCHAR(50) DEFAULT 'free',
                generations_this_month INTEGER DEFAULT 0,
                last_reset_month VARCHAR(7) DEFAULT '',
                is_admin BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                token VARCHAR(255) UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS generation_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                tool_name VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )""",
        ]
        for sql in tables:
            try:
                pg_run(sql)
            except Exception as e:
                print(f"[DB] Table creation note: {e}")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)",
            "CREATE INDEX IF NOT EXISTS idx_logs_user ON generation_logs(user_id)",
        ]
        for sql in indexes:
            try:
                pg_run(sql)
            except Exception:
                pass

        # user_defaults table
        try:
            pg_run("""CREATE TABLE IF NOT EXISTS user_defaults (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                defaults_data JSONB DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT NOW()
            )""")
            pg_run("CREATE INDEX IF NOT EXISTS idx_defaults_user ON user_defaults(user_id)")
        except Exception as e:
            print(f"[DB] user_defaults table note: {e}")

        # drafts table
        try:
            pg_run("""CREATE TABLE IF NOT EXISTS drafts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                tool_name VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                result TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )""")
            pg_run("CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id)")
        except Exception as e:
            print(f"[DB] Drafts table note: {e}")

        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS generations_this_month INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_reset_month VARCHAR(7) DEFAULT ''",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        ]
        for sql in migrations:
            try:
                pg_run(sql)
                print(f"[DB] Migration: {sql}")
            except Exception as e:
                print(f"[DB] Migration note ({sql[:60]}): {e}")

        # Ensure admin user
        try:
            pg_run(
                "UPDATE users SET is_admin=TRUE, plan='pro', generations_this_month=0 "
                "WHERE email='owen.murillo2533@gmail.com'"
            )
            print("[DB] Admin user migration applied")
        except Exception as e:
            print(f"[DB] Admin migration note: {e}")

        print("[DB] Initialized using PostgreSQL (psycopg2)")
    else:
        conn = get_db()
        conn.executescript("""
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
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tool_name TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_defaults (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            defaults_data TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            title TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
        CREATE INDEX IF NOT EXISTS idx_logs_user ON generation_logs(user_id);
        CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id);
        """)
        conn.commit()
        conn.close()
        print("[DB] Initialized using SQLite (local)")


# ---------------------------------------------------------------------------
# Password hashing (werkzeug)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password)


def verify_password(password: str, stored: str) -> bool:
    from werkzeug.security import check_password_hash
    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# User / session helpers
# ---------------------------------------------------------------------------

def create_user(email: str, username: str, password: str):
    pw_hash = hash_password(password)
    if USE_POSTGRES:
        rows = pg_run(
            "INSERT INTO users (email, username, password_hash) VALUES ($1, $2, $3) RETURNING id",
            [email, username, pw_hash]
        )
        return rows[0]['id'] if rows else None
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, username, password_hash) VALUES (?, ?, ?)",
            (email, username, pw_hash)
        )
        conn.commit()
        user_id = cur.lastrowid
        conn.close()
        return user_id


def create_session(user_id: int) -> str:
    token = generate_token()
    if USE_POSTGRES:
        pg_run(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES ($1, $2, NOW() + '30 days'::interval)",
            [user_id, token]
        )
    else:
        conn = get_db()
        conn.execute(
            "INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, datetime('now', '+30 days'))",
            (user_id, token)
        )
        conn.commit()
        conn.close()
    return token


def get_user_by_token(token: str):
    if USE_POSTGRES:
        rows = pg_run(
            """SELECT u.id, u.email, u.username, u.plan, u.generations_this_month,
                      u.last_reset_month, u.is_admin, u.is_active
               FROM users u
               JOIN sessions s ON s.user_id = u.id
               WHERE s.token = $1 AND s.expires_at > NOW()""",
            [token]
        )
        return rows[0] if rows else None
    else:
        conn = get_db()
        row = conn.execute(
            """SELECT u.id, u.email, u.username, u.plan, u.generations_this_month,
                      u.last_reset_month, u.is_admin, u.is_active
               FROM users u
               JOIN sessions s ON s.user_id = u.id
               WHERE s.token = ? AND s.expires_at > datetime('now')""",
            (token,)
        ).fetchone()
        conn.close()
        return row_to_dict(row)


def get_user_by_id(user_id: int):
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, email, username, plan, generations_this_month, last_reset_month, is_admin, is_active FROM users WHERE id = $1",
            [user_id]
        )
        return rows[0] if rows else None
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT id, email, username, plan, generations_this_month, last_reset_month, is_admin, is_active FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        return row_to_dict(row)


def log_generation(user_id: int, tool_name: str):
    if USE_POSTGRES:
        pg_run(
            "INSERT INTO generation_logs (user_id, tool_name) VALUES ($1, $2)",
            [user_id, tool_name]
        )
        pg_run(
            "UPDATE users SET generations_this_month = generations_this_month + 1 WHERE id = $1",
            [user_id]
        )
    else:
        conn = get_db()
        conn.execute(
            "INSERT INTO generation_logs (user_id, tool_name) VALUES (?, ?)",
            (user_id, tool_name)
        )
        conn.execute(
            "UPDATE users SET generations_this_month = generations_this_month + 1 WHERE id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()


def get_monthly_count(user_id: int) -> int:
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT generations_this_month FROM users WHERE id = $1",
            [user_id]
        )
        return rows[0]['generations_this_month'] if rows else 0
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT generations_this_month FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        return row_to_dict(row)['generations_this_month'] if row else 0


def maybe_reset_monthly_count(user_id: int, current_month: str):
    """Reset generations_this_month to 0 if we're in a new month."""
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT last_reset_month FROM users WHERE id = $1",
            [user_id]
        )
        last = rows[0]['last_reset_month'] if rows else ''
        if last != current_month:
            pg_run(
                "UPDATE users SET generations_this_month = 0, last_reset_month = $1 WHERE id = $2",
                [current_month, user_id]
            )
            print(f"[DB] Reset monthly count for user {user_id} (new month: {current_month})")
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT last_reset_month FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        last = row_to_dict(row)['last_reset_month'] if row else ''
        if last != current_month:
            conn.execute(
                "UPDATE users SET generations_this_month = 0, last_reset_month = ? WHERE id = ?",
                (current_month, user_id)
            )
            conn.commit()
        conn.close()


def require_auth():
    """Extract and validate Bearer token from Authorization header."""
    from flask import request as freq
    auth = freq.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        return get_user_by_token(token)
    except Exception as e:
        print(f"[Auth] require_auth error: {e}")
        _tb.print_exc()
        return None


# ---------------------------------------------------------------------------
# User Defaults
# ---------------------------------------------------------------------------

def get_defaults(user_id: int) -> dict:
    if USE_POSTGRES:
        import json as _json
        rows = pg_run(
            "SELECT defaults_data FROM user_defaults WHERE user_id = $1",
            [user_id]
        )
        if not rows:
            return {}
        raw = rows[0]['defaults_data']
        if isinstance(raw, dict):
            return raw
        try:
            return _json.loads(raw)
        except Exception:
            return {}
    else:
        import json as _json
        conn = get_db()
        row = conn.execute(
            "SELECT defaults_data FROM user_defaults WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        if not row:
            return {}
        d = row_to_dict(row)
        raw = d.get('defaults_data', '{}')
        try:
            return _json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            return {}


def save_defaults(user_id: int, new_data: dict) -> dict:
    import json as _json
    # Merge new data into existing
    existing = get_defaults(user_id)
    merged = {**existing, **new_data}

    if USE_POSTGRES:
        pg_run(
            """INSERT INTO user_defaults (user_id, defaults_data, updated_at)
               VALUES ($1, $2::jsonb, NOW())
               ON CONFLICT (user_id) DO UPDATE
               SET defaults_data = $2::jsonb, updated_at = NOW()""",
            [user_id, _json.dumps(merged)]
        )
    else:
        conn = get_db()
        conn.execute(
            """INSERT OR REPLACE INTO user_defaults (user_id, defaults_data, updated_at)
               VALUES (?, ?, datetime('now'))""",
            (user_id, _json.dumps(merged))
        )
        conn.commit()
        conn.close()
    return merged


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def save_draft(user_id: int, tool_name: str, title: str, result: str) -> int:
    if USE_POSTGRES:
        rows = pg_run(
            "INSERT INTO drafts (user_id, tool_name, title, result) VALUES ($1, $2, $3, $4) RETURNING id",
            [user_id, tool_name, title, result]
        )
        return rows[0]['id'] if rows else None
    else:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO drafts (user_id, tool_name, title, result) VALUES (?, ?, ?, ?)",
            (user_id, tool_name, title, result)
        )
        conn.commit()
        draft_id = cur.lastrowid
        conn.close()
        return draft_id


def get_drafts(user_id: int):
    if USE_POSTGRES:
        return pg_run(
            "SELECT id, tool_name, title, created_at FROM drafts WHERE user_id = $1 ORDER BY created_at DESC",
            [user_id]
        )
    else:
        conn = get_db()
        rows = conn.execute(
            "SELECT id, tool_name, title, created_at FROM drafts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        conn.close()
        return [row_to_dict(r) for r in rows]


def get_draft_by_id(user_id: int, draft_id: int):
    if USE_POSTGRES:
        rows = pg_run(
            "SELECT id, tool_name, title, result, created_at FROM drafts WHERE id = $1 AND user_id = $2",
            [draft_id, user_id]
        )
        return rows[0] if rows else None
    else:
        conn = get_db()
        row = conn.execute(
            "SELECT id, tool_name, title, result, created_at FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id)
        ).fetchone()
        conn.close()
        return row_to_dict(row)


def delete_draft(user_id: int, draft_id: int) -> bool:
    if USE_POSTGRES:
        pg_run(
            "DELETE FROM drafts WHERE id = $1 AND user_id = $2",
            [draft_id, user_id]
        )
    else:
        conn = get_db()
        conn.execute(
            "DELETE FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id)
        )
        conn.commit()
        conn.close()
    return True


if __name__ == '__main__':
    init_db()
