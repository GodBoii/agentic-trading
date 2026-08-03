# python-backend/extensions.py

from flask_socketio import SocketIO
from authlib.integrations.flask_client import OAuth
import redis

# Import the pre-configured Celery app instance instead of creating a new one.
# We import it `as celery` so that other parts of the application that
# were importing `celery` from this file do not need to change.
from celery_app import celery_app as celery
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request
from utils import get_user_from_token
import config

def get_rate_limit_key():
    """
    Determine the rate limit key for the current request.
    If the user is authenticated, use their User ID.
    Otherwise, use the Cloudflare CF-Connecting-IP or X-Forwarded-For header,
    falling back to the remote address.
    """
    # 1. Check for Authenticated User ID
    user, error = get_user_from_token(request)
    if user and not error:
        return f"user:{user.id}"
    
    # 2. Check for Cloudflare/Proxy IP headers
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return f"ip:{cf_ip}"
    
    x_forwarded = request.headers.get("X-Forwarded-For")
    if x_forwarded:
        # X-Forwarded-For can be a comma-separated list; take the first IP
        return f"ip:{x_forwarded.split(',')[0].strip()}"

    # 3. Fallback to default remote address
    return f"ip:{get_remote_address()}"

# Initialize Limiter
limiter = Limiter(
    key_func=get_rate_limit_key,
    # We will configure the storage URL in the factory or directly here
    storage_uri=config.REDIS_URL,
    default_limits=["200 per minute"],  # A safe global fallback
    strategy="fixed-window"
)

# --- Extension Instantiation ---
# These objects are created here in an uninitialized state or imported
# pre-configured. They will be linked to the Flask app in the factory.

# SocketIO: Uninitialized, will be configured in the factory.
# Increased max_http_buffer_size to handle large image payloads (up to 10MB)
socketio = SocketIO(
    cors_allowed_origins=config.ALLOWED_CORS_ORIGINS,
    async_mode="eventlet",
    max_http_buffer_size=10 * 1024 * 1024,  # 10MB limit
    logger=False,  # Disable verbose socket.io logging
    engineio_logger=False  # Disable engine.io logging
)

# OAuth: Uninitialized, will be configured in the factory.
oauth = OAuth()

# Redis: We export the class itself for the factory to instantiate.
RedisClient = redis.Redis
