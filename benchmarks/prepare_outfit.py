"""CPU-only fixture: independent striped dress shirt and dark trousers."""
import sys, json
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gui.gui_pattern import GUIPattern
from gui.browser_drape import prepare_scene

state=GUIPattern(draft=False)
try:
    shirt=deepcopy(state.design_params)
    shirt['fabric']['kind']['v']='pinstripe'
    shirt['fabric']['fg']['v']='#e7edf4'
    shirt['fabric']['bg']['v']='#27496a'
    shirt['fabric']['scale']['v']=.7
    pants=deepcopy(state.design_params)
    pants['meta']['upper']['v']=None
    pants['meta']['bottom']['v']='Pants'
    pants['meta']['wb']['v']='FittedWB'
    items=[dict(id='shirt',name='Striped Oxford',version=1,params=shirt,appearance=dict(fabric_color='#27496a',panel_colors={},panel_stiffness={})),
           dict(id='trousers',name='Trousers',version=1,params=pants,appearance=dict(fabric_color='#30384a',panel_colors={},panel_stiffness={}))]
    state.load_outfit(items);state.reload_garment()
    out=ROOT/'output/webgpu';out.mkdir(parents=True,exist_ok=True)
    prepare_scene(state,out/'outfit-test.json')
    path=out/'manifest.json';manifest=json.loads(path.read_text());manifest=[m for m in manifest if m['name']!='outfit-test']
    manifest.append(dict(name='outfit-test',label='Striped shirt and trousers',path='outfit-test.json'));path.write_text(json.dumps(manifest))
    print('Prepared outfit-test.json')
finally:state.release()
