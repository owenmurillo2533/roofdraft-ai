"""
RoofDraft — Flask Application Server
"""

import os
import sys
import json
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'roofdraft-dev-secret-change-in-production')

sys.path.insert(0, os.path.dirname(__file__))

from database.db import init_db, USE_POSTGRES, pg_run
init_db()

# Startup migrations
if USE_POSTGRES:
    _startup_sqls = [
        "UPDATE users SET is_admin=TRUE, plan='pro', generations_this_month=0 WHERE email='owen.murillo2533@gmail.com'",
        "UPDATE users SET plan='pro', generations_this_month=0 WHERE email='z.oncale.t@gmail.com'",
    ]
    for _sql in _startup_sqls:
        try:
            pg_run(_sql)
            print(f"[Startup] OK: {_sql[:80]}")
        except Exception as _e:
            print(f"[Startup] Note ({_sql[:60]}): {_e}")

from routes.auth import auth_bp
from routes.tools import tools_bp
from routes.drafts import drafts_bp
from routes.defaults import defaults_bp
from routes.admin import admin_bp
from routes.folders import folders_bp
from routes.contact import contact_bp

app.register_blueprint(auth_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(drafts_bp)
app.register_blueprint(defaults_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(folders_bp)
app.register_blueprint(contact_bp)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = os.environ.get('ALLOWED_ORIGINS', '*')
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        from flask import make_response
        r = make_response()
        r.headers['Access-Control-Allow-Origin'] = '*'
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return r


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

@app.route('/')
@app.route('/<path:path>')
def frontend(path=''):
    if path.startswith('api/') or path.startswith('static/'):
        from flask import abort
        abort(404)
    return send_from_directory(app.static_folder, 'index.html')


# ---------------------------------------------------------------------------
# Debug / health routes
# ---------------------------------------------------------------------------

@app.route('/api/health')
def health():
    env_vars = ['ANTHROPIC_API_KEY', 'DATABASE_URL', 'SECRET_KEY', 'DEBUG', 'STRIPE_SECRET_KEY']
    env_status = {k: bool(os.environ.get(k)) for k in env_vars}
    return jsonify({
        'status': 'ok',
        'service': 'RoofDraft',
        'db_mode': 'postgres' if USE_POSTGRES else 'sqlite',
        'env': env_status,
    })


@app.route('/api/debug-db')
def debug_db():
    if not USE_POSTGRES:
        return jsonify({'error': 'postgres not active'})
    try:
        counts = {}
        for t in ['users', 'sessions', 'generation_logs', 'drafts']:
            try:
                counts[t] = pg_run(f"SELECT COUNT(*) AS cnt FROM {t}")[0]['cnt']
            except Exception as e:
                counts[t] = f'error: {e}'
        return jsonify({'counts': counts})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()})


@app.route('/api/test-claude')
def test_claude():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"})
    try:
        import urllib.request, urllib.error
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Say 'ok'"}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            return jsonify({"success": True, "model_used": data.get("model"), "response": data})
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        return jsonify({"error": f"HTTP {e.code}", "api_error_body": body})
    except Exception as e:
        return jsonify({"error": type(e).__name__, "detail": str(e)})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return send_from_directory(app.static_folder, 'index.html')


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
