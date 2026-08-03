# python-backend/factory.py (Updated for Redis Pub/Sub)

import logging
from urllib.parse import urlparse

from flask import Flask, request

# --- Local Module Imports ---
import config
from extensions import socketio, oauth, RedisClient

# --- Service Layer Imports ---
from session_service import ConnectionManager
from run_state_manager import RunStateManager

# --- Route and Handler Registration Imports ---
from auth import auth_bp
from api import api_bp
import sockets 

logger = logging.getLogger(__name__)


def _is_allowed_origin(origin):
    if not origin:
        return False
    if origin in config.ALLOWED_CORS_ORIGINS:
        return True
    parsed = urlparse(origin)
    hostname = parsed.hostname or ""
    if parsed.scheme in {"http", "https"} and hostname in {"localhost", "127.0.0.1"}:
        return True
    return any(hostname.endswith(suffix) for suffix in config.ALLOWED_CORS_SUFFIXES)

# ==============================================================================
# APPLICATION FACTORY
# ==============================================================================

def create_app():
    """
    Creates and configures the Flask application and its extensions.
    """
    app = Flask(__name__)
    app.secret_key = config.FLASK_SECRET_KEY

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if _is_allowed_origin(origin):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Vary'] = 'Origin'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

    # --- 1. Initialize Extensions ---
    # Flask 3.x + some Flask-SocketIO builds can error when SocketIO tries to
    # assign to request context session. We don't rely on Flask session in
    # socket handlers (token auth is used), so disable SocketIO session
    # management explicitly.
    socketio.init_app(app, manage_session=False)
    oauth.init_app(app)

    from extensions import limiter
    limiter.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return {"ok": False, "error": f"Rate limit exceeded: {e.description}"}, 429
    
    # --- 2. Instantiate Services ---
    redis_client = RedisClient.from_url(config.REDIS_URL)
    connection_manager = ConnectionManager(redis_client)
    run_state_manager = RunStateManager(redis_client)

    # --- 3. Inject Dependencies into Modules ---
    # Pass connection_manager, redis_client, and run_state_manager to the sockets module.
    sockets.set_dependencies(
        manager=connection_manager,
        redis_client=redis_client,
        run_state_mgr=run_state_manager,
    )

    # --- 4. Register OAuth Providers ---
    # (This section is unchanged)
    if config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET:
        oauth.register(
            name='github', client_id=config.GITHUB_CLIENT_ID, client_secret=config.GITHUB_CLIENT_SECRET,
            access_token_url='https://github.com/login/oauth/access_token', authorize_url='https://github.com/login/oauth/authorize',
            api_base_url='https://api.github.com/', client_kwargs={'scope': 'repo user:email'}
        )
        logger.info("GitHub OAuth provider registered.")
    else:
        logger.warning("GitHub OAuth credentials not set. GitHub integration will be disabled.")

    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
        oauth.register(
            name='google', client_id=config.GOOGLE_CLIENT_ID, client_secret=config.GOOGLE_CLIENT_SECRET,
            authorize_url='https://accounts.google.com/o/oauth2/auth', access_token_url='https://accounts.google.com/o/oauth2/token',
            api_base_url='https://www.googleapis.com/oauth2/v1/',
            client_kwargs={'scope': 'https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets', 'access_type': 'offline', 'prompt': 'consent'}
        )
        logger.info("Google OAuth provider registered.")
    else:
        logger.warning("Google OAuth credentials not set. Google integration will be disabled.")

    if config.VERCEL_CLIENT_ID and config.VERCEL_CLIENT_SECRET:
        oauth.register(
            name='vercel', client_id=config.VERCEL_CLIENT_ID, client_secret=config.VERCEL_CLIENT_SECRET,
            access_token_url='https://api.vercel.com/v2/oauth/access_token', authorize_url='https://vercel.com/oauth/authorize',
            api_base_url='https://api.vercel.com/', client_kwargs={'scope': 'users:read teams:read projects:read deployments:read'}
        )
        logger.info("Vercel OAuth provider registered.")
    else:
        logger.warning("Vercel OAuth credentials not set. Vercel integration will be disabled.")

    if config.SUPABASE_CLIENT_ID and config.SUPABASE_CLIENT_SECRET:
        oauth.register(
            name='supabase', client_id=config.SUPABASE_CLIENT_ID, client_secret=config.SUPABASE_CLIENT_SECRET,
            access_token_url='https://api.supabase.com/v1/oauth/token', authorize_url='https://api.supabase.com/v1/oauth/authorize',
            api_base_url='https://api.supabase.com/v1/', client_kwargs={'scope': 'organizations:read projects:read'}
        )
        logger.info("Supabase OAuth provider registered.")
    else:
        logger.warning("Supabase OAuth credentials not set. Supabase integration will be disabled.")

    # --- 5. Register Blueprints (HTTP Routes) ---
    # Inject run_state_manager into api so the status endpoints can read it
    from api import set_run_state_manager
    set_run_state_manager(run_state_manager)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    # --- 6. Start Background Task Poller ---
    from task_poller import start_task_poller
    start_task_poller(poll_interval=60)
    logger.info("Task poller started (checks every 60s for scheduled tasks)")

    return app
