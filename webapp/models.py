"""Database models.

Identity is keyed on the verified Google email (no separate user id),
mirroring the pattern proven out in Rivulet_Server.
"""

from datetime import datetime

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer, String,
                        UniqueConstraint)
from sqlalchemy.orm import relationship

from webapp.db import Base


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)


class User(TimestampMixin, Base):
    """A Google-authenticated user"""
    __tablename__ = 'users'

    email = Column(String, primary_key=True)
    name = Column(String)
    picture = Column(String)

    body_profiles = relationship('BodyProfile', back_populates='owner',
                                 cascade='all,delete')


class OAuthState(Base):
    """Short-lived single-use CSRF state tokens for the OAuth flow"""
    __tablename__ = 'oauth_states'

    state = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BodyProfile(TimestampMixin, Base):
    """A named set of body measurements owned by a user.

    Measurements are stored as a JSON dict matching the 'body' section of the
    body-parameter YAML files (derived '_'-prefixed values excluded — they are
    recomputed by BodyParameters.eval_dependencies on load).
    """
    __tablename__ = 'body_profiles'
    __table_args__ = (UniqueConstraint('owner_email', 'name',
                                       name='uq_body_profiles_owner_name'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'),
                         nullable=False, index=True)
    name = Column(String, nullable=False)
    measurements = Column(JSON, nullable=False)

    owner = relationship('User', back_populates='body_profiles')
