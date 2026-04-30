"""
RoofDraftAI Flask application server.
"""

import os
import sys
import traceback
from datetime import datetime

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from database.db import USE_POSTGRES, get_db, init_db, pg_run
from extensions import limiter, register_limit_handlers
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.contact import contact_bp
from routes.defaults import defaults_bp
from routes.drafts import drafts_bp
from routes.folders import folders_bp
from routes.stripe import stripe_bp
from routes.tools import tools_bp

app = Flask(__name__, static_folder="static")
_debug_enabled = os.environ.get("DEBUG", "false").lower() == "true"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or (
    "roofdraft-dev-secret-change-in-production" if _debug_enabled else os.urandom(32).hex()
)

ALLOWED_ORIGINS = [
    "https://roofdraftai.com",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]
ENV_KEYS = [
    "ANTHROPIC_API_KEY",
    "DATABASE_URL",
    "SECRET_KEY",
    "DEBUG",
    "STRIPE_SECRET_KEY",
    "STRIPE_STARTER_PRICE_ID",
    "STRIPE_PRO_PRICE_ID",
    "YOUR_DOMAIN",
    "STRIPE_WEBHOOK_SECRET",
]

CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
limiter.init_app(app)
register_limit_handlers(app)

init_db()

if USE_POSTGRES:
    startup_sql = [
        "UPDATE users SET is_admin=TRUE, plan='pro' WHERE email='owen.murillo2533@gmail.com'",
    ]
    for sql in startup_sql:
        try:
            pg_run(sql)
        except Exception:
            traceback.print_exc()
else:
    try:
        conn = get_db()
        conn.execute(
            "UPDATE users SET is_admin=1, plan='pro' WHERE email=?",
            ("owen.murillo2533@gmail.com",),
        )
        conn.commit()
        conn.close()
    except Exception:
        traceback.print_exc()

app.register_blueprint(auth_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(drafts_bp)
app.register_blueprint(defaults_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(folders_bp)
app.register_blueprint(contact_bp)
app.register_blueprint(stripe_bp)


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/robots.txt")
def robots_txt():
    return send_from_directory(app.static_folder, "robots.txt")


@app.route("/sitemap.xml")
def sitemap_xml():
    return send_from_directory(app.static_folder, "sitemap.xml")


@app.route("/favicon.svg")
def favicon_svg():
    return send_from_directory(app.static_folder, "favicon.svg")


@app.route("/terms")
def terms_page():
    return send_from_directory(app.static_folder, "terms.html")


@app.route("/privacy")
def privacy_page():
    return send_from_directory(app.static_folder, "privacy.html")


@app.route("/sample-proposal")
def sample_proposal_page():
    return send_from_directory(app.static_folder, "sample-proposal.html")


@app.route("/sample-proposal.pdf")
def sample_proposal_pdf():
    return send_from_directory(app.static_folder, "sample-proposal.pdf")


@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.route("/api/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "RoofDraftAI",
            "db_mode": "postgres" if USE_POSTGRES else "sqlite",
            "env": {key: ("set" if os.environ.get(key) else "not set") for key in ENV_KEYS},
        }
    )


@app.route("/api/debug-db")
def debug_db():
    table_names = [
        "users",
        "sessions",
        "generation_logs",
        "user_defaults",
        "job_folders",
        "saved_drafts",
        "promo_codes",
        "affiliate_commissions",
        "contact_messages",
        "subscription_events",
    ]
    counts = {}
    try:
        if USE_POSTGRES:
            for table_name in table_names:
                counts[table_name] = pg_run(f"SELECT COUNT(*) AS cnt FROM {table_name}")[0]["cnt"]
        else:
            conn = get_db()
            for table_name in table_names:
                row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}").fetchone()
                counts[table_name] = int(row["cnt"]) if row else 0
            conn.close()
        return jsonify({"counts": counts})
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong. Please try again."}), 500


@app.route("/")
@app.route("/<path:path>")
def frontend(path=""):
    if path.startswith("api/") or path.startswith("static/"):
        abort(404)
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    return send_from_directory(app.static_folder, "index.html")


@app.errorhandler(Exception)
def handle_exception(error):
    traceback.print_exc()
    status_code = getattr(error, "code", None)
    if request.path.startswith("/api/"):
        if status_code and 400 <= status_code < 500:
            return jsonify({"error": getattr(error, "description", "Something went wrong. Please try again.")}), status_code
        return jsonify({"error": "Something went wrong. Please try again."}), 500
    if status_code == 404:
        return send_from_directory(app.static_folder, "index.html"), 404
    return send_from_directory(app.static_folder, "index.html"), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=_debug_enabled, threaded=True)
