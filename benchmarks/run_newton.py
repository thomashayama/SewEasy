"""End-to-end Newton garment trial. Run one solver per process for clean timing.

Times a full 1/60 s simulation frame, including all substeps and collision
detection, synchronizing the GPU. Rendering and readback are measured separately.
This is a fixed-topology drape experiment, not a production simulator.
"""
import argparse
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path

import newton
import numpy as np
import trimesh
import warp as wp
from newton.solvers import style3d


def build(data, solver_name, stiffness, panel_stiffness, density=0.3):
    builder = newton.ModelBuilder(up_axis=newton.Axis.Y)
    builder.default_tri_ke = stiffness
    newton.solvers.SolverStyle3D.register_custom_attributes(builder)
    style3d.add_cloth_mesh(
        builder, pos=wp.vec3(0), rot=wp.quat_identity(), vel=wp.vec3(0),
        vertices=data['vertices'].tolist(), indices=data['faces'].flatten().tolist(),
        panel_verts=data['uv'].tolist(), panel_indices=data['uv_faces'].flatten().tolist(),
        density=density, particle_radius=0.002,
        tri_aniso_ke=wp.vec3(stiffness, stiffness, stiffness * 0.1),
        tri_ka=stiffness, tri_kd=0.000002,
        edge_aniso_ke=wp.vec3(0.00002, 0.00001, 0.000005), edge_kd=0.0,
    )
    if len(builder.tri_indices) != len(data['faces']):
        raise ValueError('Adapter dropped triangles')
    if min(builder.particle_mass) <= 0:
        raise ValueError('Unreferenced/zero-mass vertex')
    rest = data['uv'][data['uv_faces']]
    rest_area = np.linalg.det(np.stack([rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]], axis=-1)) / 2
    if np.any(rest_area <= 0) or not np.isclose(sum(builder.particle_mass), rest_area.sum() * density):
        raise ValueError('Cloth mass must derive from positive 2D fabric rest areas')
    if solver_name == 'vbd':
        # VBD uses dihedral bending. A flat rest angle is intentional for cloth;
        # seam construction/fold-specific rest angles remain a future feature.
        builder.edge_rest_angle = [0.0] * len(builder.edge_rest_angle)
        builder.edge_bending_properties = [(0.00002, 0.0)] * len(builder.edge_indices)
        builder.color(include_bending=True)
    edge_multiplier = {}
    for face, panel in zip(data['faces'], data['face_panels']):
        for a, b in [(face[0], face[1]), (face[1], face[2]), (face[2], face[0])]:
            key = tuple(sorted((int(a), int(b))))
            edge_multiplier[key] = max(edge_multiplier.get(key, 1.0), panel_stiffness.get(str(panel), 1.0))
    for i, edge in enumerate(builder.edge_indices):
        multiplier = edge_multiplier.get(tuple(sorted((int(edge[2]), int(edge[3])))), 1.0)
        ke, kd = builder.edge_bending_properties[i]
        builder.edge_bending_properties[i] = (ke * multiplier, kd)
    body = newton.Mesh(data['body_vertices'], data['body_faces'].flatten())
    cfg = builder.default_shape_cfg.copy()
    cfg.mu = 0.5
    # Match Newton's own garment example: an explicit stationary body.
    # Neither cloth solver integrates this body's transform.
    builder.add_shape_mesh(body=builder.add_body() if solver_name == 'style3d' else -1,
                           mesh=body, cfg=cfg)
    return builder.finalize(device='cuda:0')


def quality(vertices, data):
    if not np.isfinite(vertices).all():
        return {'finite': False}
    rest = data['uv'][data['uv_faces']]
    dm = np.stack([rest[:, 1] - rest[:, 0], rest[:, 2] - rest[:, 0]], axis=-1)
    world = vertices[data['faces']]
    ds = np.stack([world[:, 1] - world[:, 0], world[:, 2] - world[:, 0]], axis=-1)
    singular = np.linalg.svd(ds @ np.linalg.inv(dm), compute_uv=False)
    body = trimesh.Trimesh(data['body_vertices'], data['body_faces'], process=False)
    inside = np.concatenate([body.contains(chunk) for chunk in np.array_split(vertices, 20)])
    penetration = []
    if inside.any():
        for chunk in np.array_split(vertices[inside], max(1, int(inside.sum()) // 100)):
            _, dist, _ = trimesh.proximity.closest_point(body, chunk)
            penetration.extend(dist.tolist())
    return dict(finite=True, stretch_p50=float(np.median(singular[:, 0])),
                stretch_p95=float(np.percentile(singular[:, 0], 95)),
                stretch_max=float(singular[:, 0].max()),
                body_inside_vertices=int(inside.sum()),
                body_penetration_max_mm=float(max(penetration, default=0) * 1000),
                body_watertight=bool(body.is_watertight),
                bounds_m=[vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()])


def run(args):
    started = time.perf_counter()
    data = dict(np.load(args.mesh))
    directory = args.mesh.parent / args.label
    directory.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((args.mesh.parent / 'prepare.json').read_text())
    data['uv'] = data['uv'].copy()
    data['uv'][:, 0] *= args.rest_width_scale
    if args.start_from:
        source_geometry = args.start_from.parent / 'geometry.npz'
        if not source_geometry.exists():
            source_geometry = args.start_from.parent.parent / 'mesh.npz'
        source_data = np.load(source_geometry)
        if not np.array_equal(source_data['faces'], data['faces']):
            raise ValueError('Warm-start face topology mismatch')
        data['vertices'] = np.load(args.start_from)['positions'][-1].astype(np.float64)
        if len(data['vertices']) != int(data['faces'].max()) + 1:
            raise ValueError('Warm-start topology mismatch')
    wp.init()
    wp.set_device('cuda:0')
    setup_start = time.perf_counter()
    model = build(data, args.solver, args.stiffness, metadata['panel_stiffness'])
    model.soft_contact_ke = args.contact_stiffness
    model.soft_contact_kd = 0.1
    model.soft_contact_mu = 0.5
    pipeline = newton.CollisionPipeline(model, soft_contact_gap=0.005)
    contacts = pipeline.contacts()
    if args.solver == 'style3d':
        solver = newton.solvers.SolverStyle3D(model, iterations=args.iterations)
        solver.collision.radius = 0.003
    else:
        solver = newton.solvers.SolverVBD(
            model, iterations=args.iterations, particle_enable_self_contact=True,
            particle_self_contact_margin=0.006, particle_self_contact_gap=0.003,
            particle_vertex_contact_buffer_size=64, particle_edge_contact_buffer_size=128,
            rigid_compliant_alm=True)
    state0, state1 = model.state(), model.state()
    control = model.control()
    model.set_gravity((0.0, -9.81, 0.0))
    dt = 1 / (60 * args.substeps)

    def frame():
        nonlocal state0, state1
        if not args.collide_substeps:
            pipeline.collide(state0, contacts)
        for _ in range(args.substeps):
            if args.collide_substeps:
                pipeline.collide(state0, contacts)
            state0.clear_forces()
            solver.step(state0, state1, control, contacts, dt)
            state0, state1 = state1, state0

    if args.substeps % 2:
        raise ValueError('Use an even number of substeps for graph replay')
    # Compile first, outside the timed steady-state loop. Recreate the solver
    # afterwards to discard its warmup contact/history state.
    frame()
    wp.synchronize()
    state0.particle_q.assign(data['vertices'])
    state1.particle_q.assign(data['vertices'])
    state0.particle_qd.zero_()
    state1.particle_qd.zero_()
    if args.solver == 'style3d':
        solver = newton.solvers.SolverStyle3D(model, iterations=args.iterations)
        solver.collision.radius = 0.003
    else:
        solver = newton.solvers.SolverVBD(
            model, iterations=args.iterations, particle_enable_self_contact=True,
            particle_self_contact_margin=0.006, particle_self_contact_gap=0.003,
            particle_vertex_contact_buffer_size=64, particle_edge_contact_buffer_size=128,
            rigid_compliant_alm=True)
    with wp.ScopedCapture() as capture:
        frame()
    wp.synchronize()
    setup_s = time.perf_counter() - setup_start
    frame_ms, snapshots, rms_velocity = [], [data['vertices'].astype(np.float32)], []
    frame_indices = [0]
    readback_s = 0.0
    for i in range(args.frames):
        tick = time.perf_counter()
        wp.capture_launch(capture.graph)
        wp.synchronize()
        frame_ms.append((time.perf_counter() - tick) * 1000)
        if (i + 1) % 10 == 0 or i + 1 == args.frames:
            tick = time.perf_counter()
            q = state0.particle_q.numpy()
            v = state0.particle_qd.numpy()
            readback_s += time.perf_counter() - tick
            snapshots.append(q.copy())
            frame_indices.append(i + 1)
            rms_velocity.append(float(np.sqrt(np.mean(np.sum(v * v, axis=1)))))
            if not np.isfinite(q).all() or np.abs(q).max() > 10:
                print('Simulation diverged', flush=True)
                break
        if (i + 1) % 60 == 0:
            print(f'{args.solver} {metadata["garment"]} frame {i+1}: '
                  f'{np.median(frame_ms[-60:]):.2f} ms', flush=True)
    vertices = state0.particle_q.numpy()
    simulation_s = sum(frame_ms) / 1000
    export_start = time.perf_counter()
    cloth = trimesh.Trimesh(vertices, data['faces'], process=False)
    cloth.visual.vertex_colors = [57, 135, 166, 255]
    body = trimesh.Trimesh(data['body_vertices'], data['body_faces'], process=False)
    body.visual.vertex_colors = [192, 170, 151, 255]
    if np.isfinite(vertices).all():
        cloth.export(directory / 'cloth.obj')
        trimesh.Scene({'garment': cloth, 'body': body}).export(directory / 'drape.glb')
        reloaded = trimesh.load(directory / 'drape.glb')
        assert sum(len(g.faces) for g in reloaded.geometry.values()) == len(cloth.faces) + len(body.faces)
    np.savez_compressed(directory / 'trajectory.npz', positions=np.asarray(snapshots),
                        frame_indices=np.asarray(frame_indices))
    export_s = time.perf_counter() - export_start
    qa_start = time.perf_counter()
    metrics = quality(vertices, data)
    metrics['rms_velocity_final_m_s'] = rms_velocity[-1] if rms_velocity else None
    metrics['settled'] = bool(rms_velocity and max(rms_velocity[-3:]) < 0.01)
    report = dict(solver=args.solver, label=args.label, **metadata,
                  newton=version('newton'), warp=version('warp-lang'), python=platform.python_version(),
                  device=wp.get_device().name, os=platform.platform(),
                  substeps=args.substeps, iterations=args.iterations, stiffness=args.stiffness,
                  contact_stiffness=args.contact_stiffness, collide_substeps=args.collide_substeps,
                  rest_width_scale=args.rest_width_scale, start_from=str(args.start_from) if args.start_from else None,
                  frames=len(frame_ms), simulated_seconds=len(frame_ms)/60,
                  setup_compile_s=setup_s, simulation_s=simulation_s,
                  frame_ms_median=float(np.median(frame_ms)),
                  frame_ms_p95=float(np.percentile(frame_ms, 95)),
                  readback_s=readback_s, export_s=export_s,
                  quality=metrics, quality_check_s=time.perf_counter()-qa_start,
                  total_process_work_s=time.perf_counter()-started,
                  frame_ms=frame_ms, rms_velocity_samples=rms_velocity,
                  limitations=['Uncalibrated material parameters; not equivalent across solvers',
                               'Original BoxMesh initialization, no old body-part drag or attachment constraints',
                               'Self-contact enabled; self-intersection count not measured',
                               'GPU compute benchmark, not browser physics or rendered FPS'])
    (directory / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ['frame_ms','rms_velocity_samples']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mesh', type=Path)
    parser.add_argument('--solver', choices=['style3d', 'vbd'], required=True)
    parser.add_argument('--label')
    parser.add_argument('--substeps', type=int, default=10)
    parser.add_argument('--iterations', type=int, default=10)
    parser.add_argument('--frames', type=int, default=300)
    parser.add_argument('--stiffness', type=float, default=1000.0)
    parser.add_argument('--contact-stiffness', type=float, default=10000.0)
    parser.add_argument('--collide-substeps', action='store_true')
    parser.add_argument('--rest-width-scale', type=float, default=1.0)
    parser.add_argument('--start-from', type=Path)
    args = parser.parse_args()
    args.label = args.label or args.solver
    if args.frames <= 0 or args.substeps <= 0 or args.iterations <= 0 or args.rest_width_scale <= 0:
        parser.error('Frames, substeps, iterations and rest width scale must be positive')
    if Path(args.label).name != args.label or args.label in ('.', '..'):
        parser.error('Label must be a single directory name')
    run(args)
