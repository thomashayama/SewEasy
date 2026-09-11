"""Trial libuipc with separate SewEasy panels and explicit seam constraints.

The same 2D rest triangles and initial panel transforms are used. Unlike
Newton's welded mesh, IPC uses duplicate seam vertices joined by soft stitches.
"""
import argparse
import json
import time
import traceback
from importlib.metadata import version
from pathlib import Path

import numpy as np
import trimesh
import uipc
from uipc import Logger, Timer, view
from uipc import builtin
from uipc.constitution import (DiscreteShellBending, ElasticModuli2D, Empty,
                              SoftPositionConstraint, SoftVertexStitch,
                              StrainLimitingBaraffWitkinShell)
from uipc.core import Engine, Scene, World
from uipc.geometry import label_surface, trimesh as make_mesh


def run(args):
    started = time.perf_counter()
    data = dict(np.load(args.mesh))
    out = args.mesh.parent / ('libuipc-separated' if args.separate_panels else 'libuipc')
    out.mkdir(exist_ok=True)
    metadata = json.loads((args.mesh.parent / 'prepare.json').read_text())
    report = dict(solver='libuipc', label=out.name, pyuipc=version('pyuipc'), **metadata)
    report['sewn_topology'] = 'separate panel meshes plus SoftVertexStitch constraints'
    report['separate_panels'] = args.separate_panels
    try:
        Timer.disable_all()
        Logger.set_level(Logger.Warn)
        engine = Engine('cuda', str(out / 'engine'))
        world = World(engine)
        config = Scene.default_config()
        config['dt'] = 1.0 / 60
        config['gravity'] = [[0.0], [-9.81], [0.0]]
        config['contact']['d_hat'] = 0.002
        config['newton']['max_iter'] = 100
        config['newton']['velocity_tol'] = 0.01
        scene = Scene(config)
        scene.contact_tabular().default_model(0.5, 1e5)
        shell, bending, stitch = StrainLimitingBaraffWitkinShell(), DiscreteShellBending(), SoftVertexStitch()
        panels, memberships = {}, {}
        uv_to_world = np.full(len(data['uv']), -1, dtype=int)
        uv_to_world[data['uv_faces'].flatten()] = data['faces'].flatten()
        for name in np.unique(data['face_panels']):
            face_mask = data['face_panels'] == name
            ids, inverse = np.unique(data['uv_faces'][face_mask], return_inverse=True)
            faces = inverse.reshape(-1, 3).astype(np.int32)
            initial = data['unsewn_vertices'][ids].copy()
            if args.separate_panels:
                center = initial.mean(axis=0)
                initial += [0.015 * np.sign(center[0]), 0, 0.015 * np.sign(center[2])]
            current = make_mesh(initial, faces)
            label_surface(current)
            shell.apply_to(current, stretch_moduli=ElasticModuli2D.youngs_poisson(5e4, 0.3),
                           shear_moduli=ElasticModuli2D.youngs_poisson(1e2, 0.3),
                           mass_density=150, thickness=0.001, strain_rate=100)
            bending.apply_to(current, 3e4, 0.3)
            rest = current.copy()
            view(rest.positions()).reshape(-1, 3)[:] = np.column_stack([data['uv'][ids], np.zeros(len(ids))])
            slot, _ = scene.objects().create(str(name)).geometries().create(current, rest)
            panels[str(name)] = (slot, current, ids)
            for local, uv_id in enumerate(ids):
                memberships.setdefault(int(uv_to_world[uv_id]), []).append((str(name), local))
        pairs = {}
        for members in memberships.values():
            for i in range(1, len(members)):
                a, b = members[0], members[i]
                pairs.setdefault((a[0], b[0]), []).append([a[1], b[1]])
        for i, ((a, b), indices) in enumerate(pairs.items()):
            ca = scene.contact_tabular().create(f'seam_{i}_a')
            cb = scene.contact_tabular().create(f'seam_{i}_b')
            scene.contact_tabular().insert(ca, cb, 0, 1e5, True)
            geo = stitch.create_geometry((panels[a][0], panels[b][0]),
                                         np.asarray(indices, dtype=np.int32), (ca, cb), 1000.0)
            scene.objects().create(f'seam_{i}').geometries().create(geo)
        body = make_mesh(data['body_vertices'], data['body_faces'])
        label_surface(body)
        Empty().apply_to(body, thickness=0.0)
        SoftPositionConstraint().apply_to(body, 1000.0)
        view(body.vertices().find(builtin.is_constrained))[:] = 1
        view(body.vertices().find(builtin.is_dynamic))[:] = 0
        body_element = scene.contact_tabular().create('body')
        body_element.apply_to(body)
        scene.contact_tabular().insert(body_element, body_element, 0, 0, False)
        scene.objects().create('body').geometries().create(body)
        report['stitch_pairs'] = sum(len(x) for x in pairs.values())
        report['status'] = 'initializing'
        (out / 'result.json').write_text(json.dumps(report, indent=2))
        world.init(scene)
        if not world.is_valid():
            raise RuntimeError('libuipc rejected the initial scene; see engine sanity-check output')
        report['setup_compile_s'] = time.perf_counter() - started
        def positions():
            return np.concatenate([np.asarray(view(slot.geometry().positions())).reshape(-1, 3).copy()
                                   for slot, _, _ in panels.values()])

        all_faces, all_uv, offset = [], [], 0
        for slot, _, ids in panels.values():
            all_faces.append(np.asarray(view(slot.geometry().triangles().topo())).reshape(-1, 3).copy() + offset)
            all_uv.append(data['uv'][ids])
            offset += len(ids)
        faces = np.concatenate(all_faces)
        qa_data = dict(data, vertices=positions(), faces=faces, uv=np.concatenate(all_uv), uv_faces=faces)
        np.savez_compressed(out / 'geometry.npz', **qa_data)
        snapshots, frame_indices = [positions()], [0]
        frame_ms = []
        for i in range(args.frames):
            tick = time.perf_counter()
            world.advance()
            world.retrieve()
            frame_ms.append((time.perf_counter() - tick) * 1000)
            if not world.is_valid():
                raise RuntimeError(f'libuipc world became invalid at frame {i+1}')
            if (i + 1) % 10 == 0 or i + 1 == args.frames:
                snapshots.append(positions())
                frame_indices.append(i + 1)
                print(f'libuipc frame {i+1}: {frame_ms[-1]:.2f} ms', flush=True)
        meshes = []
        for slot, _, _ in panels.values():
            current = slot.geometry()
            meshes.append(trimesh.Trimesh(np.asarray(view(current.positions())).reshape(-1, 3).copy(),
                                         np.asarray(view(current.triangles().topo())).reshape(-1, 3).copy(), process=False))
        cloth = trimesh.util.concatenate(meshes)
        cloth.export(out / 'cloth.obj')
        cloth.visual.vertex_colors = [57,135,166,255]
        avatar = trimesh.Trimesh(data['body_vertices'], data['body_faces'], process=False)
        avatar.visual.vertex_colors = [192,170,151,255]
        trimesh.Scene({'garment':cloth, 'body':avatar}).export(out / 'drape.glb')
        exported = trimesh.load(out / 'drape.glb')
        assert sum(len(g.faces) for g in exported.geometry.values()) == len(cloth.faces) + len(avatar.faces)
        np.savez_compressed(out / 'trajectory.npz', positions=np.asarray(snapshots,dtype=np.float32),
                            frame_indices=np.asarray(frame_indices))
        from run_newton import quality
        metrics = quality(positions(), qa_data)
        seam_gaps = []
        for (a, b), indices in pairs.items():
            pa = np.asarray(view(panels[a][0].geometry().positions())).reshape(-1,3)
            pb = np.asarray(view(panels[b][0].geometry().positions())).reshape(-1,3)
            indices = np.asarray(indices)
            seam_gaps.extend(np.linalg.norm(pa[indices[:,0]] - pb[indices[:,1]],axis=1).tolist())
        metrics['seam_gap_max_mm'] = max(seam_gaps,default=0) * 1000
        metrics['seam_gap_p95_mm'] = float(np.percentile(seam_gaps,95)) * 1000
        metrics['displacement_max_m'] = float(np.linalg.norm(positions()-snapshots[0],axis=1).max())
        if metrics['displacement_max_m'] < 1e-6:
            raise RuntimeError('No motion retrieved from the solver')
        report.update(status='completed', frames=len(frame_ms), simulation_s=sum(frame_ms)/1000,
                      simulated_seconds=len(frame_ms)/60, quality=metrics,
                      actual_vertices=len(qa_data['vertices']),
                      frame_ms_median=float(np.median(frame_ms)), frame_ms_p95=float(np.percentile(frame_ms,95)),
                      frame_ms=frame_ms,
                      limitations=['Separate soft seams; different topology and material model from Newton',
                                   'Frame timing includes GPU synchronization and geometry retrieval',
                                   'Cold first frame included; inspect per-frame timings',
                                   'Uncalibrated materials; no self-intersection count measured'])
    except Exception as exc:
        report.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        print(report['traceback'], flush=True)
    report['total_process_work_s'] = time.perf_counter() - started
    (out / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return report['status'] == 'completed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mesh', type=Path)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--separate-panels', action='store_true')
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error('Frames must be positive')
    raise SystemExit(0 if run(args) else 1)
