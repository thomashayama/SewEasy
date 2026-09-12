"""Static WebGPU preview + optional JSON benchmark archive. Standard library only.

No GPU library, physics computation, or render operation runs in this process.
Any ordinary static server can host the generated page; /__results is optional.
"""
import argparse
import json
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'output/webgpu'


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def do_POST(self):
        if self.path != '/__results':
            self.send_error(404)
            return
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            self.send_error(403)
            return
        length = int(self.headers.get('Content-Length', 0))
        if length <= 0 or length > 20_000_000:
            self.send_error(400)
            return
        try:
            data = json.loads(self.rfile.read(length))
            name = data['report']['scene']
            allowed = {x['name'] for x in json.loads((OUTPUT / 'manifest.json').read_text())}
            if name not in allowed:
                raise ValueError('Unknown garment')
            out = OUTPUT / 'results'
            out.mkdir(exist_ok=True)
            path = out / f'{name}_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
            path.write_text(json.dumps(data))
            body = json.dumps({'path': path.relative_to(OUTPUT).as_posix()}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ValueError, KeyError, TypeError):
            self.send_error(400)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    print(f'Browser WebGPU preview: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
