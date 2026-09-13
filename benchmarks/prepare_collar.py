"""Prepare CPU-only collar regression scenes, including a synthetic body profile."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml
from assets.bodies.body_params import BodyParameters
from assets.garment_programs.dress_shirt import DressShirt
from seweasy.meshgen.body_fit import fit_body
from seweasy.meshgen.boxmeshgen import BoxMesh
from seweasy.meshgen.webgpu import build_scene, panel_mesh_data
from seweasy.pattern.core import BasicPattern
from webapp.measurement_guide import scale_coupled


def prepare(name, edits, point=3, resolution=1.5):
    body = BodyParameters(str(ROOT/'assets/bodies/mean_all.yaml'))
    values = {**body.params, **edits}
    values.update(scale_coupled(body.params, values))
    body.params = values
    body.eval_dependencies()
    design = yaml.safe_load((ROOT/'assets/design_params/dress-shirt.yaml').read_text())['design']
    design['dress_shirt']['collar_point']['v'] = point
    pattern = DressShirt(body, design).assembly()
    with TemporaryDirectory() as work:
        BasicPattern.serialize(pattern, work, to_subfolder=False)
        box = BoxMesh(Path(work)/'DressShirt_specification.json', resolution)
        box.load()
        mesh, fit = fit_body(values)
        scene = build_scene(panel_mesh_data(box, mesh), dict(garment='dress-shirt',
            resolution_cm=resolution, panels=len(box.panelNames),
            panel_stiffness=pattern.pattern['panel_stiffness']), name)
    scene['body_fit'] = fit
    out = ROOT/'output/webgpu'
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{name}.json').write_text(json.dumps(scene, separators=(',', ':')), encoding='utf-8')
    path=out/'manifest.json'
    manifest=json.loads(path.read_text()) if path.exists() else []
    manifest=[m for m in manifest if m['name']!=name]
    manifest.append(dict(name=name,label=name,path=f'{name}.json'))
    path.write_text(json.dumps(manifest), encoding='utf-8')
    print(name, len(scene['vertices']), 'vertices,', len(scene['hinges']), 'collar hinges')


if __name__=='__main__':
    prepare('collar-default', {})
    prepare('collar-fine', {}, resolution=1)
    prepare('collar-custom', dict(height=185, bust=120, underbust=107, waist=104,
        hips=124, shoulder_w=43, waist_line=42, hips_line=25, arm_length=62,
        wrist=20, leg_circ=70), point=5)
