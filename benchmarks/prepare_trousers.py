"""CPU-only trouser regression drafts for the browser WebGPU harness."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.gui_pattern import GUIPattern
from gui.outfit import OutfitProgram
from gui.browser_drape import prepare_scene
from webapp.garment_catalog import starter_item
from webapp.measurement_guide import scale_coupled


def prepare(name, *, length=.9, flare=.7, custom=False, outfit=False):
    state = GUIPattern(draft=False)
    try:
        pants = starter_item('Pants')
        pants['params']['pants']['length']['v'] = length
        pants['params']['pants']['flare']['v'] = flare
        state.load_outfit(([starter_item('DressShirt')] if outfit else []) + [pants])
        if custom:
            values = {**state.body_params.params, 'height': 185, 'waist': 104,
                      'hips': 124, 'bust': 120, 'underbust': 107, 'leg_circ': 70,
                      'waist_line': 42, 'hips_line': 25, 'shoulder_w': 43,
                      'arm_length': 62, 'wrist': 20}
            values.update(scale_coupled(state.body_params.params, values))
            state.body_params.params = values
            state.body_params.eval_dependencies()
        state.sew_pattern = OutfitProgram(state.body_params, state.outfit_items)
        out = ROOT / 'output/webgpu'
        prepare_scene(state, out / f'{name}.json')
        path = out / 'manifest.json'
        manifest = json.loads(path.read_text()) if path.exists() else []
        manifest = [m for m in manifest if m['name'] != name]
        manifest.append(dict(name=name, label=name, path=f'{name}.json'))
        path.write_text(json.dumps(manifest), encoding='utf-8')
        print(name)
    finally:
        state.release()


if __name__ == '__main__':
    prepare('trousers-default')
    prepare('trousers-wide', flare=1)
    prepare('trousers-shorts', length=.3)
    prepare('trousers-custom', custom=True)
    prepare('trousers-outfit', outfit=True)
    for folder in ('benchmarks/webgpu', 'gui/webgpu'):
        for source in (ROOT / folder).iterdir():
            if source.is_file():
                shutil.copyfile(source, ROOT / 'output/webgpu' / source.name)
