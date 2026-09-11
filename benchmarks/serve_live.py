"""Local diagnostic server: live CUDA cloth in a browser, plus recorded trials.

Bind to loopback only. The browser renders and requests frames; Newton performs
physics on the host GPU. This is not a browser/WASM physics implementation.
"""
import argparse
import json
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import numpy as np
import newton
import trimesh
import warp as wp

from run_newton import build, quality

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/simulator-benchmark'


class LiveCloth:
    def __init__(self, data, metadata):
        self.data, self.metadata = data, metadata
        self.model = build(data, 'style3d', 1000, metadata['panel_stiffness'])
        self.model.soft_contact_ke = 10000
        self.model.soft_contact_kd = 0.1
        self.model.soft_contact_mu = 0.5
        self.model.set_gravity((0, -9.81, 0))
        self.pipeline = newton.CollisionPipeline(self.model, soft_contact_gap=0.005)
        self.contacts = self.pipeline.contacts()
        self.state0, self.state1 = self.model.state(), self.model.state()
        self.control = self.model.control()
        self.new_solver()
        self.frame()
        wp.synchronize()
        for state in (self.state0, self.state1):
            state.particle_q.assign(data['vertices'])
            state.particle_qd.zero_()
        self.new_solver()
        with wp.ScopedCapture() as capture:
            self.frame()
        self.graph = capture.graph
        wp.synchronize()
        self.frame_index = 0
        self.snapshots = [data['vertices'].astype(np.float32)]
        self.gpu_ms = []
        self.is_edit = False

    def new_solver(self):
        self.solver = newton.solvers.SolverStyle3D(self.model, iterations=4)
        self.solver.collision.radius = 0.003

    def frame(self):
        for _ in range(4):
            self.pipeline.collide(self.state0, self.contacts)
            self.state0.clear_forces()
            self.solver.step(self.state0, self.state1, self.control, self.contacts, 1 / 240)
            self.state0, self.state1 = self.state1, self.state0

    def step(self):
        tick = time.perf_counter()
        wp.capture_launch(self.graph)
        wp.synchronize()
        gpu_ms = (time.perf_counter() - tick) * 1000
        positions = self.state0.particle_q.numpy()
        if not np.isfinite(positions).all():
            raise RuntimeError('Non-finite solver output')
        self.frame_index += 1
        self.gpu_ms.append(gpu_ms)
        if self.frame_index % 10 == 0:
            self.snapshots.append(positions.copy())
        return positions, gpu_ms


class Handler(SimpleHTTPRequestHandler):
    session = None
    run_directory = None
    runs = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def log_message(self, fmt, *args):
        # Avoid a console write in every timed frame.
        if self.path != '/api/step':
            super().log_message(fmt, *args)

    def do_POST(self):
        # A local experiment, deliberately without remote access or CORS.
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 8192:
                raise ValueError('Request too large')
            payload = json.loads(self.rfile.read(length)) if length else {}
            if self.path == '/api/start':
                run = self.runs[payload['run']]
                result = json.loads((run / 'result.json').read_text())
                if result['solver'] != 'style3d' or result['label'] != 'style3d-tuned':
                    raise ValueError('Choose a style3d-tuned recording for live simulation')
                data = dict(np.load(run.parent / 'mesh.npz'))
                metadata = json.loads((run.parent / 'prepare.json').read_text())
                tick = time.perf_counter()
                Handler.session = LiveCloth(data, metadata)
                Handler.run_directory = run.parent
                self.reply_json({'setup_ms': (time.perf_counter() - tick) * 1000})
            elif self.path == '/api/step':
                if self.session is None:
                    raise ValueError('Start a live session first')
                positions, gpu_ms = self.session.step()
                body = positions.astype('<f4', copy=False).tobytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('X-GPU-ms', str(gpu_ms))
                self.send_header('X-Sim-Frame', str(self.session.frame_index))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == '/api/width':
                if self.session is None:
                    raise ValueError('Start a live session first')
                data = dict(self.session.data)
                data['vertices'] = self.session.state0.particle_q.numpy().astype(np.float64)
                data['uv'] = data['uv'].copy()
                data['uv'][:, 0] *= 1.02
                tick = time.perf_counter()
                Handler.session = LiveCloth(data, self.session.metadata)
                self.session.is_edit = True
                self.reply_json({'setup_ms': (time.perf_counter() - tick) * 1000,
                                 'edit': '2% wider rest UV, fixed topology, model rebuilt'})
            elif self.path == '/api/finish':
                if self.session is None or not self.session.gpu_ms:
                    raise ValueError('No frames to summarize')
                s = self.session
                output = self.run_directory / ('live-width-edit' if s.is_edit else 'live-style3d')
                output.mkdir(exist_ok=True)
                q = s.state0.particle_q.numpy()
                cloth = trimesh.Trimesh(q, s.data['faces'], process=False)
                avatar = trimesh.Trimesh(s.data['body_vertices'], s.data['body_faces'], process=False)
                trimesh.Scene({'garment': cloth, 'body': avatar}).export(output / 'drape.glb')
                np.savez_compressed(output / 'trajectory.npz', positions=np.asarray(s.snapshots),
                                    frame_indices=np.arange(len(s.snapshots)) * 10)
                report = dict(solver='style3d', label=output.name, **s.metadata,
                              frames=s.frame_index, simulated_seconds=s.frame_index/60,
                              frame_ms_median=float(np.median(s.gpu_ms)),
                              frame_ms_p95=float(np.percentile(s.gpu_ms, 95)),
                              frame_ms=s.gpu_ms, browser=payload, quality=quality(q, s.data),
                              limitations=['Live physics ran in CUDA on the host; browser rendered positions',
                                           'Loopback transport, one client, fixed mannequin and topology',
                                           'Width edit rebuilds model and clears velocity; no pattern redraft'])
                (output / 'result.json').write_text(json.dumps(report, indent=2))
                self.reply_json({'saved': output.name, 'quality': report['quality']})
            else:
                self.send_error(404)
        except Exception as exc:
            self.reply_json({'error': str(exc)}, status=400)

    def reply_json(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    for run in json.loads((OUTPUT / 'manifest.json').read_text()):
        Handler.runs[run['path']] = (OUTPUT / run['path']).parent
    wp.init()
    wp.set_device('cuda:0')
    print(f'Live GPU preview: http://127.0.0.1:{args.port}', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
