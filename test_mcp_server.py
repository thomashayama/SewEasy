"""Real MCP HTTP requests, account isolation, uploads and durable render results."""
import base64
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from webapp.db import Base
from webapp.models import User, AgentToken, AgentRender
from webapp import agent_tokens, base_garments, mcp_server
from webapp.wardrobe import Wardrobe
from test_thumbnails import raster


def panel_spec():
    return {'pattern': {'panels': {'front': {
        'vertices': [[0, 0], [40, 0], [40, 50], [0, 50]],
        'edges': [{'endpoints': [i, (i + 1) % 4]} for i in range(4)],
        'translation': [-20, 80, 20], 'rotation': [0, 0, 0]}}, 'stitches': []}}


class MCPTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        temp = self.stack.enter_context(TemporaryDirectory())
        self.engine = create_engine('sqlite:///' + str(Path(temp) / 'test.db'), connect_args={'check_same_thread': False})
        self.stack.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        for module in ('agent_tokens', 'base_garments', 'agent_renders', 'wardrobe', 'wardrobe_sharing', 'access'):
            self.stack.enter_context(patch('webapp.' + module + '.SessionLocal', self.sessions))
        for module in ('mcp_server', 'agent_renders'):
            self.stack.enter_context(patch('webapp.' + module + '.APP_URL', 'http://testserver'))
        with self.sessions() as db:
            db.add_all([User(email='alice@example.test'), User(email='bob@example.test')])
            db.commit()
        self.token = agent_tokens.create('alice@example.test', 'Test MCP')
        self.other = agent_tokens.create('bob@example.test', 'Other MCP')
        app = FastAPI()
        mcp_server.register(app)
        self.client = self.stack.enter_context(TestClient(app))
        self.headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json, text/event-stream',
                        'MCP-Protocol-Version': '2025-11-25'}
        self.request_id = 0

    def tearDown(self):
        self.stack.close()

    def rpc(self, method, params=None, token=None):
        self.request_id += 1
        headers = dict(self.headers)
        if token:
            headers['Authorization'] = 'Bearer ' + token
        response = self.client.post('/mcp/', headers=headers, json={
            'jsonrpc': '2.0', 'id': self.request_id, 'method': method, 'params': params or {}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['result']

    def tool(self, name, arguments=None, token=None, error=False):
        result = self.rpc('tools/call', {'name': name, 'arguments': arguments or {}}, token)
        self.assertEqual(result.get('isError', False), error, result)
        if error:
            return result
        return result.get('structuredContent') or json.loads(result['content'][0]['text'])

    def test_protocol_auth_and_token_lifecycle(self):
        self.assertEqual(self.client.post('/mcp/', json={}).status_code, 401)
        info = self.rpc('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                      'clientInfo': {'name': 'test', 'version': '1'}})
        self.assertEqual(info['serverInfo']['name'], 'SewEasy')
        self.assertEqual(len(self.rpc('tools/list')['tools']), 14)
        self.assertIn('upload-guide', self.rpc('resources/list')['resources'][0]['uri'])
        self.assertIn('centimeter', self.rpc('resources/read', {'uri': 'seweasy://upload-guide'})['contents'][0]['text'])
        self.assertEqual(self.client.post('/mcp/', headers={**self.headers, 'Origin': 'https://evil.test'}, json={}).status_code, 403)
        with self.sessions() as db:
            token = db.query(AgentToken).filter_by(owner_email='alice@example.test').one()
            self.assertNotIn(self.token, token.digest)
            identity = token.id
        agent_tokens.revoke('bob@example.test', identity)
        self.assertEqual(agent_tokens.authenticate(self.token), 'alice@example.test')
        agent_tokens.revoke('alice@example.test', identity)
        self.assertEqual(self.client.post('/mcp/', headers=self.headers, json={}).status_code, 401)

    def test_create_base_garment_outfit_update_copy_and_isolation(self):
        base = self.tool('create_base_garment', {'name': 'Short sleeve', 'template_id': 'standard:Shirt',
                                               'parameters': {'sleeve.length': .22}})
        garment = self.tool('create_garment', {'name': 'Blue tee', 'base_id': base['id'],
                                              'appearance': {'fabric_color': '#334455'}})
        self.assertEqual(garment['params']['sleeve']['length']['v'], .22)
        self.tool('get_base_garment', {'base_id': base['id']}, token=self.other, error=True)
        self.tool('get_item', {'kind': 'garment', 'item_id': garment['id']}, token=self.other, error=True)
        outfit = self.tool('create_outfit', {'name': 'Blue outfit', 'garments': [
            {'garment_id': garment['id'], 'appearance': {'fabric_color': '#ff0000'}}]})
        self.assertEqual(outfit['garments'][0]['appearance']['fabric_color'], '#ff0000')
        self.assertEqual(self.tool('get_item', {'kind': 'garment', 'item_id': garment['id']})['appearance']['fabric_color'], '#334455')
        updated = self.tool('update_garment', {'item_id': garment['id'], 'expected_updated_at': garment['updated_at'],
                                               'name': 'Long tee', 'parameters': {'shirt.length': 2.5}})
        self.assertEqual(updated['id'], garment['id'])
        self.tool('update_garment', {'item_id': garment['id'], 'expected_updated_at': garment['updated_at'], 'name': 'Stale'}, error=True)
        copied = self.tool('save_copy', {'kind': 'garment', 'item_id': garment['id']})
        self.assertEqual(copied['name'], 'Long tee (copy)')
        self.assertNotEqual(copied['id'], garment['id'])

    def test_pattern_upload_roundtrip_and_rejections(self):
        files = [{'name': 'panel.json', 'content': json.dumps(panel_spec())},
                 {'name': 'params.yaml', 'content': 'pattern_fit.width: 1.2'}]
        base = self.tool('upload_base_garment', {'name': 'Uploaded panel', 'files': files})
        saved = self.tool('get_base_garment', {'base_id': base['id'], 'include_files': True})
        self.assertEqual(saved['files'], files)
        garment = self.tool('create_garment', {'name': 'Panel sample', 'base_id': base['id']})
        from gui.gui_pattern import GUIPattern
        pattern = GUIPattern(draft=False)
        try:
            pattern.load_outfit([garment]); pattern.reload_garment()
            self.assertEqual(pattern.sew_pattern.assembly().pattern['panels']['g0__front']['vertices'][1], [48, 0])
            self.assertIn('_custom_pattern', pattern.design_params)
            self.assertTrue(pattern.is_design_sectioned())
            from webapp.garment_catalog import starter_item
            pattern.load_outfit([starter_item('Shirt')]); pattern.reload_garment()
            self.assertNotIn('_custom_pattern', pattern.design_params)
        finally:
            pattern.release()
        for name in ('../escape.json', 'code.py', 'archive.zip'):
            self.tool('upload_base_garment', {'name': 'Rejected', 'files': [{'name': name, 'content': '{}'}]}, error=True)
        bad = panel_spec(); bad['pattern']['stitches'] = [[{'panel': 'missing', 'edge': 0}, {'panel': 'front', 'edge': 0}]]
        self.tool('upload_base_garment', {'name': 'Bad seam', 'files': [{'name': 'bad.json', 'content': json.dumps(bad)}]}, error=True)
        self.assertEqual(len(self.tool('list_base_garments')['base_garments']), 7)

    def test_2d_render_and_thumbnail_ownership_staleness(self):
        garment = self.tool('create_garment', {'name': 'Render tee', 'base_id': 'standard:Shirt'})
        render = self.tool('render_item', {'kind': 'garment', 'item_id': garment['id'], 'view': '2d'})
        self.assertEqual(render['state'], 'ready_2d')
        response = self.client.get(render['pattern_png_url'])
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        result = self.rpc('tools/call', {'name': 'get_render', 'arguments': {'render_id': render['id'], 'view': '2d'}})
        self.assertEqual(result['content'][1]['type'], 'image')
        self.tool('get_render', {'render_id': render['id']}, token=self.other, error=True)
        # Exercise the completion boundary with a fixture scene, without claiming
        # this raster is a rendered garment (real WebGPU rendering is tested in-browser).
        with self.sessions() as db:
            row = db.get(AgentRender, render['id']); row.scene = b'fixture'; row.state = 'awaiting_browser'; db.commit()
        endpoint = f'/agent-render/{render["id"]}/complete'
        self.assertEqual(self.client.post(endpoint.replace('/complete', '/failed'), json={'error': 'WebGPU unavailable'}).status_code, 200)
        failed = self.tool('get_render', {'render_id': render['id']})
        self.assertEqual(failed['state'], 'failed')
        self.assertEqual(failed['error'], 'WebGPU unavailable')
        self.assertEqual(self.client.post(endpoint, json={'image': raster()}).status_code, 200)
        library = Wardrobe('alice@example.test').read()
        self.assertIn('garment:' + garment['id'], library['thumbnails'])
        self.tool('update_garment', {'item_id': garment['id'], 'expected_updated_at': garment['updated_at'],
                                    'appearance': {'fabric_color': '#112233'}})
        self.assertEqual(self.client.post(endpoint, json={'image': raster()}).status_code, 400)
        self.tool('delete_render', {'render_id': render['id']})
        self.assertEqual(self.client.get(render['pattern_png_url']).status_code, 404)


if __name__ == '__main__':
    unittest.main()
