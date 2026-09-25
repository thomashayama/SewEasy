"""Environment-driven configuration for the web-service layer"""

import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

# --- Database ---
# Default: local SQLite file for dependency-free development.
# Railway/Heroku-style managed Postgres injects postgres:// URLs. Name the
# driver that is installed (psycopg2-binary): a bare postgresql:// means
# whatever SQLAlchemy's default is, and 2.1 switched that to psycopg 3.
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/seweasy.db')
for _scheme in ('postgres://', 'postgresql://'):
    if DATABASE_URL.startswith(_scheme):
        DATABASE_URL = 'postgresql+psycopg2://' + DATABASE_URL[len(_scheme):]

# --- App location ---
APP_URL = os.getenv('APP_URL', 'http://localhost:8080').rstrip('/')
SECURE_COOKIES = APP_URL.startswith('https')

# --- Google OAuth ---
# Bare `python gui.py` launches do not inherit docker-compose's .env values.
# Read local OAuth defaults here, with explicit environment values taking
# precedence. Keep database and session settings environment-driven: restoring
# local sign-in must not rotate an existing session key or change its database.
_local_auth = dotenv_values(Path(__file__).resolve().parents[1] / '.env')


def _auth_setting(name, default=''):
    return os.getenv(name, _local_auth.get(name) or default)


GOOGLE_AUTHORIZE_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

GOOGLE_CLIENT_ID = _auth_setting('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = _auth_setting('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = _auth_setting('GOOGLE_REDIRECT_URI', f'{APP_URL}/auth/callback')
GOOGLE_SCOPE = _auth_setting('GOOGLE_SCOPE', 'openid email profile')


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
