"""Regenerate the six bundled presets with the real browser WebGPU renderer.

Run this script, then open http://127.0.0.1:8768 and click Regenerate.
Only built-in presets are drafted and only their bundled WebPs can be written.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webapp.garment_catalog import standard_garments
from webapp.thumbnail_cache import normalize_image, prepare_thumbnail_scene, transparent_thumbnail

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<title>SewEasy — Studio glow</title>
<style>
body{margin:32px;background:#141c24;color:#e7edf2;font:15px system-ui}
button{padding:12px 18px;cursor:pointer}main{display:flex;flex-wrap:wrap;gap:20px;margin-top:24px}
figure{margin:0;width:220px}canvas,img{width:220px;height:257px;border-radius:8px;background:radial-gradient(ellipse at 50% 38%,#52606b 0%,#303d48 40%,#202c37 80%)}
figcaption{padding:12px 0}#status{min-height:24px}
</style><h1>SewEasy · Studio glow</h1><p>Built-in garments on the default mannequin</p>
<button id="start">Regenerate</button><p id="status" role="status">Ready</p><main></main>
<script type="module">
import {captureThumbnail} from '/webgpu/capture.js?v=2';
const presets=PRESETS;
document.querySelector('#start').onclick=async()=>{
 const button=document.querySelector('#start'),status=document.querySelector('#status');button.disabled=true;
 try{
  document.querySelector('main').replaceChildren();
  for(const {standard,name} of presets){
   const figure=document.createElement('figure'),canvas=document.createElement('canvas'),label=document.createElement('figcaption');
   label.textContent=name;figure.append(canvas,label);document.querySelector('main').append(figure);
   const response=await fetch('/scenes/'+standard+'.json');if(!response.ok)throw Error('Scene unavailable');
   const image=await captureThumbnail(await response.json(),canvas,frame=>status.textContent=name+' · '+frame+'/180');
   const preview=document.createElement('img');preview.src=image;preview.alt=name+' on the default mannequin';canvas.replaceWith(preview);
   const saved=await fetch('/save/'+standard,{method:'POST',body:JSON.stringify({image})});
   if(!saved.ok)throw Error('Could not save '+name);
  }
  status.textContent='All six transparent thumbnails saved.';document.body.dataset.state='complete';
 }catch(error){status.textContent=error.message;document.body.dataset.state='failed';}
 finally{button.disabled=false;}
};
</script></html>'''


def main():
    presets = standard_garments()
    names = {item['standard'] for item in presets}
    page = PAGE.replace('PRESETS', json.dumps([{'standard': g['standard'], 'name': g['name']} for g in presets])).encode()
    with TemporaryDirectory(prefix='seweasy-thumbnails-') as tmp:
        scenes = Path(tmp)
        for item in presets:
            print('Preparing ' + item['name'], flush=True)
            prepare_thumbnail_scene([item], scenes / (item['standard'] + '.json'))

        class Handler(BaseHTTPRequestHandler):
            def reply(self, data, content_type):
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == '/':
                    return self.reply(page, 'text/html; charset=utf-8')
                if path.startswith('/webgpu/'):
                    target = (ROOT / 'gui' / path.lstrip('/')).resolve()
                    if target.parent == (ROOT / 'gui/webgpu').resolve() and target.suffix == '.js' and target.is_file():
                        return self.reply(target.read_bytes(), 'text/javascript')
                if path.startswith('/scenes/') and path.removeprefix('/scenes/').removesuffix('.json') in names:
                    target = scenes / path.rsplit('/', 1)[1]
                    if target.is_file():
                        return self.reply(target.read_bytes(), 'application/json')
                self.send_error(404)

            def do_POST(self):
                if self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
                    return self.send_error(403)
                name = self.path.removeprefix('/save/')
                length = int(self.headers.get('Content-Length', '0'))
                if not self.path.startswith('/save/') or name not in names or not 0 < length < 410_000:
                    return self.send_error(400)
                try:
                    image = normalize_image(json.loads(self.rfile.read(length))['image'])
                    if not transparent_thumbnail(image):
                        raise ValueError('Capture must have transparency')
                    (ROOT / 'assets/garment_thumbnails' / (name + '.webp')).write_bytes(base64.b64decode(image.split(',', 1)[1]))
                    self.reply(b'{}', 'application/json')
                except (ValueError, KeyError, TypeError):
                    self.send_error(400)

        print('Ready: http://127.0.0.1:8768', flush=True)
        ThreadingHTTPServer(('127.0.0.1', 8768), Handler).serve_forever()


if __name__ == '__main__':
    main()
