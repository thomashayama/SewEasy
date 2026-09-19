"""Account-owned fabric records and immutable, body-independent snapshots."""
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from gui.fabric_library import FABRIC_PRESETS
from webapp.db import SessionLocal
from webapp.models import Fabric
from webapp import fabric_formats as formats


def _email(email):
    if not isinstance(email, str) or not email.strip():
        raise ValueError('Sign in to save fabrics.')
    return email.strip().lower()


def _name(name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError('Choose a fabric name between 1 and 120 characters.')
    return name.strip()


def _record(row):
    return dict(id=row.id, name=row.name, content=deepcopy(row.content), edit_token=row.edit_token,
                created_at=row.created_at, updated_at=row.updated_at, standard=False,
                has_source=bool(row.source_name))


def _owned(db, email, identity):
    row = db.scalar(select(Fabric).where(Fabric.id == identity, Fabric.owner_email == _email(email)))
    if row is None:
        raise ValueError('Fabric unavailable.')
    return row


def _normalized_content(row):
    """Upgrade old imports on detail reads without rewriting the user's record.

    Lists never read blobs. A subsequent save persists the normalization marker,
    so intentionally cleared fields stay cleared. Only our derived bending
    estimates are refreshed when the normalizer changes; user values win.
    """
    content = deepcopy(row.content)
    from webapp.fabric_measurements import VERSION, is_loop_estimate
    previous = content.get('physics_normalization') or {}
    stale = (previous.get('version', 0) < VERSION
             or (content.get('source') or {}).get('importer') != formats.IMPORTER)
    if stale and row.source_name and row.source_bytes:
        try:
            imported = formats.import_fabric(row.source_bytes, row.source_name)
        except ValueError:
            # A stricter reader must not lock an owner out of a stored fabric.
            return content
        for key, item in imported['properties'].items():
            existing = content['properties'][key]
            if (is_loop_estimate(existing) or (not previous and existing['value'] is None
                                             and existing['origin'] == 'unknown')):
                content['properties'][key] = item
        content['curves'] = imported['curves']
        content['physics_normalization'] = imported['physics_normalization']
        # Both describe the file itself, so they follow the reader that read it.
        content['textures'] = imported['textures']
        content['source'] = imported['source']
    return content


def _empty():
    return dict(schema=1, description='', properties=formats.properties(), appearance={},
                source=None, textures=[], curves=[], solver_tuning={})


def standard_fabrics():
    """Legacy artistic IDs remain resolvable alongside the physical collection."""
    result = []
    for preset in FABRIC_PRESETS:
        content = _empty()
        content['description'] = preset['description']
        content['solver_tuning'] = dict(bend_multiplier=preset['stiffness'], origin='estimated')
        content['source'] = dict(format='SewEasy preset', preset_id=preset['id'])
        result.append(dict(id='standard:' + preset['id'], name=preset['label'], content=content,
                           standard=True, has_source=False, edit_token=None))
    from webapp.fabric_catalog import standard_fabrics as catalog_fabrics
    return result + catalog_fabrics()


def list_fabrics(email):
    with SessionLocal() as db:
        return [_record(row) for row in db.scalars(select(Fabric).where(
            Fabric.owner_email == _email(email)).order_by(Fabric.updated_at.desc()))]


def get_fabric(email, identity):
    _email(email)
    if identity.startswith('standard:'):
        for item in standard_fabrics():
            if item['id'] == identity:
                return item
        raise ValueError('Fabric unavailable.')
    with SessionLocal() as db:
        row = _owned(db, email, identity)
        return dict(_record(row), content=_normalized_content(row))


def _create(email, name, content, source_bytes=None, source_name=None):
    content = deepcopy(content)
    content.pop('name', None)
    formats.validate_properties(content['properties'])
    with SessionLocal() as db:
        row = Fabric(id=str(uuid4()), owner_email=_email(email), name=_name(name), content=content,
                     edit_token=str(uuid4()), source_bytes=source_bytes, source_name=source_name)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError('That fabric name is already in use, or your account is unavailable.') from None
        return _record(row)


def create_fabric(email, name):
    return _create(email, name, _empty())


def import_fabric(email, raw, filename, name=None):
    _email(email)
    content = formats.import_fabric(raw, filename)
    # Imported names are not allowed to overwrite another saved fabric.
    return _create(email, name or _copy_name(email, content['name'], imported=True),
                   content, source_bytes=raw, source_name=filename)


def _copy_name(email, name, imported=False):
    names = {r['name'] for r in list_fabrics(email)}
    base = name.strip()[:100] or 'Untitled fabric'
    if imported and base not in names:
        return base
    candidate, index = base + ' (copy)', 2
    while candidate in names:
        candidate = f'{base} (copy {index})'
        index += 1
    return candidate


def copy_fabric(email, identity, name=None):
    source = get_fabric(email, identity)
    raw = filename = None
    if not source['standard']:
        with SessionLocal() as db:
            row = _owned(db, email, identity)
            raw, filename = row.source_bytes, row.source_name
    return _create(email, name or _copy_name(email, source['name']), source['content'], raw, filename)


def update_fabric(email, identity, edit_token, *, name, description, values):
    """Compare-and-swap prevents overwrites from another tab or stale editor."""
    if identity.startswith('standard:'):
        raise ValueError('Save a copy before editing a standard fabric.')
    with SessionLocal() as db:
        row = _owned(db, email, identity)
        content = _normalized_content(row)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('Keep the description under 4,000 characters.')
        content['description'] = description
        if not isinstance(values, dict) or not set(values) <= set(formats.PROPERTY_UNITS):
            raise ValueError('Unknown fabric property.')
        for key, value in values.items():
            normalized = None if value is None or value == '' else formats.number(value)
            item = content['properties'][key]
            if normalized != item['value']:
                item.update(value=normalized, origin='unknown' if normalized is None else 'user', source=None)
        formats.validate_properties(content['properties'])
        try:
            changed = db.execute(update(Fabric).where(
                Fabric.id == identity, Fabric.owner_email == _email(email), Fabric.edit_token == edit_token
            ).values(name=_name(name), content=content, edit_token=str(uuid4())))
            if changed.rowcount != 1:
                raise ValueError('This fabric changed in another tab. Reopen it before saving.')
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError('That fabric name is already in use.') from None
        db.expire_all()
        return _record(_owned(db, email, identity))


def snapshot(email, identity):
    """Embed this value in an assignment; never dereference it to apply later edits."""
    record = get_fabric(email, identity)
    return dict(source_fabric_id=identity, name=record['name'], **deepcopy(record['content']))


def export_fabric(email, identity):
    record = get_fabric(email, identity)
    raw = filename = None
    if not record['standard']:
        with SessionLocal() as db:
            row = _owned(db, email, identity)
            raw, filename = row.source_bytes, row.source_name
    return formats.export_fabric(record, raw, filename)


def original_file(email, identity):
    with SessionLocal() as db:
        row = _owned(db, email, identity)
        if row.source_bytes is None:
            raise ValueError('This fabric has no imported source file.')
        return row.source_name, row.source_bytes
