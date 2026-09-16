"""Thumbnails attached to garment/outfit revision IDs, on the default mannequin."""
import base64
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE = (384, 448)


def thumbnail_key(kind, revision_id):
    """The immutable saved version owns its image; no design/file hashing."""
    if kind not in ('garment', 'outfit') or not revision_id or revision_id == 'draft':
        raise ValueError('A thumbnail needs a saved garment or outfit ID.')
    return f'{kind}:{revision_id}'


def preview_key(items, garments, outfits, outfit_id=None):
    """Resolve a saved image, but don't show it as an unsaved edit's preview."""
    def unchanged(current, saved):
        return saved is not None and all(current.get(k) == saved.get(k) for k in ('id', 'params', 'appearance'))
    if outfit_id:
        saved = outfits.get(outfit_id)
        if saved and len(items) == len(saved['garments']) and all(
                unchanged(a, b) for a, b in zip(items, saved['garments'])):
            return thumbnail_key('outfit', outfit_id)
    elif len(items) == 1 and unchanged(items[0], garments.get(items[0].get('id'))):
        return thumbnail_key('garment', items[0]['id'])
    return None


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
    from webapp.garment_catalog import STARTERS
    standards = {thumbnail_key('garment', f'standard:{kind}'): kind for kind, *_ in STARTERS}
    kind = standards.get(key)
    if kind and (ROOT / 'assets/garment_thumbnails' / f'{kind}.webp').is_file():
        return f'/garment-thumbnails/{kind}.webp'
    return None


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
