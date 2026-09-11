"""Verify actual solver output contracts, without declaring a drape physically valid."""
import json
from pathlib import Path

import numpy as np
import trimesh

OUTPUT = Path(__file__).resolve().parents[1] / 'output/simulator-benchmark'


def verify():
    checked, expected_failures = [], []
    for path in sorted(OUTPUT.glob('*/*/result.json')):
        report = json.loads(path.read_text())
        name = path.parent.relative_to(OUTPUT).as_posix()
        if report.get('status') == 'failed':
            expected_failures.append(name)
            continue
        geometry = path.parent / 'geometry.npz'
        if not geometry.exists():
            geometry = path.parent.parent / 'mesh.npz'
        data = np.load(geometry)
        trajectory = np.load(path.parent / 'trajectory.npz')
        frames, positions = trajectory['frame_indices'], trajectory['positions']
        assert frames[0] == 0 and frames[-1] == report['frames'], name
        assert len(frames) == len(positions) and np.all(np.diff(frames) > 0), name
        assert positions.shape[1:] == data['vertices'].shape, name
        assert np.isfinite(positions).all(), name
        assert np.max(np.linalg.norm(positions[-1] - positions[0], axis=1)) > 1e-6, name
        assert len(report['frame_ms']) == report['frames'], name
        assert np.isclose(np.median(report['frame_ms']), report['frame_ms_median']), name
        assert data['faces'].min() >= 0 and data['faces'].max() < positions.shape[1], name
        glb = trimesh.load(path.parent / 'drape.glb', force='scene', process=False)
        assert sum(len(m.faces) for m in glb.geometry.values()) == len(data['faces']) + len(data['body_faces']), name
        exported = np.concatenate([m.vertices for m in glb.geometry.values()])
        expected = np.concatenate([positions[-1], data['body_vertices']])
        np.testing.assert_allclose(exported.min(axis=0), expected.min(axis=0), atol=1e-5, err_msg=name)
        np.testing.assert_allclose(exported.max(axis=0), expected.max(axis=0), atol=1e-5, err_msg=name)
        assert report['quality']['finite'], name
        checked.append(name)
    result = dict(artifact_contracts_passed=checked, recorded_solver_failures=expected_failures,
                  note='Checks motion, topology, finite output, frame accounting and GLB export. '
                       'Does not certify contact, fabric calibration or garment fit.')
    (OUTPUT / 'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    verify()
