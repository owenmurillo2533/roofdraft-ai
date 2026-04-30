import os

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def auth_user_or_ip():
    from database.db import require_auth

    user = require_auth()
    if user and user.get("id"):
        return f"user:{user['id']}"
    return f"ip:{get_remote_address()}"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)


def register_limit_handlers(app):
    @app.errorhandler(429)
    def rate_limit_handler(error):
        return jsonify({"error": "Too many requests. Please wait before trying again."}), 429
