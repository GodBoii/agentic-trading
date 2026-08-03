# python-backend/config.py

import os
from dotenv import load_dotenv
from urllib.parse import urlparse

# Load environment variables from a .env file
load_dotenv()

# --- Core Application Configuration ---
REDIS_URL = os.getenv('REDIS_URL')
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
SANDBOX_API_URL = os.getenv("SANDBOX_API_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_POOLER_URL = os.getenv("DATABASE_POOLER_URL") or os.getenv("SUPABASE_DB_POOLER_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _split_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


def _origin_from_url(url):
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _default_cors_origins():
    origins = {
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "https://localhost",
        "capacitor://localhost",
        "ionic://localhost",
        "https://api.aetheriaai.website",
        "https://api.aetheriaai.online",
        "https://aetheria-ai-website.vercel.app",
        "https://aetheriaai.website",
        "https://www.aetheriaai.website",
    }
    frontend_origin = _origin_from_url(FRONTEND_URL)
    if frontend_origin:
        origins.add(frontend_origin)
    return sorted(origins)


ALLOWED_CORS_ORIGINS = sorted(set(_default_cors_origins()) | set(_split_csv(os.getenv("ALLOWED_CORS_ORIGINS"))))
ALLOWED_CORS_SUFFIXES = _split_csv(
    os.getenv(
        "ALLOWED_CORS_SUFFIXES",
        ".api.aetheriaai.website,.api.aetheriaai.online,.aetheriaai.website",
    )
)

# --- LLM Provider Keys (Handled automatically by Agno, listed here for clarity) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # For Google Search, also auto-detected
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
AGNO_DEBUG_MODE = os.getenv("AGNO_DEBUG_MODE", "false").lower() == "true"
SYSTEM_ASSISTANT_DEBUG_MODE = (
    os.getenv("SYSTEM_ASSISTANT_DEBUG_MODE", "true").lower() == "true"
)

# --- OAuth Provider Credentials (Optional) ---
# These can be None if not set in the .env file. The factory will handle this.
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

VERCEL_CLIENT_ID = os.getenv("VERCEL_CLIENT_ID")
VERCEL_CLIENT_SECRET = os.getenv("VERCEL_CLIENT_SECRET")

SUPABASE_CLIENT_ID = os.getenv("SUPABASE_CLIENT_ID")
SUPABASE_CLIENT_SECRET = os.getenv("SUPABASE_CLIENT_SECRET")

# --- Composio Configuration (Optional) ---
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_PROJECT_ID = os.getenv("COMPOSIO_PROJECT_ID")
COMPOSIO_BASE_URL = os.getenv("COMPOSIO_BASE_URL") or "https://backend.composio.dev/api/v3"
COMPOSIO_GOOGLESHEETS_AUTH_CONFIG_ID = os.getenv("COMPOSIO_GOOGLESHEETS_AUTH_CONFIG_ID")
COMPOSIO_WHATSAPP_AUTH_CONFIG_ID = os.getenv("COMPOSIO_WHATSAPP_AUTH_CONFIG_ID")
COMPOSIO_ENABLE_GOOGLE_SHEETS = os.getenv("COMPOSIO_ENABLE_GOOGLE_SHEETS", "false").lower() == "true"
COMPOSIO_ENABLE_WHATSAPP = os.getenv("COMPOSIO_ENABLE_WHATSAPP", "false").lower() == "true"

# --- Deploy Platform Configuration (AI app hosting) ---
DEPLOY_DOMAIN = os.getenv("DEPLOY_DOMAIN")
R2_SITES_BUCKET = os.getenv("R2_SITES_BUCKET")
TURSO_API_TOKEN = os.getenv("TURSO_API_TOKEN")
TURSO_ORG_SLUG = os.getenv("TURSO_ORG_SLUG")
TURSO_GROUP = os.getenv("TURSO_GROUP")
DEPLOY_SECRET_KEY = os.getenv("DEPLOY_SECRET_KEY")

# --- Convex Usage Logging Configuration ---
# Prefer backend-specific key, but support common frontend/public key names too.
CONVEX_URL = (
    os.getenv("CONVEX_URL")
    or os.getenv("VITE_CONVEX_URL")
    or os.getenv("NEXT_PUBLIC_CONVEX_URL")
)
CONVEX_ADMIN_KEY = os.getenv("CONVEX_ADMIN_KEY")
CONVEX_USAGE_ENABLED = os.getenv("CONVEX_USAGE_ENABLED", "true").lower() == "true"
USAGE_ADMIN_API_KEY = os.getenv("USAGE_ADMIN_API_KEY")

# --- Razorpay Subscription Configuration ---
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
PRO_PLAN_ID = os.getenv("PRO_PLAN_ID")
ELITE_PLAN_ID = os.getenv("ELITE_PLAN_ID")
RAZORPAY_SUBSCRIPTION_TOTAL_COUNT = _int_env("RAZORPAY_SUBSCRIPTION_TOTAL_COUNT", 120)
RAZORPAY_SUBSCRIPTION_MAX_TOTAL_COUNT = _int_env("RAZORPAY_SUBSCRIPTION_MAX_TOTAL_COUNT", 120)
RAZORPAY_SUBSCRIPTION_AUTH_EXPIRE_MINUTES = _int_env("RAZORPAY_SUBSCRIPTION_AUTH_EXPIRE_MINUTES", 60)
RAZORPAY_INCOMPLETE_SUBSCRIPTION_GRACE_SECONDS = _int_env("RAZORPAY_INCOMPLETE_SUBSCRIPTION_GRACE_SECONDS", 300)
RAZORPAY_SUBSCRIPTION_CHANGE_MODE = os.getenv("RAZORPAY_SUBSCRIPTION_CHANGE_MODE", "cycle_end").strip().lower()

# --- Celery Configuration ---
CELERY_CONFIG = {
    'broker_url': REDIS_URL,
    'result_backend': REDIS_URL
}

# --- Validation for Critical Variables ---
# The application cannot run without these.
if not FLASK_SECRET_KEY:
    raise ValueError("CRITICAL: FLASK_SECRET_KEY must be set in the environment.")
if not DATABASE_URL:
    raise ValueError("CRITICAL: DATABASE_URL must be set in the environment.")
if not REDIS_URL:
    raise ValueError("CRITICAL: REDIS_URL must be set in the environment.")
