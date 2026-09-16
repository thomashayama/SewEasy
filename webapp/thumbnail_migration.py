"""One-time import of old content-keyed images into revision attachments.

Only legacy libraries use these frozen recipes. New images and normal reads
never hash designs or body files.
"""
from hashlib import sha256
import json
import re

from webapp.thumbnail_cache import thumbnail_key

# Body checksums used by the two previously shipped cache formats.
LEGACY_BODIES = (
    'aed8c58d445a732a45f8bc9e042d36f7d8c57d8df7a6ef24061f1caa08e794c6',
    'fc78250c24f7f40d10ac6e60a1af37deb24bd8439c1109be701ad255b28819eb',
)


def legacy_key(items, body):
    def look(item):
        appearance = item.get('appearance', {})
        return dict(fabric_color=appearance.get('fabric_color') or '#b7cde5',
                    **{field: appearance.get(field, {}) for field in
                       ('panel_colors', 'panel_fabrics', 'panel_stiffness', 'panel_materials')})
    recipe = dict(version='default-mannequin-webgpu-v2', body=body,
                  garments=[dict(params=g['params'], appearance=look(g)) for g in items])
    return sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':'), default=float).encode()).hexdigest()


def migrate_thumbnails(library):
    images = library.get('thumbnails', {})
    legacy = {key: image for key, image in images.items() if re.fullmatch('[0-9a-f]{64}', key)}
    if not legacy:
        return
    from webapp.garment_catalog import standard_garments
    attached = {key: image for key, image in images.items() if key not in legacy}
    targets = [(thumbnail_key('garment', g['id']), [g]) for g in library['garments'] + standard_garments()]
    targets += [(thumbnail_key('outfit', o['revision_id']), o['garments']) for o in library['outfit_revisions']]
    for key, items in targets:
        if key in attached:
            continue
        for body in LEGACY_BODIES:
            image = legacy.get(legacy_key(items, body))
            if image:
                attached[key] = image
                break
    library['thumbnails'] = attached
