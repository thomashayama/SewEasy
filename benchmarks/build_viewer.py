"""Package local simulation recordings for visual end-to-end inspection."""
import json
import shutil
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'output/simulator-benchmark'
manifest = []
for path in sorted(out.glob('*/*/result.json')):
    result = json.loads(path.read_text())
    if result.get('status') == 'failed' or not (path.parent / 'trajectory.npz').exists():
        continue
    data = np.load(path.parent / 'geometry.npz' if (path.parent / 'geometry.npz').exists()
                   else path.parent.parent / 'mesh.npz')
    trajectory = np.load(path.parent / 'trajectory.npz')
    brief = {k: result[k] for k in ['solver', 'garment', 'setup_compile_s', 'browser',
             'simulation_s', 'frame_ms_median', 'frame_ms_p95', 'quality'] if k in result}
    brief['quality'].pop('retained_on_body', None)  # Early heuristic was not a fit-quality test.
    playback = dict(positions=trajectory['positions'].tolist(),
                    frame_indices=trajectory['frame_indices'].tolist(),
                    faces=data['faces'].tolist(), body_vertices=data['body_vertices'].tolist(),
                    body_faces=data['body_faces'].tolist(), vertices=len(data['vertices']), metrics=brief)
    dest = path.parent / 'playback.json'
    dest.write_text(json.dumps(playback, separators=(',', ':')))
    manifest.append(dict(label=path.parent.parent.name + ' / ' + result['label'],
                         path=dest.relative_to(out).as_posix()))
(out / 'manifest.json').write_text(json.dumps(manifest))
shutil.copyfile(ROOT / 'benchmarks/viewer.html', out / 'index.html')
print(f'Packaged {len(manifest)} recordings')
