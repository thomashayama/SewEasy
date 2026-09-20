"""Bounded U3M 1.1 import/export. No extraction, remote fetching, or solver guesses."""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
import re
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
from zlib import error as ZlibError

from jsonschema import Draft7Validator, FormatChecker
from PIL import Image

SPEC = Path(__file__).with_name('u3m_spec')
MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_JSON = 4 * 1024 * 1024
MAX_FILES = 128
# Recorded on every import so a record states which reader produced it.
# 1: prototype; textures were resolved but never read. 2: header-checked textures.
# 3: render-ready base-colour maps for the front and back.
IMPORTER = 'seweasy-u3m/3'
TEXTURE_FORMATS = ('PNG', 'JPEG', 'TIFF', 'WEBP')
MAX_TEXTURE_SIDE = 16384
MAX_TEXTURE_PIXELS = 80_000_000
MM_PER_INCH = 25.4
SCALE_TOLERANCE = .02
# A garment carries its own copy of the map, so it is small: a repeat tile is
# drawn a few centimetres wide, where 512 px already exceeds the screen.
TEXTURE_MAP_PX = 512
TEXTURE_MAP_BYTES = 200_000
TEXTURE_MAP_DECODE_PIXELS = 36_000_000

# These describe normalized physical quantities, not XPBD constraint compliance.
PROPERTY_UNITS = {
    'weight': 'g/m2', 'thickness': 'mm', 'friction': '1', 'damping': '1/s',
    'stretch_warp': 'N/m', 'stretch_weft': 'N/m', 'shear': 'N/m',
    'bend_warp': 'N*m', 'bend_weft': 'N*m',
}
ORIGINS = {'unknown', 'measured', 'reported', 'estimated', 'user'}


def properties():
    return {key: dict(value=None, unit=unit, origin='unknown', source=None)
            for key, unit in PROPERTY_UNITS.items()}


def number(value):
    if isinstance(value, bool):
        raise ValueError('Use a finite, non-negative number or leave the value blank.')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Use a finite, non-negative number or leave the value blank.') from None
    if not math.isfinite(result) or result < 0:
        raise ValueError('Use a finite, non-negative number or leave the value blank.')
    return result


def validate_properties(values):
    """Unknown is null; physical validity is enforced without arbitrary safe bounds."""
    if not isinstance(values, dict) or set(values) != set(PROPERTY_UNITS):
        raise ValueError('The fabric property set is incomplete.')
    for key, item in values.items():
        if (not isinstance(item, dict) or item.get('unit') != PROPERTY_UNITS[key]
                or item.get('origin') not in ORIGINS):
            raise ValueError(f'Invalid units or provenance for {key}.')
        if item.get('value') is not None:
            item['value'] = number(item['value'])
            if key in ('weight', 'thickness') and item['value'] == 0:
                raise ValueError(f'{key.title()} must be greater than zero, or blank if unknown.')
        if item.get('source') is not None and not isinstance(item['source'], str):
            raise ValueError('A measurement source must be text.')
    return values


def _json(raw):
    if len(raw) > MAX_JSON:
        raise ValueError('Each material or measurement JSON file must be under 4 MB.')
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('Duplicate JSON keys are not supported.')
                result[key] = value
            return result
        def invalid(_):
            raise ValueError('JSON cannot contain NaN or infinity.')
        result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)
        # Also rejects overflowed exponents (e.g. 1e999).
        json.dumps(result, allow_nan=False)
        return result
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError('The material contains invalid or overly nested JSON.') from None


@lru_cache(maxsize=2)
def _validator(filename):
    return Draft7Validator(json.loads((SPEC / filename).read_text(encoding='utf-8')),
                           format_checker=FormatChecker())


def _validate(value, filename):
    try:
        error = next(_validator(filename).iter_errors(value), None)
    except RecursionError:
        raise ValueError('The material is too deeply nested.') from None
    if error:
        location = '.'.join(str(x) for x in error.absolute_path) or 'document'
        raise ValueError(f'Invalid U3M 1.1 {location}: {error.message[:180]}')


def _path(name):
    if (not name or len(name) > 240 or '\\' in name or '\x00' in name
            or any(ord(c) < 32 for c in name) or re.search(r'[:*?"<>|]', name)
            or any(p in ('', '.', '..') or p.endswith(('.', ' ')) for p in name.split('/'))
            or any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?', p)
                   for p in name.split('/'))):
        raise ValueError('Package files must have safe relative paths.')
    return name


def _referenced(node, role=''):
    """Yield (role, node) for every file reference: textures, maps and previews."""
    if isinstance(node, dict):
        if isinstance(node.get('path'), str):
            yield role, node
            return
        for key, child in node.items():
            yield from _referenced(child, f'{role}.{key}' if role else key)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _referenced(child, f'{role}[{index}]')


def _scale_warning(role, node, pixels):
    """U3M 1.1 states image width/height in mm; pixels must match them at dpi."""
    dpi = node['dpi'] if isinstance(node.get('dpi'), dict) else {}
    expected = []
    for size, axis in ((node.get('width'), 'x'), (node.get('height'), 'y')):
        resolution = dpi.get(axis)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                   for v in (size, resolution)):
            return f'{role} does not declare a usable physical size, so its texture scale is unknown.'
        expected.append(size / MM_PER_INCH * resolution)
    if any(abs(want - have) > max(1, SCALE_TOLERANCE * have) for want, have in zip(expected, pixels)):
        return (f'{role} is {pixels[0]}×{pixels[1]} px but declares {node["width"]:.4g}×{node["height"]:.4g} mm '
                f'at {dpi["x"]:g}×{dpi["y"]:g} dpi, which is {expected[0]:.0f}×{expected[1]:.0f} px. '
                'The declared physical size is kept unchanged.')
    return None


def inspect_textures(files, manifest, document):
    """Headers only: real images of bounded size, with their declared scale checked.

    Pixels are never decoded, so a truncated file is reported by the renderer,
    not here. Nothing is rescaled, re-encoded, or dropped.
    """
    parent = PurePosixPath(manifest).parent
    material, result, seen = document['material'], [], {}
    for side in ('front', 'back', 'side'):
        for role, node in _referenced(material[side], side):
            data = files[str(parent / node['path'])]
            if node['path'] not in seen:
                try:
                    with Image.open(BytesIO(data)) as image:
                        seen[node['path']] = (image.format, list(image.size))
                except Exception:
                    raise ValueError(f'{role} file {node["path"]} is not a readable image. '
                                     'Upload the original PNG, JPEG, TIFF or WebP texture.') from None
            kind, pixels = seen[node['path']]
            if kind not in TEXTURE_FORMATS:
                raise ValueError(f'{role} file {node["path"]} is {kind or "an unrecognized format"}. '
                                 'Convert it to PNG, JPEG, TIFF or WebP and export the package again.')
            if max(pixels) > MAX_TEXTURE_SIDE or pixels[0] * pixels[1] > MAX_TEXTURE_PIXELS:
                raise ValueError(f'{role} file {node["path"]} is {pixels[0]}×{pixels[1]} px. The limit is '
                                 f'{MAX_TEXTURE_SIDE} px per side and {MAX_TEXTURE_PIXELS // 10**6} megapixels.')
            dpi = node['dpi'] if isinstance(node.get('dpi'), dict) else {}
            result.append(dict(role=role, path=node['path'], format=kind, pixels=pixels, bytes=len(data),
                               size_mm=[node.get('width'), node.get('height')],
                               dpi=[dpi.get('x'), dpi.get('y')],
                               warning=_scale_warning(role, node, pixels)))
    return result


def texture_maps(files, manifest, document):
    """Render-ready base colour for each side that supplies one, at its declared size.

    Only the base-colour map is drawn. Normal, roughness and the other PBR maps,
    mirrored repeats and repeat rotation are stored with the package but not
    rendered. The original files are untouched; this is a separate small copy.
    """
    from base64 import b64encode
    parent, material, result = PurePosixPath(manifest).parent, document['material'], {}
    for side in ('front', 'back'):
        texture = ((material[side] or {}).get('basecolor') or {}).get('texture') or {}
        node = texture.get('image')
        if not isinstance(node, dict) or not all(
                isinstance(node.get(k), (int, float)) and node[k] > 0 for k in ('width', 'height')):
            continue                    # No map, or no physical size to draw it at.
        try:
            with Image.open(BytesIO(files[str(parent / node['path'])])) as image:
                if image.size[0] * image.size[1] > TEXTURE_MAP_DECODE_PIXELS:
                    continue            # Stored, but too large to decode on a request.
                image.draft('RGB', (TEXTURE_MAP_PX, TEXTURE_MAP_PX))
                pixels = image.convert('RGB')
        except Exception:
            continue                    # Headers passed; a truncated body is simply not drawn.
        pixels.thumbnail((TEXTURE_MAP_PX, TEXTURE_MAP_PX), Image.LANCZOS)
        factor = texture.get('factor') or {}
        if texture.get('mode', 'multiply') == 'multiply' and any(factor.get(c, 1) != 1 for c in 'rgb'):
            pixels = Image.merge('RGB', [band.point(lambda v, k=max(0., min(1., float(factor.get(c, 1)))): int(v * k))
                                         for band, c in zip(pixels.split(), 'rgb')])
        for quality in (85, 70, 50):
            encoded = BytesIO()
            pixels.save(encoded, format='WEBP', quality=quality)
            if encoded.tell() <= TEXTURE_MAP_BYTES:
                break
        else:
            continue
        result[side] = dict(image='data:image/webp;base64,' + b64encode(encoded.getvalue()).decode('ascii'),
                            size_mm=[float(node['width']), float(node['height'])], pixels=list(pixels.size))
    return result


def read_package(raw, filename):
    """Legacy ZIP wrappers are readable; references must be local and complete."""
    if not raw or len(raw) > MAX_UPLOAD:
        raise ValueError('Choose a U3M file or U3MA package under 20 MB.')
    suffix = Path(filename).suffix.lower()
    if suffix == '.u3m':
        files = {'material.u3m': raw}
    elif suffix in ('.u3ma', '.zip'):
        try:
            with ZipFile(BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_EXPANDED:
                    raise ValueError('The package exceeds 128 files or 64 MB uncompressed.')
                files, seen = {}, set()
                for item in entries:
                    name = _path(item.filename.rstrip('/') if item.is_dir() else item.filename)
                    if name.casefold() in seen:
                        raise ValueError('Duplicate package paths are not supported.')
                    seen.add(name.casefold())
                    if item.flag_bits & 1 or item.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                        raise ValueError('Encrypted or unusually compressed packages are not supported.')
                    if (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Package links are not supported.')
                    if not item.is_dir():
                        with archive.open(item) as source:
                            data = source.read(MAX_EXPANDED + 1)
                        if len(data) != item.file_size or len(data) > MAX_EXPANDED:
                            raise ValueError('Invalid package file size.')
                        files[name] = data
        except (BadZipFile, RuntimeError, NotImplementedError, EOFError, ZlibError):
            raise ValueError('The U3MA package is damaged or unsupported.') from None
    else:
        raise ValueError('Choose a .u3m, .u3ma, or .zip file.')
    manifests = [p for p in files if p.lower().endswith('.u3m')]
    if len(manifests) != 1:
        raise ValueError('A package must contain exactly one .u3m material.')
    manifest = manifests[0]
    document = _json(files[manifest])
    if isinstance(document, dict) and document.get('schema') == '1.0':
        # 1.0 has no physics section, no unit for image width/height, a single
        # dpi number, and no U3MA archive spec, so neither measurements nor
        # texture scale can be read from it. See webapp/u3m_spec/README.md.
        raise ValueError('This is a U3M 1.0 material. SewEasy reads U3M 1.1, which adds the physics '
                         'section and texture units. Re-export the material as 1.1 and upload it again.')
    _validate(document, 'u3m_schema.json')
    parent = PurePosixPath(manifest).parent

    def resolve(path):
        _path(path)
        full = str(parent / path)
        if full not in files:
            raise ValueError(f'Missing companion file: {path}. Upload the complete package.')
        return full

    material = document['material']
    for side in ('front', 'back', 'side'):
        for _, node in _referenced(material[side], side):
            resolve(node['path'])
    physics = material['physics'] or {}
    fab_path = (physics.get('devices') or {}).get('fab')
    fab = None
    if fab_path and fab_path != 'null':
        fab = _json(files[resolve(fab_path)])
        _validate(fab, 'physics_schema.json')
    return files, manifest, document, fab


def import_fabric(raw, filename):
    files, manifest, document, fab = read_package(raw, filename)
    textures = inspect_textures(files, manifest, document)
    material = document['material']
    values = properties()
    physics = material['physics'] or {}
    for key in ('weight', 'thickness'):
        if physics.get(key) is not None:
            values[key].update(value=number(physics[key]), origin='reported', source=f'material.physics.{key}')
    vendor = ((fab or {}).get('custom') or {}).get('browzwear') or {}
    if not isinstance(vendor, dict):
        vendor = {}
    raw_data = (fab or {}).get('raw_data') or {}
    if values['weight']['value'] is None and raw_data.get('M') is not None:
        values['weight'].update(value=number(raw_data['M']), origin='measured', source='FAB raw_data.M')
    for key, vendor_key in (('thickness', 'thickness'), ('friction', 'friction')):
        if values[key]['value'] is None and vendor.get(vendor_key) is not None:
            values[key].update(value=number(vendor[vendor_key]), origin='reported', source=f'FAB custom.browzwear.{vendor_key}')
    extension = (document.get('custom') or {}).get('seweasy')
    from webapp.fabric_measurements import normalize, is_loop_estimate
    normalized, curves, normalization = normalize(fab)
    values.update(normalized)
    if isinstance(extension, dict) and extension.get('schema') == 1 and 'properties' in extension:
        # Our exports explicitly distinguish edits from original measurements.
        values = deepcopy(extension['properties'])
    validate_properties(values)
    # Old SewEasy exports can contain estimates made before we honored FAB
    # quality flags. Retire those estimates without replacing edits or clears.
    for warning in normalization['warnings']:
        key = warning['property']
        if is_loop_estimate(values[key]):
            values[key] = normalized[key]
    from webapp.fabric_catalog import metadata
    catalog = metadata(extension.get('catalog')) if isinstance(extension, dict) else None
    result = dict(
        schema=1, name=material['name'], description=material['description'], properties=values,
        appearance={side: deepcopy(material[side]) for side in ('front', 'back', 'side')},
        source=dict(format='U3M 1.1', importer=IMPORTER, filename=Path(filename).name,
                    sha256=sha256(raw).hexdigest(), material_id=material['id'],
                    has_raw_measurements=bool(raw_data), vendor='Browzwear' if vendor else None),
        # Full original curves, vendor fields and textures remain in source_bytes.
        textures=textures, texture_maps=texture_maps(files, manifest, document),
        curves=curves, physics_normalization=normalization,
        solver_tuning=deepcopy(extension.get('solver_tuning', {}))
        if isinstance(extension, dict) and isinstance(extension.get('solver_tuning'), dict) else {},
    )
    if catalog is not None:
        result['catalog'] = catalog
    color = extension.get('display_color') if isinstance(extension, dict) else None
    if isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        result['appearance']['display_color'] = color.lower()
    if isinstance(extension, dict) and extension.get('purchase_sources'):
        from webapp.fabric_sources import from_file
        # A file is untrusted: links are re-validated, and it can carry no private notes.
        result['purchase_sources'] = from_file(extension['purchase_sources'])
    return result


class _U3mZipInfo(ZipInfo):
    def _encodeFilenameFlags(self):
        # U3MA requires UTF-8 flags even for ASCII names.
        return self.filename.encode('utf-8'), self.flag_bits | 0x800


def pack(files):
    """Write the U3MA subset, rather than just renaming an ordinary ZIP."""
    output = BytesIO()
    now = datetime.now(timezone.utc)
    with ZipFile(output, 'w', allowZip64=False) as archive:
        for name, raw in files.items():
            info = _U3mZipInfo(_path(name), date_time=now.timetuple()[:6])
            info.create_system, info.create_version, info.extract_version = 0, 63, 20
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, raw)
            # zipfile supplies Unix permissions when attrs are initially zero.
            info.external_attr = info.internal_attr = 0
    return output.getvalue()


def _encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')


def empty_document(name, identity=None):
    now = datetime.now(timezone.utc).isoformat()
    return dict(schema='1.1', custom=None, material=dict(
        id=identity or str(uuid4()), name=name, description='', created=now, modified=now,
        front=None, back=None, side=None, metadata=None,
        physics=dict(weight=None, thickness=None, composition=None,
                     devices=dict(fab='null'), material_type=None, construction=None)))


NOTES_PATH = 'seweasy-export-notes.txt'
NOTES_HEADING = 'SewEasy fabric export'
# Every U3M reader understands these; everything else travels in custom.seweasy.
NATIVE_PROPERTIES = ('weight', 'thickness')


def export_notes(record, has_measurements=False):
    """Plain text for whoever opens the package elsewhere: what another application will and will not read."""
    content = record['content']
    lines = [NOTES_HEADING, f'Material: {record["name"]}', f'Format: U3M 1.1, written by {IMPORTER}.', '']

    def stated(key):
        item = content['properties'][key]
        unit = '' if item['unit'] == '1' else ' ' + item['unit']      # a bare "1" reads as a typo
        return f'  {key} = {item["value"]:.8g}{unit} ({item["origin"]})'
    supplied = [k for k in PROPERTY_UNITS if content['properties'][k]['value'] is not None]
    lines.append('Written to standard U3M fields, which any U3M application reads:')
    lines += [stated(k) for k in supplied if k in NATIVE_PROPERTIES] or ['  (no weight or thickness supplied)']
    lines += ['  name, description, and the original visual maps and companion files, byte for byte.', '']
    lines.append('Written only to the custom.seweasy extension. Other applications will ignore these:')
    lines += [stated(k) for k in supplied if k not in NATIVE_PROPERTIES] or ['  (none)']
    if (content.get('appearance') or {}).get('display_color'):
        lines.append(f'  display colour = {content["appearance"]["display_color"]}')
    if content.get('catalog'):
        lines.append('  composition, construction and source attribution')
    if content.get('purchase_sources'):
        lines.append(f'  {len(content["purchase_sources"])} place(s) to buy it, without private notes')
    missing = [k for k in PROPERTY_UNITS if k not in supplied]
    lines += ['', 'Not supplied, and left empty rather than zero: ' + (', '.join(missing) or 'nothing'), '']
    lines.append('Values marked "user" are edits made in SewEasy. '
                 + ('The original test measurements in the companion file were not rewritten, so they '
                    'remain the original laboratory data, not a new measurement.' if has_measurements else
                    'No laboratory measurement file accompanies this material.'))
    lines.append('No proprietary solver parameters for any other application are included.')
    return '\n'.join(lines).encode('utf-8')


def export_fabric(record, source_bytes=None, source_name=None, bundle=False):
    """A restricted U3MA archive, or with `bundle` the same files as an ordinary ZIP to unpack."""
    content = record['content']
    if source_bytes:
        files, manifest, document, _ = read_package(source_bytes, source_name)
    else:
        files, manifest, document = {}, 'material.u3m', empty_document(record['name'])
    material = document['material']
    material.update(id=str(uuid4()) if record.get('standard') else record['id'],
                    name=record['name'], description=content['description'],
                    modified=datetime.now(timezone.utc).isoformat())
    material['physics'] = material['physics'] or empty_document(record['name'])['material']['physics']
    for key in ('weight', 'thickness'):
        material['physics'][key] = content['properties'][key]['value']
    document['custom'] = document['custom'] or {}
    previous = document['custom'].get('seweasy')
    document['custom']['seweasy'] = dict(previous if isinstance(previous, dict) else {},
        schema=1, properties=content['properties'], solver_tuning=content['solver_tuning'])
    # Where to buy travels with the fabric; the owner's private notes never leave the account.
    from webapp.fabric_sources import public
    document['custom']['seweasy'].pop('purchase_sources', None)
    if content.get('purchase_sources'):
        document['custom']['seweasy']['purchase_sources'] = public(content['purchase_sources'])
    # The library's own swatch colour; U3M front/back maps stay as the vendor wrote them.
    document['custom']['seweasy'].pop('display_color', None)
    if (content.get('appearance') or {}).get('display_color'):
        document['custom']['seweasy']['display_color'] = content['appearance']['display_color']
    from webapp.fabric_catalog import metadata
    catalog = metadata(content.get('catalog'))
    if catalog is not None:
        document['custom']['seweasy']['catalog'] = catalog
        # Attribution is readable without software that understands our extension.
        credits = [catalog['composition'], catalog['construction'], catalog['notes']]
        for ref in catalog['references']:
            credits.append(f'{ref["title"]}\n{ref["authors"]}\n{ref["url"]}\n'
                           f'{ref["license"]} {ref["license_url"]}')
        credits.append('SewEasy estimates and conversions are identified per property in material.u3m. '
                       'These are not measurements of every fabric with the same fiber composition.')
        credit_bytes = '\n\n'.join(credits).encode('utf-8')
        credit_path, suffix = 'seweasy-fabric-sources.txt', 2
        folded_paths = {p.casefold(): p for p in files}
        while credit_path.casefold() in folded_paths and files[folded_paths[credit_path.casefold()]] != credit_bytes:
            credit_path = f'seweasy-fabric-sources-{suffix}.txt'
            suffix += 1
        credit_path = folded_paths.get(credit_path.casefold(), credit_path)
        files[credit_path] = credit_bytes
    _validate(document, 'u3m_schema.json')
    files[manifest] = _encode(document)
    # Replace our own earlier notes; never a vendor's file that happens to share the name.
    notes_path, suffix = str(PurePosixPath(manifest).parent / NOTES_PATH).lstrip('./'), 2
    folded_paths = {p.casefold(): p for p in files}
    while notes_path.casefold() in folded_paths and not files[folded_paths[notes_path.casefold()]].startswith(
            NOTES_HEADING.encode()):
        notes_path = str(PurePosixPath(manifest).parent / f'seweasy-export-notes-{suffix}.txt').lstrip('./')
        suffix += 1
    files[folded_paths.get(notes_path.casefold(), notes_path)] = export_notes(
        record, has_measurements=bool((content.get('source') or {}).get('has_raw_measurements')))
    if not bundle:
        return pack(files)
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(_path(name), data)
    return output.getvalue()


def sample_package():
    """Our minimal material wrapper around Vizoo's unmodified published FAB example."""
    document = empty_document('SU-1098 Cupro', 'c154fbdc-e515-4a98-b27b-17a7173578ce')
    document['material']['description'] = 'Published Browzwear FAB measurements; SewEasy U3M wrapper. No visual textures.'
    document['material']['physics'].update(devices=dict(fab='physics.json'),
        composition=dict(parts=[dict(ratio=1, type='Rayon', name=None)]),
        material_type=dict(type='Woven', name=None))
    return pack({'material.u3m': _encode(document), 'physics.json': (SPEC / 'cupro_physics.json').read_bytes(),
                 'LICENSE.txt': (SPEC / 'LICENSE').read_bytes()})
