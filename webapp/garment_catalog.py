"""Lightweight garment labels, starter designs and library illustrations.

No drafting or simulation imports: the wardrobe should open immediately.
"""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import re
from uuid import uuid4

import yaml


STARTERS = (
    ('DressShirt', 'Dress shirt', 'Collar, buttons & cuffs', '#a6bfd7'),
    ('Shirt', 'T-shirt', 'Crew neck & short sleeves', '#d2c8b9'),
    ('ElementTubeTop', 'Tube top', 'Strapless, shaped at the waist', '#bcb0c9'),
    ('Pants', 'Trousers', 'Full length with a fitted waistband', '#53677c'),
    ('SkirtCircle', 'Circle skirt', 'Flared with a fitted waistband', '#aabcb2'),
    ('PencilSkirt', 'Pencil skirt', 'Straight silhouette & back slit', '#b7bec7'),
)


def garment_title(params):
    names = {'DressShirt': 'Dress shirt', 'FittedShirt': 'Fitted shirt', 'Shirt': 'Shirt',
             'ElementTubeTop': 'Tube top', 'Pants': 'Trousers', 'SkirtCircle': 'Circle skirt',
             'PencilSkirt': 'Pencil skirt'}
    parts = [v.get('v') for k, v in params.get('meta', {}).items() if k != 'wb' and v.get('v')]
    return ' + '.join(names.get(v, re.sub(r'(?<!^)(?=[A-Z])', ' ', v)) for v in parts) or 'New garment'


@lru_cache(maxsize=1)
def _defaults():
    return yaml.safe_load((Path(__file__).resolve().parents[1] /
                           'assets/design_params/default.yaml').read_text(encoding='utf-8'))['design']


def starter_item(kind):
    spec = next((s for s in STARTERS if s[0] == kind), None)
    if spec is None:
        raise ValueError('Choose one of the available starter garments.')
    params = deepcopy(_defaults())
    for value in params['meta'].values():
        value['v'] = None
    params['meta']['bottom' if kind in ('Pants', 'SkirtCircle', 'PencilSkirt') else 'upper']['v'] = kind
    if kind in ('Pants', 'SkirtCircle', 'PencilSkirt'):
        params['meta']['wb']['v'] = 'FittedWB'
    if kind == 'Pants':
        params['pants']['length']['v'] = .9
        params['pants']['flare']['v'] = .7
    if kind == 'Shirt':
        params['sleeve']['length']['v'] = .28
        params['sleeve']['end_width']['v'] = .9
        params['sleeve']['cuff']['type']['v'] = None
    if kind == 'PencilSkirt':
        params['pencil-skirt']['length']['v'] = .55
        params['pencil-skirt']['back_slit']['v'] = .15
    return dict(id='draft', name=spec[1], params=params,
                appearance=dict(fabric_color=spec[3]))


def standard_garments():
    """Read-only catalog entries; editing always starts with an independent copy."""
    return [dict(starter_item(kind), id=f'standard:{kind}', standard=kind, description=description)
            for kind, _, description, _ in STARTERS]


def _color(value, fallback):
    return value if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else fallback


def thumbnail(item):
    """Illustrative flat, with saved base color/print; never a claimed fit render."""
    params, look = item.get('params', {}), item.get('appearance', {})
    meta, fabric = params.get('meta', {}), params.get('fabric', {})
    color = _color(look.get('fabric_color'), '#b7cde5')
    kind = fabric.get('kind', {}).get('v', 'plain')
    ink = _color(fabric.get('fg', {}).get('v'), '#eef2f8')
    if kind != 'plain':
        color = _color(fabric.get('bg', {}).get('v'), color)
    if meta.get('upper', {}).get('v'):
        outline = 'M24 12 15 16 5 37 16 42 22 31 21 68 51 68 50 31 56 42 67 37 57 16 48 12 42 20 36 24 30 20Z'
        detail = 'M30 13 36 24 42 13M36 24V68M23 61H49'
        if meta['upper']['v'] == 'Shirt':
            detail = 'M25 12Q36 32 47 12M23 63H49'
        elif meta['upper']['v'] == 'ElementTubeTop':
            outline = 'M22 24Q36 28 50 24L47 47 50 64H22L25 47Z'
            detail = 'M23 28Q36 32 49 28M24 60H48'
    elif meta.get('bottom', {}).get('v') == 'Pants':
        outline = 'M22 12H50L55 70H40L36 35 32 70H17Z'
        detail = 'M22 20H50M36 20V35M23 22 21 33M49 22 51 33'
    elif meta.get('bottom', {}).get('v') == 'PencilSkirt':
        outline = 'M24 14H48L51 31 47 70H25L21 31Z'
        detail = 'M23 21H49M36 21V62L39 70M29 23 28 32M43 23 44 32'
    else:
        outline = 'M26 14H46L61 67Q36 74 11 67Z'
        detail = 'M25 21H47M29 24 23 66M43 24 49 66'
    print_shapes = {
        'stripe': f'<path d="M2 0V8" stroke="{ink}" stroke-width="2"/>',
        'pinstripe': f'<path d="M2 0V8" stroke="{ink}" stroke-width=".5"/>',
        'polka_dot': f'<circle cx="3" cy="3" r="1.2" fill="{ink}"/>',
        'gingham': f'<path d="M2 0V8M0 2H8" stroke="{ink}" stroke-width="3" opacity=".65"/>',
        'windowpane': f'<path d="M1 0V8M0 1H8" stroke="{ink}" stroke-width=".6"/>',
    }
    defs, fill = '', color
    if kind in print_shapes:
        pid = 'fabric-' + uuid4().hex
        defs = (f'<defs><pattern id="{pid}" width="8" height="8" patternUnits="userSpaceOnUse">'
                f'<rect width="8" height="8" fill="{color}"/>{print_shapes[kind]}</pattern></defs>')
        fill = f'url(#{pid})'
    return (f'<svg viewBox="0 0 72 82" aria-hidden="true">{defs}'
            f'<path d="{outline}" fill="{fill}" stroke="#57728f" stroke-width=".85"/>'
            f'<path d="{detail}" fill="none" stroke="#57728f" stroke-width=".65"/></svg>')


def draft_items(snapshot):
    if snapshot.get('outfit'):
        return deepcopy(snapshot['outfit'])
    if snapshot.get('design'):
        return [dict(id='draft', name=garment_title(snapshot['design']),
                     params=deepcopy(snapshot['design']), appearance=deepcopy(
                         snapshot.get('appearance') or {'fabric_color': snapshot.get('fabric')}))]
    return []


def studio_snapshot(items, name='Untitled outfit', previous=None, *, outfit_revision_id=None, editor_mode=None,
                    source_share=None, outfit_updated_at=None):
    """Open editable copies while retaining the currently chosen measurements."""
    if not items:
        raise ValueError('Choose at least one garment.')
    items = deepcopy(items)
    active = items[0]
    snapshot = {key: deepcopy(value) for key, value in (previous or {}).items() if key in ('body', 'skin')}
    mode = editor_mode or ('outfit' if outfit_revision_id or len(items) > 1 else 'garment')
    snapshot.update(design=deepcopy(active['params']), outfit=items, outfit_name=name,
                    editor_mode=mode, source_share=source_share, outfit_updated_at=outfit_updated_at,
                    outfit_revision_id=outfit_revision_id,
                    active_garment=0, appearance=deepcopy(active.get('appearance', {})),
                    fabric=active.get('appearance', {}).get('fabric_color', '#b7cde5'))
    return snapshot


def library_matches(items, query):
    query = (query or '').strip().casefold()
    return [item for item in reversed(items) if not query or query in item['name'].casefold()
            or any(query in g['name'].casefold() for g in item.get('garments', []))]
