"""Declarative garment uploads. No uploaded program is imported or executed."""
from copy import deepcopy
import json
import math
import re
from uuid import uuid4

import yaml
from sqlalchemy.exc import IntegrityError

from webapp.db import SessionLocal
from webapp.models import BaseGarment
from webapp.garment_catalog import standard_garments, starter_item

MAX_BYTES = 2_000_000
FIT_DEFAULTS = {key: {'v': 1., 'type': 'float', 'range': [.5, 2.]}
                for key in ('width', 'height')}


def bounded_json(value):
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('Use finite, non-recursive JSON data.') from None
    if len(encoded.encode()) > MAX_BYTES:
        raise ValueError('The garment definition must be under 2 MB.')
    return deepcopy(value)


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError('Use a name between 1 and 100 characters.')
    return value.strip()


def set_parameters(params, values):
    """Dotted leaf paths; preserve types and schema, but not slider limits."""
    result = deepcopy(params)
    for path, value in (values or {}).items():
        if not isinstance(path, str) or path.startswith('_') or path.startswith('meta.'):
            raise ValueError('Choose a base garment to change its construction type.')
        node = result
        try:
            for part in path.split('.'):
                node = node[part]
            kind = node['type']
        except (KeyError, TypeError):
            raise ValueError(f'Unknown parameter: {path}') from None
        if kind in ('float', 'int'):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{path} needs a finite number.')
            if kind == 'int' and (int(value) != value or abs(value) > 200):
                raise ValueError(f'{path} needs a whole number with magnitude at most 200.')
            if abs(value) > 10000:
                raise ValueError(f'{path} exceeds the drafting resource limit.')
        elif kind == 'bool' and not isinstance(value, bool):
            raise ValueError(f'{path} needs true or false.')
        elif 'select' in kind and value not in node['range'] and not (value is None and 'null' in kind):
            raise ValueError(f'{path} is not an available option.')
        elif kind == 'color' and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(value)):
            raise ValueError(f'{path} needs a six-digit hex color.')
        node['v'] = value
    return result


def appearance(value):
    value = bounded_json(value or {})
    if not isinstance(value, dict):
        raise ValueError('Appearance must be an object.')
    allowed = {'fabric_color', 'panel_colors', 'panel_stiffness', 'panel_materials', 'panel_fabrics',
               'materials'}
    if set(value) - allowed:
        raise ValueError('Unknown appearance field.')
    for key in allowed - {'fabric_color'}:
        if key in value and not isinstance(value[key], dict):
            raise ValueError(f'{key} must map panel names to values.')
    colors = [value['fabric_color']] if value.get('fabric_color') else []
    colors += list(value.get('panel_colors', {}).values())
    for spec in value.get('panel_fabrics', {}).values():
        if not isinstance(spec, dict):
            raise ValueError('Each panel fabric must be an object.')
        if set(spec) - {'kind', 'fg', 'bg', 'scale'}:
            raise ValueError('Fabric accepts kind, fg, bg and scale.')
        if spec.get('kind', 'plain') not in ('plain', 'stripe', 'pinstripe', 'polka_dot', 'gingham', 'windowpane'):
            raise ValueError('Unknown fabric print.')
        colors += [spec[k] for k in ('fg', 'bg') if k in spec]
        if 'scale' in spec and not .01 <= float(spec['scale']) <= 1000:
            raise ValueError('Fabric scale must be between .01 and 1000.')
        spec.setdefault('kind', 'plain')
        spec.setdefault('fg', '#ffffff')
        spec.setdefault('bg', value.get('fabric_color') or '#b7cde5')
        spec.setdefault('scale', 1.)
    if any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors):
        raise ValueError('Colors must be six-digit hex values.')
    if any(not isinstance(v, (int, float)) or not .01 <= v <= 100
           for v in value.get('panel_stiffness', {}).values()):
        raise ValueError('Panel stiffness must be between .01 and 100.')
    from gui.fabric_library import FABRICS_BY_ID
    from webapp.fabric_formats import validate_properties
    from webapp.fabric_catalog import metadata
    from webapp.garment_materials import stiffness_for
    saved = value.get('materials', {})
    for identity, material in saved.items():
        if not isinstance(material, dict) or set(material) - {
                'source_fabric_id', 'name', 'standard', 'description', 'properties',
                'solver_tuning', 'catalog', 'display_color'}:
            raise ValueError('A saved material carries its id, name, properties and provenance.')
        if 'display_color' in material and not (isinstance(material['display_color'], str) and re.fullmatch(
                r'#[0-9a-fA-F]{6}', material['display_color'])):
            raise ValueError('Colors must be six-digit hex values.')
        if material.get('source_fabric_id', identity) != identity:
            raise ValueError('A saved material must be keyed by its own fabric id.')
        label(material.get('name', ''))
        validate_properties(material.get('properties'))
        if not isinstance(material.get('solver_tuning', {}), dict):
            raise ValueError('Solver tuning must be an object.')
        if material.get('catalog') is not None:
            material['catalog'] = metadata(material['catalog'])
        material['source_fabric_id'] = identity
    for panel, material in value.get('panel_materials', {}).items():
        if not isinstance(material, str):
            raise ValueError('Unknown fabric material.')
        # Library ids are only resolvable against the pool sent with them; a
        # partial update may name a material an earlier one already saved.
        if material in saved:
            stiffness = stiffness_for(saved[material])
            if stiffness is not None:
                value.setdefault('panel_stiffness', {}).setdefault(panel, stiffness)
        elif material in FABRICS_BY_ID:
            value.setdefault('panel_stiffness', {}).setdefault(panel, FABRICS_BY_ID[material]['stiffness'])
        elif material not in ('custom', 'default'):
            if 'materials' in value or not re.fullmatch(r'[A-Za-z0-9:_-]{1,64}', material):
                raise ValueError('Unknown fabric material.')
    return value


def validate_pattern(spec):
    spec = bounded_json(spec)
    if not isinstance(spec, dict) or not isinstance(spec.get('pattern'), dict):
        raise ValueError('A pattern file needs a pattern object with panels and stitches.')
    pattern = spec['pattern']
    panels = pattern.get('panels', {})
    if not isinstance(panels, dict) or not 1 <= len(panels) <= 64:
        raise ValueError('A pattern needs 1–64 panels.')
    if sum(len(p.get('vertices', [])) for p in panels.values()) > 8192:
        raise ValueError('Too many pattern vertices (maximum 8192).')
    for name, panel in panels.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name):
            raise ValueError('Panel names can contain letters, numbers, underscores and hyphens.')
        vertices, edges = panel.get('vertices', []), panel.get('edges', [])
        if not 3 <= len(vertices) <= 512 or not 3 <= len(edges) <= 512:
            raise ValueError(f'{name}: use 3–512 vertices and edges.')
        for vector, size in [(v, 2) for v in vertices] + [(panel.get(k, [0, 0, 0]), 3) for k in ('translation', 'rotation')]:
            if not isinstance(vector, list) or len(vector) != size or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or abs(v) > 1000 for v in vector):
                raise ValueError(f'{name}: invalid coordinates; use centimeters, within ±1000.')
        panel.setdefault('translation', [0, 0, 0])
        panel.setdefault('rotation', [0, 0, 0])
        for index, edge in enumerate(edges):
            ends = edge.get('endpoints', [])
            if len(ends) != 2 or any(type(v) is not int or not 0 <= v < len(vertices) for v in ends) or ends[0] == ends[1]:
                raise ValueError(f'{name}: invalid edge endpoints.')
            if ends[1] != edges[(index + 1) % len(edges)].get('endpoints', [None])[0]:
                raise ValueError(f'{name}: edges must form a closed, ordered loop.')
    seams = pattern.setdefault('stitches', [])
    if not isinstance(seams, list) or len(seams) > 4096:
        raise ValueError('Too many stitches.')
    for seam in seams:
        if not isinstance(seam, list) or len(seam) not in (2, 3):
            raise ValueError('A stitch must join two panel edges.')
        for end in seam[:2]:
            if end.get('panel') not in panels or type(end.get('edge')) is not int or not 0 <= end['edge'] < len(panels[end['panel']]['edges']):
                raise ValueError('A stitch refers to an unknown panel or edge.')
    props = spec.setdefault('properties', {})
    if props.get('units_in_meter', 100) != 100 or props.get('curvature_coords', 'relative') != 'relative':
        raise ValueError('Upload centimeter units with relative curvature coordinates.')
    props.update(units_in_meter=100, curvature_coords='relative', normalize_panel_translation=False, normalized_edge_loops=True)
    spec.setdefault('parameters', {})
    spec.setdefault('parameter_order', [])
    return spec


def base_record(row, files=False):
    result = dict(id=row.id, name=row.name, description=row.description,
                  params=deepcopy(row.params), appearance=deepcopy(row.appearance))
    if files:
        result['files'] = deepcopy(row.files)
    return result


def list_bases(email):
    with SessionLocal() as db:
        return standard_garments() + [base_record(r) for r in db.query(BaseGarment).filter_by(owner_email=email).order_by(BaseGarment.name)]


def get_base(email, base_id, files=False):
    if base_id.startswith('standard:'):
        return next((g for g in standard_garments() if g['id'] == base_id), None) or _unavailable()
    with SessionLocal() as db:
        row = db.query(BaseGarment).filter_by(id=base_id, owner_email=email).first()
        return base_record(row, files) if row else _unavailable()


def _unavailable():
    raise ValueError('Base garment is not in your library.')


def create_base(email, name, template_id=None, parameters=None, files=None, description=''):
    name = label(name)
    files = bounded_json(files or [])
    if not isinstance(files, list) or len(files) > 8:
        raise ValueError('Upload up to eight UTF-8 JSON or YAML files.')
    base = get_base(email, template_id) if template_id else None
    uploaded_pattern = None
    patch = dict(parameters or {})
    seen = set()
    for file in files:
        filename, content = file.get('name', ''), file.get('content', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}\.(json|yaml|yml)', filename) or filename in seen:
            raise ValueError('Use unique .json/.yaml filenames without folders. Python programs are not executed.')
        seen.add(filename)
        if not isinstance(content, str):
            raise ValueError('File content must be UTF-8 text.')
        try:
            if not filename.endswith('.json') and any(isinstance(t, (yaml.AliasToken, yaml.AnchorToken)) for t in yaml.scan(content)):
                raise ValueError('YAML aliases and anchors are not supported in uploads.')
            data = bounded_json(json.loads(content) if filename.endswith('.json') else yaml.safe_load(content))
        except (json.JSONDecodeError, yaml.YAMLError):
            raise ValueError(f'{filename} is not valid JSON or YAML.') from None
        if not isinstance(data, dict):
            raise ValueError(f'{filename} needs an object.')
        if 'pattern' in data:
            if uploaded_pattern is not None:
                raise ValueError('Upload one pattern specification per base garment.')
            uploaded_pattern = validate_pattern(data)
        elif 'design' in data:
            if not base:
                raise ValueError('Supply template_id with a design-parameter file.')
            def collect(node, prefix=''):
                for key, value in node.items():
                    path = f'{prefix}.{key}' if prefix else key
                    if path.startswith('meta') or key.startswith('_'):
                        continue
                    if isinstance(value, dict) and 'v' in value:
                        patch[path] = value['v']
                    elif isinstance(value, dict):
                        collect(value, path)
            collect(data['design'])
        else:
            patch.update(data.get('parameters', data))
    if uploaded_pattern:
        base = starter_item('Shirt')
        base['params']['meta']['upper']['v'] = 'UploadedPattern'
        base['params']['pattern_fit'] = deepcopy(FIT_DEFAULTS)
        base['params']['_custom_pattern'] = uploaded_pattern
    if base is None:
        raise ValueError('Choose template_id or upload a pattern specification JSON.')
    identity = uuid4().hex
    params = set_parameters(base['params'], patch)
    params['_base_id'] = identity
    params['_base_name'] = name
    row = BaseGarment(id=identity, owner_email=email, name=name, description=description[:2000],
                      params=params, appearance=base['appearance'], files=files)
    # Draft before persisting: malformed geometry never becomes a base template.
    from gui.gui_pattern import GUIPattern
    pattern = GUIPattern(draft=False)
    try:
        pattern.load_outfit([dict(params=params, appearance=base['appearance'])])
        pattern.reload_garment()
    finally:
        pattern.release()
    with SessionLocal() as db:
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            raise ValueError('A base garment already has that name.') from None
        return base_record(row)
