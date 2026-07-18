"""Database models.

Identity is keyed on the verified Google email (no separate user id),
mirroring the pattern proven out in Rivulet_Server.
"""

from datetime import datetime

from sqlalchemy import (JSON, Column, DateTime, ForeignKey, Integer,
                        LargeBinary, String, Text, UniqueConstraint)
from sqlalchemy.orm import deferred, relationship

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
    # Preferred display units for body measurements ('in' or 'cm');
    # values are always stored in centimeters
    units = Column(String, nullable=False, default='in', server_default='in')

    body_profiles = relationship('BodyProfile', back_populates='owner',
                                 cascade='all,delete')
    designs = relationship('Design', back_populates='owner',
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
    # Display-space '#rrggbb' mannequin skin tone; NULL = default muslin.
    # Kept out of the measurements dict, which feeds BodyParameters as-is.
    skin_color = Column(String)

    owner = relationship('User', back_populates='body_profiles')


class Design(TimestampMixin, Base):
    """A named garment design owned by a user.

    A design is deliberately body-independent: it captures the user's
    choices in the parametric design space (a garment is drafted as
    design x body measurements, so the two are separate entities —
    see BodyProfile for the other half). Params are stored in the same
    self-describing format as the 'design' section of the design-param
    YAML files, so saved designs and file uploads are interchangeable.

    `kind` distinguishes a whole outfit from an individual piece:
    * 'outfit' — full design-parameter snapshot; loading replaces the
      current design
    * 'top' / 'bottom' / 'waistband' — partial snapshot holding only that
      piece's sections (see designs.GARMENT_SECTIONS); loading merges the
      piece into the current outfit, keeping the other pieces
    """
    __tablename__ = 'designs'
    __table_args__ = (UniqueConstraint('owner_email', 'name',
                                       name='uq_designs_owner_name'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'),
                         nullable=False, index=True)
    name = Column(String, nullable=False)
    params = Column(JSON, nullable=False)
    kind = Column(String, nullable=False, default='outfit',
                  server_default='outfit')
    # Pattern-SVG thumbnail captured at save time (NULL for older rows)
    preview = Column(Text)
    # Draped-garment GLB captured when an outfit is saved with a current
    # 3D result; loading the outfit shows it without re-simulating.
    # deferred: listing queries must not drag multi-MB blobs along.
    drape_glb = deferred(Column(LargeBinary))
    # Fabric color the outfit was saved with ('#rrggbb', display space)
    fabric_color = Column(String)

    owner = relationship('User', back_populates='designs')
