"""CRUD for per-user saved designs: whole outfits and individual garments"""

import json
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import Design

# Which design-param sections make up each individually-savable piece.
# 'left' rides with the top: it holds upper-garment asymmetry params.
GARMENT_SECTIONS = {
    'top': {
        'meta': ['upper'],
        'sections': ['shirt', 'collar', 'sleeve', 'left'],
    },
    'bottom': {
        'meta': ['bottom'],
        'sections': ['skirt', 'flare-skirt', 'godet-skirt',
                     'pencil-skirt', 'levels-skirt', 'pants'],
    },
    'waistband': {
        'meta': ['wb'],
        'sections': ['waistband'],
    },
}
KIND_LABELS = {'outfit': 'Outfit', 'top': 'Top',
               'bottom': 'Bottom', 'waistband': 'Waistband'}


def snapshot_design_params(design_params: dict) -> dict:
    """A JSON-safe deep copy of the GUI's design-parameter state.

    The state matches the design-params YAML structure; the JSON round
    trip also coerces stray non-JSON scalars (e.g. numpy floats from
    sampling) to plain numbers.
    """
    return json.loads(json.dumps(design_params, default=float))


def snapshot_garment(design_params: dict, kind: str) -> dict:
    """Partial snapshot holding only the sections of one piece.

    The result keeps the self-describing design-params structure, so it
    merges into a full design via GUIPattern.set_new_design.
    """
    spec = GARMENT_SECTIONS[kind]
    partial = {'meta': {key: design_params['meta'][key]
                        for key in spec['meta']
                        if key in design_params['meta']}}
    for section in spec['sections']:
        if section in design_params:
            partial[section] = design_params[section]
    return snapshot_design_params(partial)


def list_designs(email: str) -> list:
    with SessionLocal() as db:
        rows = (db.query(Design)
                .filter(Design.owner_email == email)
                .order_by(Design.updated_at.desc())
                .all())
        return [{'id': r.id, 'name': r.name, 'kind': r.kind or 'outfit',
                 'updated_at': r.updated_at, 'preview': r.preview}
                for r in rows]


def count_designs(email: str) -> dict:
    """Design counts per kind — for summary displays, without dragging
    every row's preview SVG out of the database"""
    with SessionLocal() as db:
        rows = (db.query(Design.kind, func.count(Design.id))
                .filter(Design.owner_email == email)
                .group_by(Design.kind)
                .all())
        return {(kind or 'outfit'): n for kind, n in rows}


# Don't let a pathological drape blob bloat the database
MAX_DRAPE_BYTES = 32 * 1024 * 1024


def save_design(email: str, name: str, params: dict,
                kind: str = 'outfit', preview: Optional[str] = None,
                drape_glb: Optional[bytes] = None,
                fabric_color: Optional[str] = None) -> bool:
    """Create or update the design with this name. Returns True if created"""
    if drape_glb is not None and len(drape_glb) > MAX_DRAPE_BYTES:
        print(f'designs::WARNING::drape of "{name}" is '
              f'{len(drape_glb) / 1e6:.0f} MB — not stored')
        drape_glb = None
    with SessionLocal() as db:
        row = (db.query(Design)
               .filter(Design.owner_email == email, Design.name == name)
               .one_or_none())
        created = row is None
        if created:
            db.add(Design(owner_email=email, name=name, params=params,
                          kind=kind, preview=preview, drape_glb=drape_glb,
                          fabric_color=fabric_color))
        else:
            row.params = params
            row.kind = kind
            row.preview = preview
            row.drape_glb = drape_glb
            row.fabric_color = fabric_color
        db.commit()
        return created


def get_design(email: str, design_id: int) -> Optional[dict]:
    with SessionLocal() as db:
        row = db.get(Design, design_id)
        if row is None or row.owner_email != email:
            return None
        return {'id': row.id, 'name': row.name, 'params': row.params,
                'kind': row.kind or 'outfit',
                'drape_glb': row.drape_glb,
                'fabric_color': row.fabric_color}


def rename_design(email: str, design_id: int, new_name: str) -> bool:
    """Rename; False if not found, not owned, or the name is taken"""
    new_name = (new_name or '').strip()
    if not new_name:
        return False
    with SessionLocal() as db:
        row = db.get(Design, design_id)
        if row is None or row.owner_email != email:
            return False
        row.name = new_name
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False
        return True


def delete_design(email: str, design_id: int) -> bool:
    with SessionLocal() as db:
        row = db.get(Design, design_id)
        if row is None or row.owner_email != email:
            return False
        db.delete(row)
        db.commit()
        return True
