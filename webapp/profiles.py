"""CRUD for per-user body-measurement profiles.

Profiles follow the shared access model in webapp/access.py: viewers use a
profile and save a copy; admins also edit and delete it; the owner alone can
transfer it.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from webapp import access
from webapp.db import SessionLocal
from webapp.models import BodyProfile, User


def get_units(email: str) -> str:
    """The user's preferred display units ('in' default)"""
    with SessionLocal() as db:
        row = db.get(User, email)
        return row.units if row and row.units in ('in', 'cm') else 'in'


def set_units(email: str, units: str) -> None:
    if units not in ('in', 'cm'):
        return
    with SessionLocal() as db:
        row = db.get(User, email)
        if row is not None:
            row.units = units
            db.commit()


DEFAULT_BODIES = {'all': 'Default body', 'female': 'Default woman', 'male': 'Default man'}


@lru_cache(maxsize=len(DEFAULT_BODIES))
def _default_measurements(name):
    from assets.bodies.body_params import BodyParameters
    if name not in DEFAULT_BODIES:
        raise ValueError('Unknown default body.')
    path = Path(__file__).resolve().parents[1] / 'assets' / 'bodies' / f'mean_{name}.yaml'
    return measurements_from_body(BodyParameters(path))


def default_measurements(name='all') -> dict:
    """A default mannequin's measurements: the neutral average, a woman's, or a man's."""
    return dict(_default_measurements(name))


def measurements_from_body(body_params) -> dict:
    """Extract storable measurements from a BodyParameters object.

    Derived '_'-prefixed values are dropped (recomputed on load); values are
    coerced to float where possible since GUI inputs hold strings.
    """
    result = {}
    for key, value in body_params.params.items():
        if key.startswith('_'):
            continue
        try:
            result[key] = float(value)
        except (TypeError, ValueError):
            result[key] = value
    return result


def list_profiles(email: str) -> list:
    with SessionLocal() as db:
        rows = (db.query(BodyProfile)
                .filter(BodyProfile.owner_email == email)
                .order_by(BodyProfile.updated_at.desc())
                .all())
        return [{'id': r.id, 'name': r.name, 'updated_at': r.updated_at}
                for r in rows]


def shared_profiles(email: str) -> list:
    """Profiles others share with you, as a member or their friend, with your role on each."""
    views = access.Access(email).shared_with_me(('body',))
    with SessionLocal() as db:
        rows = {r.id: r for r in db.query(BodyProfile).filter(
            BodyProfile.id.in_([int(v['revision_id']) for v in views]))} if views else {}
        return [{'id': rows[int(v['revision_id'])].id, 'name': rows[int(v['revision_id'])].name,
                 'updated_at': rows[int(v['revision_id'])].updated_at, 'owner_name': v['owner_name'],
                 'role': v['role'], 'share_id': v['id'], 'is_member': v['is_member']}
                for v in views if int(v['revision_id']) in rows]


def _open(db, email, profile_id, minimum='viewer'):
    """(profile, role) when the caller's role suffices, else (None, role or None)."""
    try:
        row = db.get(BodyProfile, int(profile_id))
    except (TypeError, ValueError):
        row = None
    if row is None:
        return None, None
    current = access.item_role(db, 'body', row.id, email, row.owner_email)
    if access.RANK[current] < access.RANK[minimum]:
        return None, current
    return row, current


def save_profile(email: str, name: str, measurements: dict,
                 skin_color: Optional[str] = None) -> bool:
    """Create or update the profile with this name. Returns True if created"""
    with SessionLocal() as db:
        row = (db.query(BodyProfile)
               .filter(BodyProfile.owner_email == email,
                       BodyProfile.name == name)
               .one_or_none())
        created = row is None
        if created:
            db.add(BodyProfile(owner_email=email, name=name,
                               measurements=measurements,
                               skin_color=skin_color))
        else:
            row.measurements = measurements
            row.skin_color = skin_color
        db.commit()
        return created


def get_profile(email: str, profile_id: int) -> Optional[dict]:
    """A profile you can open (yours or shared), with your `role` and its `owner_name`."""
    with SessionLocal() as db:
        row, role = _open(db, email, profile_id)
        if row is None:
            return None
        return {'id': row.id, 'name': row.name,
                'measurements': row.measurements,
                'skin_color': row.skin_color, 'role': role,
                'owner_name': None if role == 'owner' else access.display_name(db, row.owner_email)}


def update_profile(email: str, profile_id: int, measurements: dict,
                   skin_color: Optional[str] = None) -> None:
    """Save an existing profile's measurements, as its owner or an admin."""
    with SessionLocal() as db:
        row, role = _open(db, email, profile_id, 'admin')
        if row is None:
            raise ValueError('Only the profile’s owner or an admin can change it.' if role
                             else 'This profile is no longer available.')
        row.measurements = measurements
        row.skin_color = skin_color
        db.commit()


def copy_profile(email: str, profile_id: int) -> Optional[str]:
    """Your own private copy of a profile you can open. Returns its name."""
    with SessionLocal() as db:
        src, _ = _open(db, email, profile_id)
        if src is None or db.get(User, email) is None:
            return None
        taken = [name for (name,) in db.query(BodyProfile.name).filter(BodyProfile.owner_email == email)]
        name = access.unique_name(src.name, taken)
        db.add(BodyProfile(owner_email=email, name=name, measurements=dict(src.measurements),
                           skin_color=src.skin_color))
        db.commit()
        return name


def delete_profile(email: str, profile_id: int) -> bool:
    """For the owner or an admin; a copy someone saved remains theirs."""
    with SessionLocal() as db:
        row, _ = _open(db, email, profile_id, 'admin')
        if row is None:
            return False
        access.forget(db, 'body', row.id)
        db.delete(row)
        db.commit()
        return True


def delete_item(kind, profile_id, owner):
    """For webapp.access, once an admin's role is checked."""
    with SessionLocal() as db:
        row = db.get(BodyProfile, int(profile_id))
        if row is not None:
            access.forget(db, 'body', row.id)
            db.delete(row)
            db.commit()


def transfer_item(kind, profile_id, old_owner, new_owner):
    """Hand a profile to a member. A name they already use gains a number."""
    with SessionLocal() as db:
        row = db.get(BodyProfile, int(profile_id))
        if row is None or row.owner_email != old_owner:
            raise ValueError('This profile is no longer available.')
        access.reassign(db, 'body', row.id, old_owner, new_owner)
        taken = [name for (name,) in db.query(BodyProfile.name).filter(BodyProfile.owner_email == new_owner)]
        row.owner_email, row.name = new_owner, access.unique_name(row.name, taken)
        access.sync(db, 'body', row.id, dict(name=row.name))
        db.commit()
        return {'id': row.id, 'name': row.name}
