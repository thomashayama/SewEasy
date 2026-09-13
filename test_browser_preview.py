"""Regression checks for lazy, latest-design-only CPU preparation.

Run with the GUI environment: python -m unittest test_browser_preview -v
The real WebGPU path is exercised separately in the browser.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gui.callbacks import GUIState


class Preview:
    def __init__(self):
        self.props = {}
        self.loaded = []

    def configure(self, **props):
        self.props.update(props)
        if props.get('scene_url'):
            self.loaded.append(props['scene_url'])


class BrowserPreviewTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.state = GUIState.__new__(GUIState)
        self.state._released = False
        self.state._view_3d_active = True
        self.state._draft_pending = 0
        self.state._draft_failed = False
        self.state._preparing_3d = False
        self.state._prepared_revision = -1
        self.state._preview_revision = 0
        self.state._async_executor = ThreadPoolExecutor(1)
        self.state.local_path_3d = Path(self.directory.name)
        self.state.ui_browser_drape = Preview()
        self.state.pattern_state = SimpleNamespace(svg_filename='pattern.svg',
            id='TEST', fabric_color='#b7cde5', panel_colors={})

    def tearDown(self):
        self.state._async_executor.shutdown(wait=True)
        self.directory.cleanup()

    @staticmethod
    def prepare(_pattern, target):
        target.write_text('{}')

    async def test_no_work_when_hidden_drafting_failed_or_disconnected(self):
        for key, value in [('_view_3d_active', False), ('_draft_pending', 1),
                           ('_draft_failed', True), ('_released', True)]:
            old = getattr(self.state, key)
            setattr(self.state, key, value)
            with patch('gui.callbacks.prepare_scene') as prepare:
                await self.state.update_3d_scene()
                prepare.assert_not_called()
            setattr(self.state, key, old)

    async def test_reopen_reuses_prepared_scene(self):
        with patch('gui.callbacks.prepare_scene', side_effect=self.prepare) as prepare:
            await self.state.update_3d_scene()
            await self.state.update_3d_scene()
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(self.state.ui_browser_drape.loaded, ['/geo/TEST/scene-0.json'])

    async def test_edit_during_preparation_never_publishes_stale_design(self):
        entered, proceed = Event(), Event()
        def slow_prepare(pattern, target):
            if target.name == 'scene-0.json':
                entered.set()
                if not proceed.wait(5):
                    raise TimeoutError('Test did not release the CPU job')
            self.prepare(pattern, target)
        with patch('gui.callbacks.prepare_scene', side_effect=slow_prepare):
            task = asyncio.create_task(self.state.update_3d_scene())
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            self.state._preview_revision = 1
            await self.state.update_3d_scene()
            proceed.set()
            await task
        self.assertEqual(self.state.ui_browser_drape.loaded, ['/geo/TEST/scene-1.json'])
        self.assertFalse((self.state.local_path_3d / 'scene-0.json').exists())

    async def test_empty_design_clears_previous_scene(self):
        self.state.pattern_state.svg_filename = ''
        with patch('gui.callbacks.prepare_scene') as prepare:
            await self.state.update_3d_scene()
            prepare.assert_not_called()
        self.assertEqual(self.state.ui_browser_drape.props['scene_url'], '')
        self.assertFalse(self.state.ui_browser_drape.props['preparing'])

    async def test_mesh_failure_can_retry(self):
        with patch('gui.callbacks.prepare_scene', side_effect=ValueError('invalid panel')), \
                patch('gui.callbacks.traceback.print_exc'):
            await self.state.update_3d_scene()
        self.assertIn('Could not prepare', self.state.ui_browser_drape.props['error'])
        self.assertFalse(self.state._preparing_3d)
        with patch('gui.callbacks.prepare_scene', side_effect=self.prepare):
            await self.state.update_3d_scene()
        self.assertEqual(self.state.ui_browser_drape.props['error'], '')
        self.assertEqual(self.state._prepared_revision, 0)


if __name__ == '__main__':
    unittest.main()
