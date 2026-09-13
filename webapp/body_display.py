"""Cached mannequin GLBs for account previews; the studio uses WebGPU buffers."""

from pathlib import Path
import hashlib
import json

import trimesh
from nicegui import app

from gui.gui_pattern import display_to_base_rgba

BODY_GLB_FILE = './assets/bodies/mean_all_display.glb'
BODY_TONE_CACHE = Path('./tmp_gui/body_tones')

BODY_TONE_CACHE.mkdir(parents=True, exist_ok=True)
# Tone files are content-keyed by color, body assets are immutable ->
# both can be cached by the browser for a long time
app.add_static_files('/body_tones', str(BODY_TONE_CACHE),
                     max_cache_age=30 * 24 * 3600)


def tinted_body_glb_url(color: str) -> str:
    """URL of the display body tinted with a skin tone (cached by tone)"""
    name = f'body_{color.lstrip("#").lower()}.glb'
    path = BODY_TONE_CACHE / name
    if not path.exists():
        body = trimesh.load(BODY_GLB_FILE)
        for geom in body.geometry.values():
            geom.visual.material.baseColorFactor = display_to_base_rgba(color)
        body.export(path)
    return f'/body_tones/{name}'


def profile_body_glb_url(color, measurements):
    """Use the same fitted surface as the studio; cache by profile and tone."""
    from seweasy.meshgen.body_fit import fit_body
    color = color or '#f9f2e4'
    key = json.dumps(['body-fit-v1', color, measurements], sort_keys=True, allow_nan=False)
    name = f'fitted_{hashlib.sha256(key.encode()).hexdigest()[:24]}.glb'
    path = BODY_TONE_CACHE / name
    if not path.exists():
        body, _ = fit_body(measurements)
        body.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=display_to_base_rgba(color), roughnessFactor=.9, metallicFactor=0))
        body.export(path)
    return f'/body_tones/{name}'
