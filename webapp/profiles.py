"""CRUD for per-user body-measurement profiles"""

from typing import Optional

from webapp.db import SessionLocal
from webapp.models import BodyProfile


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
    with SessionLocal() as db:
        row = db.get(BodyProfile, profile_id)
        if row is None or row.owner_email != email:
            return None
        return {'id': row.id, 'name': row.name,
                'measurements': row.measurements,
                'skin_color': row.skin_color}


def delete_profile(email: str, profile_id: int) -> bool:
    with SessionLocal() as db:
        row = db.get(BodyProfile, profile_id)
        if row is None or row.owner_email != email:
            return False
        db.delete(row)
        db.commit()
        return True
