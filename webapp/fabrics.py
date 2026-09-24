"""Account-owned fabric records and immutable, body-independent snapshots.

Fabrics follow the shared access model in webapp/access.py: viewers read,
export and copy one; admins also edit and delete it; the owner alone can
transfer it. Purchase sources' private notes are the owner's alone: nobody
else reads them, an admin's save keeps them, and a transfer drops them.
"""
from copy import deepcopy
import re
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from gui.fabric_library import FABRIC_PRESETS
from webapp.db import SessionLocal
from webapp.models import Fabric
from webapp import access
from webapp import fabric_formats as formats


def _email(email):
    if not isinstance(email, str) or not email.strip():
        raise ValueError('Sign in to save fabrics.')
    return email.strip().lower()


def _name(name):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError('Choose a fabric name between 1 and 120 characters.')
    return name.strip()


def _private(content, role):
    """Everyone but the owner reads purchase sources with the owner's notes blank, as an import has them."""
    if role != 'owner' and content.get('purchase_sources'):
        from webapp.fabric_sources import PRIVATE
        content['purchase_sources'] = [dict(source, **dict.fromkeys(PRIVATE, ''))
                                       for source in content['purchase_sources']]
    return content


def _record(row, role='owner', owner_name=None):
    return dict(id=row.id, name=row.name, content=_private(deepcopy(row.content), role), edit_token=row.edit_token,
                created_at=row.created_at, updated_at=row.updated_at, standard=False,
                has_source=bool(row.source_name), role=role, owner_name=owner_name)


def _open(db, email, identity, minimum='viewer'):
    """A saved fabric and the caller's role on it. A guest may open a linked or public one."""
    email = email.strip().lower() if isinstance(email, str) and email.strip() else None
    row = db.get(Fabric, identity) if isinstance(identity, str) else None
    current = access.item_role(db, 'fabric', identity, email, row.owner_email) if row else None
    if current is None:
        raise ValueError('Fabric unavailable.')
    if access.RANK[current] < access.RANK[minimum]:
        raise ValueError('Only the fabric’s owner or an admin can change it.')
    return row, current


def _opened(db, row, role):
    return _record(row, role, None if role == 'owner' else access.display_name(db, row.owner_email))


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
        content['texture_maps'] = imported['texture_maps']
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


def shared_fabrics(email):
    """Fabrics others share with you, as a member or their friend, with your role on each."""
    views = access.Access(_email(email)).shared_with_me(('fabric',))
    with SessionLocal() as db:
        rows = {r.id: r for r in db.scalars(select(Fabric).where(
            Fabric.id.in_([v['revision_id'] for v in views])))} if views else {}
        return [dict(_record(rows[v['revision_id']], v['role'], v['owner_name']), share_id=v['id'],
                     is_member=v['is_member']) for v in views if v['revision_id'] in rows]


def listed(email, identity):
    """A list entry for any fabric you can open, without reading its stored file."""
    with SessionLocal() as db:
        return _opened(db, *_open(db, email, identity))


def get_fabric(email, identity):
    if identity.startswith('standard:'):
        _email(email)
        for item in standard_fabrics():
            if item['id'] == identity:
                return item
        raise ValueError('Fabric unavailable.')
    with SessionLocal() as db:
        row, role = _open(db, email, identity)
        return dict(_opened(db, row, role), content=_private(_normalized_content(row), role))


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
    """Your own private copy of any fabric you can open (a viewer's fork)."""
    source = get_fabric(email, identity)
    raw = filename = None
    if not source['standard']:
        with SessionLocal() as db:
            row, _ = _open(db, email, identity)
            raw, filename = row.source_bytes, row.source_name
    return _create(email, name or _copy_name(email, source['name']), source['content'], raw, filename)


def _imported(row):
    """What the stored original says, before any edit made here."""
    if not (row.source_name and row.source_bytes):
        return {}
    try:
        return formats.import_fabric(row.source_bytes, row.source_name)['properties']
    except ValueError:
        return {}


def imported_properties(email, identity):
    """An override never discards the measurement it replaced; the file still has it."""
    if identity.startswith('standard:'):
        return {}
    with SessionLocal() as db:
        return _imported(_open(db, email, identity)[0])


def update_fabric(email, identity, edit_token, *, name, description, values, restore=(), display_color=None,
                  sources=None):
    """Compare-and-swap prevents overwrites from another tab or stale editor.

    `restore` names properties to take back from the imported file, provenance
    included. `display_color` is left alone when None and cleared when empty.
    `sources` replaces the places to buy the fabric; None leaves them alone.
    The owner or an admin may save; an admin's save keeps the owner's notes.
    """
    if identity.startswith('standard:'):
        raise ValueError('Save a copy before editing a standard fabric.')
    with SessionLocal() as db:
        row, role = _open(db, email, identity, 'admin')
        content = _normalized_content(row)
        if not isinstance(description, str) or len(description) > 4000:
            raise ValueError('Keep the description under 4,000 characters.')
        content['description'] = description
        if display_color is not None:
            if display_color and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(display_color)):
                raise ValueError('Use a six-digit hex color, or leave it blank.')
            look = content.setdefault('appearance', {})
            look.pop('display_color', None)
            if display_color:
                look['display_color'] = display_color.lower()
        if sources is not None:
            from webapp.fabric_sources import PRIVATE, validate
            sources = validate(sources)
            if role != 'owner':
                kept = {s['id']: s for s in content.get('purchase_sources') or []}
                for source in sources:
                    for key in PRIVATE:
                        source[key] = kept.get(source['id'], {}).get(key, '')
            content['purchase_sources'] = sources
        if not isinstance(values, dict) or not set(values) <= set(formats.PROPERTY_UNITS):
            raise ValueError('Unknown fabric property.')
        restore = set(restore) - set(values)
        if not restore <= set(formats.PROPERTY_UNITS):
            raise ValueError('Unknown fabric property.')
        if restore:
            imported = _imported(row)
            if not imported:
                raise ValueError('This fabric has no imported measurements to restore.')
            for key in restore:
                content['properties'][key] = deepcopy(imported[key])
        for key, value in values.items():
            normalized = None if value is None or value == '' else formats.number(value)
            item = content['properties'][key]
            if normalized != item['value']:
                item.update(value=normalized, origin='unknown' if normalized is None else 'user', source=None)
        formats.validate_properties(content['properties'])
        try:
            changed = db.execute(update(Fabric).where(
                Fabric.id == identity, Fabric.owner_email == row.owner_email, Fabric.edit_token == edit_token
            ).values(name=_name(name), content=content, edit_token=str(uuid4())))
            if changed.rowcount != 1:
                raise ValueError('This fabric changed in another tab. Reopen it before saving.')
            access.sync(db, 'fabric', identity, dict(
                name=_name(name), display_color=(content.get('appearance') or {}).get('display_color')))
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError('That fabric name is already in use.') from None
        db.expire_all()
        return _opened(db, *_open(db, email, identity))


def delete_fabric(email, identity):
    """For the owner or an admin. Garments already cut from it keep their own copy."""
    if str(identity).startswith('standard:'):
        raise ValueError('Standard fabrics cannot be deleted.')
    with SessionLocal() as db:
        row, _ = _open(db, email, identity, 'admin')
        access.forget(db, 'fabric', identity)
        db.delete(row)
        db.commit()


def delete_item(kind, identity, owner):
    """For webapp.access, once an admin's role is checked."""
    with SessionLocal() as db:
        row = db.get(Fabric, identity)
        if row is not None:
            access.forget(db, 'fabric', identity)
            db.delete(row)
            db.commit()


def transfer_item(kind, identity, old_owner, new_owner):
    """Hand a fabric to a member. A name they already use gains a number; the notes stay behind."""
    with SessionLocal() as db:
        row = db.get(Fabric, identity)
        if row is None or row.owner_email != old_owner:
            raise ValueError('This fabric is no longer available.')
        access.reassign(db, 'fabric', identity, old_owner, new_owner)
        taken = db.scalars(select(Fabric.name).where(Fabric.owner_email == new_owner)).all()
        row.owner_email, row.name = new_owner, access.unique_name(row.name, taken)
        row.content = _private(deepcopy(row.content), 'new owner')
        row.edit_token = str(uuid4())   # An editor open on the old ownership must reload.
        access.sync(db, 'fabric', identity, dict(
            name=row.name, display_color=(row.content.get('appearance') or {}).get('display_color')))
        db.commit()
        return _record(row)


APPLIED_KEYS = ('description', 'properties', 'solver_tuning', 'catalog', 'texture_maps')


def _applied(record):
    content = record['content']
    result = dict(source_fabric_id=record['id'], name=record['name'], standard=record['standard'],
                  **{key: deepcopy(content[key]) for key in APPLIED_KEYS if key in content})
    color = (content.get('appearance') or {}).get('display_color')
    if color:
        result['display_color'] = color
    return result


def snapshot(email, identity):
    """Embed this value in an assignment; never dereference it to apply later edits.

    Curves, full-size textures and original bytes stay in the library. A garment
    needs the properties, their provenance and the small base-colour maps it
    draws; a full record copied into every saved outfit that uses the fabric
    would carry megabytes of measurement branches.
    """
    return _applied(get_fabric(email, identity))


def library_snapshot(email, identity):
    """Standard fabrics are public; a saved fabric still needs its own account."""
    if str(identity).startswith('standard:'):
        for item in standard_fabrics():
            if item['id'] == identity:
                return _applied(item)
        raise ValueError('Fabric unavailable.')
    return snapshot(email, identity)


# 4 and 8 oz/yd², the usual apparel boundaries between light, medium and heavy cloth.
WEIGHT_CLASSES = dict(light='Light · under 135 g/m²', medium='Medium · 135–270 g/m²',
                      heavy='Heavy · over 270 g/m²')


def weight_class(content):
    value = content['properties']['weight']['value']
    if value is None:
        return None
    return 'light' if value < 135 else 'medium' if value <= 270 else 'heavy'


def matches(record, query='', weight=''):
    """The library's search box and weight filter, shared by the account page and the studio picker."""
    content = record['content']
    catalog = content.get('catalog') or {}
    text = ' '.join((record['name'], content.get('description', ''), catalog.get('composition', ''),
                     catalog.get('construction', ''))).casefold()
    return (query or '').strip().casefold() in text and (not weight or weight_class(content) == weight)


def assignable(email=None):
    """Fabrics a signed-in or guest studio may cut a piece from, each listed once."""
    from webapp.fabric_catalog import standard_fabrics as catalog_fabrics
    from webapp.fabric_favorites import favorites
    owned, shared, hearted = [], [], []
    if email:
        try:
            owned, shared, hearted = list_fabrics(email), shared_fabrics(email), favorites(email)
        except ValueError:
            owned, shared, hearted = [], [], []
    # The artistic presets already are the panel's own "Drape presets" group.
    hearted = [r for r in hearted if not r['id'].startswith('standard:') or r['id'].startswith('standard:catalog:')]
    first = {r['id'] for r in hearted}
    groups = (('Favorites', hearted),
              ('My fabrics', [r for r in owned if r['id'] not in first]),
              ('Shared with me', [r for r in shared if r['id'] not in first]),
              ('Common fabrics', [r for r in catalog_fabrics() if r['id'] not in first]))
    return [dict(id=r['id'], label=r['name'], group=group) for group, records in groups for r in records]


def export_fabric(email, identity, bundle=False):
    record = get_fabric(email, identity)
    raw = filename = None
    if not record['standard']:
        with SessionLocal() as db:
            row, _ = _open(db, email, identity)
            raw, filename = row.source_bytes, row.source_name
    return formats.export_fabric(record, raw, filename, bundle=bundle)


def original_file(email, identity):
    with SessionLocal() as db:
        row, _ = _open(db, email, identity)
        if row.source_bytes is None:
            raise ValueError('This fabric has no imported source file.')
        return row.source_name, row.source_bytes
