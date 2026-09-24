"""Database models.

Identity is keyed on the verified Google email (no separate user id),
mirroring the pattern proven out in Rivulet_Server.
"""

from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
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
    wardrobe = relationship('WardrobeLibrary', back_populates='owner',
                            cascade='all, delete-orphan', uselist=False)


class OAuthState(Base):
    """Short-lived single-use CSRF state tokens for the OAuth flow"""
    __tablename__ = 'oauth_states'

    state = Column(String, primary_key=True)
    # Indexed: every login sweeps expired states by created_at
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False,
                        index=True)


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
    shares = relationship('BodyProfileShare', back_populates='profile',
                          cascade='all, delete-orphan')


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
    shares = relationship('DesignShare', back_populates='design',
                          cascade='all, delete-orphan')


class WardrobeLibrary(Base):
    """Named garments and outfits with independent appearance snapshots."""
    __tablename__ = 'wardrobe_libraries'
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), primary_key=True)
    content = Column(JSON, nullable=False)
    owner = relationship('User', back_populates='wardrobe')


class AgentToken(Base):
    """Revocable personal access: only a SHA-256 digest is retained."""
    __tablename__ = 'agent_tokens'
    id = Column(String, primary_key=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, nullable=False)
    digest = Column(String, nullable=False, unique=True)
    prefix = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)


class BaseGarment(TimestampMixin, Base):
    """Reusable private construction template; saved garments embed its data."""
    __tablename__ = 'base_garments'
    __table_args__ = (UniqueConstraint('owner_email', 'name', name='uq_base_garment_name'),)
    id = Column(String, primary_key=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False, default='')
    params = Column(JSON, nullable=False)
    appearance = Column(JSON, nullable=False)
    files = deferred(Column(JSON, nullable=False))


class Fabric(TimestampMixin, Base):
    """Private reusable fabric; source bytes stay separate from editable values."""
    __tablename__ = 'fabrics'
    __table_args__ = (UniqueConstraint('owner_email', 'name', name='uq_fabric_owner_name'),)
    id = Column(String, primary_key=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    name = Column(String, nullable=False)
    content = Column(JSON, nullable=False)
    # Opaque optimistic-lock token, not a user-visible version/history.
    edit_token = Column(String, nullable=False)
    source_name = Column(String)
    source_bytes = deferred(Column(LargeBinary))


class AgentRender(Base):
    """Expiring draft artifacts; browser output attaches to the original item."""
    __tablename__ = 'agent_renders'
    id = Column(String, primary_key=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String, nullable=False)
    item_id = Column(String, nullable=False)
    items = deferred(Column(JSON, nullable=False))
    state = Column(String, nullable=False)
    error = Column(Text)
    expires_at = Column(DateTime, nullable=False, index=True)
    scene = deferred(Column(LargeBinary))
    svg = deferred(Column(Text))
    png = deferred(Column(LargeBinary))
    thumbnail = deferred(Column(Text))


class WardrobeShare(TimestampMixin, Base):
    """The access record of one garment, outfit, fabric or body profile.

    The table name dates from when only wardrobe items could be shared; see
    webapp/access.py for the model. revision_id is the item's stable ID (a
    legacy column name), stored as text for every kind. No record means
    private: one is created the first time the owner opens sharing.
    """
    __tablename__ = 'wardrobe_shares'
    __table_args__ = (UniqueConstraint('owner_key', 'kind', 'revision_id', name='uq_wardrobe_share_revision'),)
    id = Column(String, primary_key=True)  # Unguessable capability for link access.
    owner_key = Column(String, nullable=False, index=True)
    owner_name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    revision_id = Column(String, nullable=False)
    snapshot = Column(JSON, nullable=False)
    thumbnail = deferred(Column(Text))
    public_link = Column(Boolean, nullable=False, default=False)
    # NULL preserves legacy private/unlisted links; existing links are never
    # promoted into public discovery by a migration.
    visibility = Column(String)
    invitations = relationship('WardrobeInvitation', cascade='all, delete-orphan', back_populates='share')


class WardrobeInvitation(Base):
    """A member of an access record: a viewer or an admin, never the owner.

    Membership appears when the recipient signs in with this verified email.
    """
    __tablename__ = 'wardrobe_invitations'
    __table_args__ = (UniqueConstraint('share_id', 'recipient_email', name='uq_wardrobe_invitation'),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    share_id = Column(String, ForeignKey('wardrobe_shares.id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_email = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False, default='viewer', server_default='viewer')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    share = relationship('WardrobeShare', back_populates='invitations')


class Friendship(TimestampMixin, Base):
    """One relationship per unordered email pair; acceptance is bilateral."""
    __tablename__ = 'friendships'
    __table_args__ = (UniqueConstraint('email_a', 'email_b', name='uq_friendship_pair'),)
    id = Column(String, primary_key=True)
    email_a = Column(String, nullable=False, index=True)
    email_b = Column(String, nullable=False, index=True)
    requester_email = Column(String, nullable=False)
    status = Column(String, nullable=False, default='pending')


class WardrobeFavorite(TimestampMixin, Base):
    __tablename__ = 'wardrobe_favorites'
    __table_args__ = (UniqueConstraint('owner_email', 'kind', 'item_id', name='uq_wardrobe_favorite'),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String, nullable=False)  # garment, outfit, or permission-checked share
    item_id = Column(String, nullable=False)


class FinishedPhoto(TimestampMixin, Base):
    """Real finished-piece photos belong to one stable garment/outfit ID."""
    __tablename__ = 'finished_photos'
    id = Column(String, primary_key=True)
    owner_email = Column(String, ForeignKey('users.email', ondelete='CASCADE'), nullable=False, index=True)
    kind = Column(String, nullable=False)
    item_id = Column(String, nullable=False, index=True)
    caption = Column(String, nullable=False, default='')
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    image = deferred(Column(LargeBinary, nullable=False))


class BodyProfileShare(Base):
    """Legacy read access to a body profile, emptied into viewer members of
    the unified access records at startup (webapp.access).

    The recipient is keyed on their (lowercased) email rather than a User
    FK, so an item can be shared with someone before their first sign-in;
    the share shows up once they authenticate with that address.
    """
    __tablename__ = 'body_profile_shares'
    __table_args__ = (UniqueConstraint('profile_id', 'recipient_email',
                                       name='uq_body_profile_shares'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer,
                        ForeignKey('body_profiles.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    recipient_email = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    profile = relationship('BodyProfile', back_populates='shares')


class DesignShare(Base):
    """Read access to a design granted to another user (see BodyProfileShare
    for the email-keyed recipient rationale)."""
    __tablename__ = 'design_shares'
    __table_args__ = (UniqueConstraint('design_id', 'recipient_email',
                                       name='uq_design_shares'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    design_id = Column(Integer,
                       ForeignKey('designs.id', ondelete='CASCADE'),
                       nullable=False, index=True)
    recipient_email = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    design = relationship('Design', back_populates='shares')
