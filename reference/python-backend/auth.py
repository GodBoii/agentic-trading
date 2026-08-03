# python-backend/auth.py

import html
import json
import logging
import requests
from flask import Blueprint, request, url_for, session

import config
from extensions import oauth
from gotrue.errors import AuthApiError
from supabase_client import supabase_client
from cache_manager import CacheManager

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth_bp', __name__)


def _oauth_callback_page(*, success, provider, message, close_delay_ms):
    provider_label = html.escape(provider.capitalize())
    frontend_origin = json.dumps(config.FRONTEND_URL)
    payload = json.dumps({
        "type": "oauth-callback",
        "success": success,
        "provider": provider,
        **({} if success else {"error": "Authentication failed"}),
    })
    title = "Authentication Successful" if success else "Authentication Failed"
    heading = "Authentication Successful!" if success else "Authentication Failed"
    icon = "&#10003;" if success else "&#10007;"
    background = "#667eea" if success else "#f5576c"
    body_message = html.escape(message.format(provider=provider_label))

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                background: {background};
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
            }}
            .status-icon {{
                font-size: 4rem;
                margin-bottom: 1rem;
            }}
            h1 {{
                margin: 0 0 0.5rem 0;
                font-size: 1.5rem;
            }}
            p {{
                margin: 0.5rem 0;
                opacity: 0.9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-icon">{icon}</div>
            <h1>{heading}</h1>
            <p>{body_message}</p>
            <p>This window will close automatically...</p>
        </div>
        <script>
            if (window.opener) {{
                window.opener.postMessage({payload}, {frontend_origin});
            }}
            setTimeout(function() {{
                window.close();
            }}, {close_delay_ms});
        </script>
    </body>
    </html>
    """


@auth_bp.route('/login/<provider>')
def login_provider(provider):
    """
    Initiates the OAuth login flow for a configured provider.
    """
    if provider not in oauth._clients:
        return "Invalid or unconfigured provider specified.", 404

    token = request.args.get('token')
    if not token:
        return "Authentication token is missing.", 400

    session['supabase_token'] = token
    redirect_uri = url_for('auth_bp.auth_callback', provider=provider, _external=True)

    if provider == 'google':
        return oauth.google.authorize_redirect(redirect_uri, access_type='offline', prompt='consent')

    return oauth.create_client(provider).authorize_redirect(redirect_uri)


@auth_bp.route('/auth/<provider>/callback')
def auth_callback(provider):
    """
    Handles the OAuth callback and stores the integration tokens for the user.
    """
    if provider not in oauth._clients:
        return "Invalid or unconfigured provider specified.", 404

    try:
        if provider == 'vercel':
            code = request.args.get('code')
            if not code:
                return "Vercel authorization code is missing.", 400

            token_response = requests.post(
                'https://api.vercel.com/v2/oauth/access_token',
                data={
                    'client_id': config.VERCEL_CLIENT_ID,
                    'client_secret': config.VERCEL_CLIENT_SECRET,
                    'code': code,
                    'redirect_uri': url_for('auth_bp.auth_callback', provider='vercel', _external=True),
                },
            )
            token_response.raise_for_status()
            token = token_response.json()

            user_info_response = requests.get(
                'https://api.vercel.com/v2/user',
                headers={'Authorization': f"Bearer {token['access_token']}"},
            )
            user_info_response.raise_for_status()
            vercel_user_email = user_info_response.json()['user']['email']

            user_lookup = supabase_client.from_('profiles').select('id').eq('email', vercel_user_email).single().execute()
            if not user_lookup.data:
                return "Error: Could not find a user in our system with the Vercel email address.", 400
            user_id = user_lookup.data['id']
        else:
            supabase_token = session.get('supabase_token')
            if not supabase_token:
                return "Your session has expired. Please try logging in again.", 400

            user = supabase_client.auth.get_user(jwt=supabase_token).user
            if not user:
                raise AuthApiError("User not found for token.", 401)
            user_id = user.id

            client = oauth.create_client(provider)
            token = client.authorize_access_token()

        if not user_id:
            return "Could not identify the user.", 400

        integration_data = {
            'user_id': str(user_id),
            'service': provider,
            'access_token': token.get('access_token'),
            'refresh_token': token.get('refresh_token'),
            'scopes': token.get('scope', '').split(' '),
        }
        integration_data = {k: v for k, v in integration_data.items() if v is not None}

        supabase_client.from_('user_integrations').upsert(integration_data).execute()
        CacheManager.delete(f"cache:integrations:{user_id}")
        logger.info("Supabase: Saved %s integration", provider)

        return _oauth_callback_page(
            success=True,
            provider=provider,
            message="You have successfully connected your {provider} account.",
            close_delay_ms=1500,
        )

    except Exception as e:
        logger.error("%s auth error: %s", provider, e)
        return _oauth_callback_page(
            success=False,
            provider=provider,
            message="An error occurred during authentication.",
            close_delay_ms=2000,
        )
