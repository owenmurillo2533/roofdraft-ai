"""
RoofDraftAI - Flask Application Server
"""

import os
import sys
import json
from flask import Flask, request, jsonify, send_from_directory

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

app = Flask(__name__, static_folder='static')
_debug_enabled = os.environ.get('DEBUG', 'false').lower() == 'true'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or (
    'roofdraft-dev-secret-change-in-production' if _debug_enabled else os.urandom(32).hex()
)
DEFAULT_ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGINS', 'https://roofdraftai.com')
EXPOSE_DIAGNOSTICS = os.environ.get('EXPOSE_DIAGNOSTICS', 'false').lower() == 'true'

sys.path.insert(0, os.path.dirname(__file__))

from database.db import init_db, USE_POSTGRES, pg_run
init_db()

# Startup migrations
if USE_POSTGRES:
    _startup_sqls = [
        "UPDATE users SET is_admin=TRUE, plan='pro' WHERE email='owen.murillo2533@gmail.com'",
        "UPDATE users SET plan='pro' WHERE email='z.oncale.t@gmail.com'",
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
try:
    from routes.stripe import stripe_bp
    _stripe_bp_loaded = True
except Exception as _e:
    print(f'[App] WARNING: Failed to load stripe blueprint: {_e}')
    _stripe_bp_loaded = False

app.register_blueprint(auth_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(drafts_bp)
app.register_blueprint(defaults_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(folders_bp)
app.register_blueprint(contact_bp)
if _stripe_bp_loaded:
    app.register_blueprint(stripe_bp)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = DEFAULT_ALLOWED_ORIGIN
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response


@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        from flask import make_response
        r = make_response()
        r.headers['Access-Control-Allow-Origin'] = DEFAULT_ALLOWED_ORIGIN
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return r


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

@app.route('/robots.txt')
def robots_txt():
    return send_from_directory(app.static_folder, 'robots.txt')


@app.route('/sitemap.xml')
def sitemap_xml():
    return send_from_directory(app.static_folder, 'sitemap.xml')


@app.route('/terms')
def terms_page():
    return send_from_directory(app.static_folder, 'terms.html')


@app.route('/privacy')
def privacy_page():
    return send_from_directory(app.static_folder, 'privacy.html')


@app.route('/sample-proposal')
def sample_proposal_page():
    return send_from_directory(app.static_folder, 'sample-proposal.html')


@app.route('/sample-proposal.pdf')
def sample_proposal_pdf():
    return send_from_directory(app.static_folder, 'sample-proposal.pdf')

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
    payload = {
        'status': 'ok',
        'service': 'RoofDraftAI',
        'version': '2.1.0',
        'db_mode': 'postgres' if USE_POSTGRES else 'sqlite',
    }
    if EXPOSE_DIAGNOSTICS:
        env_vars = ['ANTHROPIC_API_KEY', 'DATABASE_URL', 'SECRET_KEY', 'DEBUG',
                    'STRIPE_SECRET_KEY', 'STRIPE_STARTER_PRICE_ID', 'STRIPE_PRO_PRICE_ID',
                    'STRIPE_WEBHOOK_SECRET', 'YOUR_DOMAIN']
        payload['env'] = {k: bool(os.environ.get(k)) for k in env_vars}
    return jsonify(payload)


@app.route('/api/debug-db')
def debug_db():
    if not EXPOSE_DIAGNOSTICS:
        return jsonify({'error': 'Not found'}), 404
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
    if not EXPOSE_DIAGNOSTICS:
        return jsonify({'error': 'Not found'}), 404
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"})
    try:
        import urllib.request, urllib.error
        payload = json.dumps({
            "model": "claude-sonnet-4-6",
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
    debug = _debug_enabled
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
