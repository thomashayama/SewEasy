"""CRUD for per-user saved garment designs"""

import json
from typing import Optional

from webapp.db import SessionLocal
from webapp.models import Design


def snapshot_design_params(design_params: dict) -> dict:
    """A JSON-safe deep copy of the GUI's design-parameter state.

    The state matches the design-params YAML structure; the JSON round
    trip also coerces stray non-JSON scalars (e.g. numpy floats from
    sampling) to plain numbers.
    """
    return json.loads(json.dumps(design_params, default=float))


def list_designs(email: str) -> list:
    with SessionLocal() as db:
        rows = (db.query(Design)
                .filter(Design.owner_email == email)
                .order_by(Design.updated_at.desc())
                .all())
        return [{'id': r.id, 'name': r.name, 'updated_at': r.updated_at}
                for r in rows]


def save_design(email: str, name: str, params: dict) -> bool:
    """Create or update the design with this name. Returns True if created"""
    with SessionLocal() as db:
        row = (db.query(Design)
               .filter(Design.owner_email == email, Design.name == name)
               .one_or_none())
        created = row is None
        if created:
            db.add(Design(owner_email=email, name=name, params=params))
        else:
            row.params = params
        db.commit()
        return created


def get_design(email: str, design_id: int) -> Optional[dict]:
    with SessionLocal() as db:
        row = db.get(Design, design_id)
        if row is None or row.owner_email != email:
            return None
        return {'id': row.id, 'name': row.name, 'params': row.params}


def delete_design(email: str, design_id: int) -> bool:
    with SessionLocal() as db:
        row = db.get(Design, design_id)
        if row is None or row.owner_email != email:
            return False
        db.delete(row)
        db.commit()
        return True
