"""Shared display-body helpers: skin-tinted mannequin GLBs.

The mannequin shape never changes — only its material tint does — so
tinted exports are cached on disk keyed by tone and served from one
static mount. Both the studio 3D view and the account page use this
cache; tinting is a trimesh load + export, so call it off the event
loop (run.io_bound / an executor) on a cache miss.
"""

from pathlib import Path

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
