"""Account-scoped MCP credentials, independent of browser session cookies."""
from datetime import datetime, timedelta
import hashlib
import secrets
from uuid import uuid4

from webapp.db import SessionLocal
from webapp.models import AgentToken, User


def create(email, name):
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError('Give this connection a name (up to 80 characters).')
    token = 'se_' + secrets.token_urlsafe(36)
    with SessionLocal() as db:
        if db.get(User, email) is None:
            raise ValueError('Sign in before connecting an agent.')
        if db.query(AgentToken).filter_by(owner_email=email, revoked=False).filter(
                AgentToken.expires_at > datetime.utcnow()).count() >= 20:
            raise ValueError('Revoke an unused connection before creating another.')
        row = AgentToken(id=uuid4().hex, owner_email=email, name=name,
                         digest=hashlib.sha256(token.encode()).hexdigest(), prefix=token[:10],
                         expires_at=datetime.utcnow() + timedelta(days=90))
        db.add(row)
        db.commit()
    return token


def authenticate(token):
    if not isinstance(token, str) or not token.startswith('se_') or len(token) > 128:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with SessionLocal() as db:
        row = db.query(AgentToken).filter_by(digest=digest, revoked=False).filter(
            AgentToken.expires_at > datetime.utcnow()).first()
        return row.owner_email if row and db.get(User, row.owner_email) else None


def list_tokens(email):
    with SessionLocal() as db:
        return [dict(id=r.id, name=r.name, prefix=r.prefix, expires_at=r.expires_at.isoformat())
                for r in db.query(AgentToken).filter_by(owner_email=email, revoked=False)
                .filter(AgentToken.expires_at > datetime.utcnow()).order_by(AgentToken.created_at.desc())]


def revoke(email, token_id):
    with SessionLocal() as db:
        db.query(AgentToken).filter_by(id=token_id, owner_email=email).update({'revoked': True})
        db.commit()
