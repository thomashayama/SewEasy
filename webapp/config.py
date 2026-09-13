"""Environment-driven configuration for the web-service layer"""

import os
import secrets
from pathlib import Path

# --- Database ---
# Default: local SQLite file for dependency-free development.
# Railway/Heroku-style managed Postgres injects postgres:// URLs; SQLAlchemy
# needs the postgresql:// scheme.
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/seweasy.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# --- App location ---
APP_URL = os.getenv('APP_URL', 'http://localhost:8080').rstrip('/')
SECURE_COOKIES = APP_URL.startswith('https')

# --- Google OAuth ---
GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', f'{APP_URL}/auth/callback')
GOOGLE_SCOPE = os.getenv('GOOGLE_SCOPE', 'openid email profile')


def google_configured() -> bool:
    """Whether sign-in can be offered at all"""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


# --- Session tokens ---
JWT_SECRET = os.getenv('JWT_SECRET', '')
if not JWT_SECRET:
    # Keep guest libraries reachable across local server restarts. Deployments
    # should still provide JWT_SECRET through their environment.
    secret_path = Path(__file__).resolve().parents[1] / 'data' / '.session-secret'
    secret_path.parent.mkdir(exist_ok=True)
    try:
        with secret_path.open('x', encoding='utf-8') as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    JWT_SECRET = secret_path.read_text(encoding='utf-8').strip()
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = 24 * 7
