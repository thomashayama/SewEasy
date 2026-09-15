"""Content-addressed previews: designs and appearance, never a user's body profile."""
import base64
from hashlib import sha256
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THUMBNAIL_VERSION = 'default-mannequin-webgpu-v1'
SIZE = (384, 448)


@lru_cache(maxsize=1)
def _default_body_key():
    return sha256((ROOT / 'assets/bodies/mean_all.yaml').read_bytes()).hexdigest()


def thumbnail_key(items):
    if not items:
        raise ValueError('A thumbnail needs at least one garment.')
    def look(item):
        appearance = item.get('appearance', {})
        return dict(fabric_color=appearance.get('fabric_color') or '#b7cde5',
                    **{field: appearance.get(field, {}) for field in
                       ('panel_colors', 'panel_fabrics', 'panel_stiffness', 'panel_materials')})
    recipe = dict(version=THUMBNAIL_VERSION, body=_default_body_key(),
                  garments=[dict(params=g['params'], appearance=look(g)) for g in items])
    return sha256(json.dumps(recipe, sort_keys=True, separators=(',', ':'), default=float).encode()).hexdigest()


def normalize_image(data_url):
    """Accept a bounded raster from the renderer; strip all uploaded metadata."""
    from PIL import Image
    if not isinstance(data_url, str) or len(data_url) > 400_000 or not data_url.startswith('data:image/webp;base64,'):
        raise ValueError('Invalid thumbnail image.')
    try:
        raw = base64.b64decode(data_url.split(',', 1)[1], validate=True)
        with Image.open(BytesIO(raw)) as image:
            if image.size != SIZE or image.format != 'WEBP':
                raise ValueError('Invalid thumbnail dimensions or format.')
            out = BytesIO()
            image.convert('RGB').save(out, format='WEBP', quality=86)
        return 'data:image/webp;base64,' + base64.b64encode(out.getvalue()).decode()
    except Exception as error:
        raise ValueError('Invalid thumbnail image.') from error


def bundled_thumbnail(key):
    path = ROOT / 'assets/garment_thumbnails' / f'{key}.webp'
    return f'/garment-thumbnails/{key}.webp' if path.is_file() else None


def prepare_thumbnail_scene(items, target):
    """CPU drafting/meshing only; isolated from the user's working pattern/body."""
    from gui.gui_pattern import GUIPattern
    from gui.outfit import OutfitProgram
    from gui.browser_drape import prepare_scene
    pattern = GUIPattern(draft=False)  # Always loads mean_all.yaml, not the user's profile.
    try:
        pattern.load_outfit(items)
        pattern.sew_pattern = OutfitProgram(pattern.body_params, pattern.outfit_items)
        return prepare_scene(pattern, target)
    finally:
        pattern.release()
