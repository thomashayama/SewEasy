"""Google OAuth sign-in and JWT cookie sessions.

Flow (adapted from Rivulet_Server):
  GET /auth/login    -> 302 to Google's consent screen (state in DB + cookie)
  GET /auth/callback -> validates state, exchanges code, fetches userinfo
                        (fails closed on unverified email), upserts the User,
                        sets an HttpOnly JWT cookie, redirects to /
  GET /auth/logout   -> clears the cookie, redirects to /
  GET /auth/me       -> current user as JSON (401 if not signed in)

Session enforcement is cookie-based: pages/handlers call current_user(request).
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import requests
from fastapi import Cookie, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import jwt
from jose.exceptions import JWTError

from webapp import config
from webapp.db import SessionLocal
from webapp.models import OAuthState, User

TOKEN_COOKIE = 'token'
STATE_COOKIE = 'oauth_state'
STATE_MAX_AGE = 600  # seconds a login attempt may take


# --- JWT session tokens ---

def create_jwt(email: str, name: str = '', picture: str = '') -> str:
    payload = {
        'sub': email,
        'name': name,
        'picture': picture,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None


def current_user(request: Request) -> Optional[dict]:
    """The signed-in user ({email, name, picture}) or None"""
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        return None
    payload = decode_jwt(token)
    if not payload:
        return None
    return {
        'email': payload['sub'].lower(),
        'name': payload.get('name', ''),
        'picture': payload.get('picture', ''),
    }


# --- Google endpoints ---

def build_login_url(state: str) -> str:
    params = {
        'client_id': config.GOOGLE_CLIENT_ID,
        'redirect_uri': config.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': config.GOOGLE_SCOPE,
        'state': state,
    }
    return f'{config.GOOGLE_AUTHORIZE_URL}?{urlencode(params)}'


def exchange_code(code: str) -> Optional[dict]:
    resp = requests.post(config.GOOGLE_TOKEN_URL, data={
        'code': code,
        'client_id': config.GOOGLE_CLIENT_ID,
        'client_secret': config.GOOGLE_CLIENT_SECRET,
        'redirect_uri': config.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }, timeout=10)
    return resp.json() if resp.status_code == 200 else None


def get_user_info(access_token: str) -> Optional[dict]:
    """Fetch userinfo; returns None unless Google reports the email verified"""
    resp = requests.get(
        config.GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    verified = data.get('email_verified', data.get('verified_email'))
    if isinstance(verified, str):
        verified = verified.strip().lower() == 'true'
    if not verified:
        return None
    return data


# --- Routes ---

def register(app: FastAPI):

    @app.get('/auth/login')
    def login():
        if not config.google_configured():
            return JSONResponse({'error': 'google_oauth_not_configured'},
                                status_code=503)
        state = secrets.token_urlsafe(32)
        with SessionLocal() as db:
            expiry = datetime.utcnow() - timedelta(seconds=STATE_MAX_AGE)
            db.query(OAuthState).filter(OAuthState.created_at < expiry).delete()
            db.add(OAuthState(state=state))
            db.commit()
        response = RedirectResponse(build_login_url(state))
        response.set_cookie(STATE_COOKIE, state, httponly=True,
                            secure=config.SECURE_COOKIES, samesite='lax',
                            max_age=STATE_MAX_AGE)
        return response

    @app.get('/auth/callback')
    def callback(code: str = '', state: str = '', error: str = '',
                 oauth_state: Optional[str] = Cookie(default=None)):

        def fail(reason: str):
            response = RedirectResponse(f'/?auth_error={reason}')
            response.delete_cookie(STATE_COOKIE)
            return response

        if error or not code:
            return fail(error or 'no_code')

        # CSRF: state must match both the HttpOnly cookie and an unused DB row
        if not oauth_state or not state \
                or not secrets.compare_digest(oauth_state, state):
            return fail('invalid_state')
        with SessionLocal() as db:
            row = db.get(OAuthState, state)
            if row is None:
                return fail('invalid_state')
            db.delete(row)
            db.commit()

        token_data = exchange_code(code)
        if not token_data or 'access_token' not in token_data:
            return fail('token_exchange_failed')

        user_info = get_user_info(token_data['access_token'])
        email = (user_info.get('email') or '').lower() if user_info else ''
        if not email:
            return fail('no_verified_email')
        name = user_info.get('given_name') or user_info.get('name') or ''
        picture = user_info.get('picture', '')

        with SessionLocal() as db:
            user = db.get(User, email)
            if user is None:
                db.add(User(email=email, name=name, picture=picture))
            else:
                user.name = name or user.name
                user.picture = picture or user.picture
            db.commit()

        response = RedirectResponse('/')
        response.delete_cookie(STATE_COOKIE)
        response.set_cookie(TOKEN_COOKIE, create_jwt(email, name, picture),
                            httponly=True, secure=config.SECURE_COOKIES,
                            samesite='lax',
                            max_age=config.JWT_EXPIRY_HOURS * 3600)
        return response

    @app.get('/auth/logout')
    def logout():
        response = RedirectResponse('/')
        response.delete_cookie(TOKEN_COOKIE)
        return response

    @app.get('/auth/me')
    def me(request: Request):
        user = current_user(request)
        if user is None:
            return JSONResponse({'error': 'not_authenticated'}, status_code=401)
        return user
