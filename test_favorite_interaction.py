"""Favorite clicks update in place while persistence is still pending."""
import asyncio
import inspect
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from nicegui import Client
from nicegui.page import page
from starlette.requests import Request

from webapp.home_page import home_page


class FavoriteInteractionTest(unittest.IsolatedAsyncioTestCase):
    async def test_optimistic_toggle_rollback_and_no_library_reload(self):
        store = Mock(email='alice@example.test')
        store.read.return_value = {'garments': [], 'outfits': [
            {'id': 'outfit-1', 'revision_id': 'outfit-1', 'name': 'Weekend', 'garments': []}], 'thumbnails': {}}
        favorites = Mock()
        favorites.keys.return_value = set()
        sharing = Mock()
        sharing.shared_with_me.return_value = []
        sharing.owner_access.return_value = {}
        gate = asyncio.Event()

        async def save(*args):
            await gate.wait()

        with ExitStack() as stack:
            for name, value in {
                'app': SimpleNamespace(storage=SimpleNamespace(user={})),
                'Wardrobe': Mock(return_value=store),
                'Favorites': Mock(return_value=favorites),
                'WardrobeSharing': Mock(return_value=sharing),
                'ThumbnailQueue': Mock(),
                'Friends': Mock(return_value=Mock(list=Mock(return_value={'incoming': []}))),
            }.items():
                stack.enter_context(patch('webapp.home_page.' + name, value))
            stack.enter_context(patch('webapp.home_page.auth.current_user', return_value={'email': store.email}))
            stack.enter_context(patch('webapp.base_garments.list_bases', return_value=[]))
            persist = stack.enter_context(patch('webapp.home_page.run.io_bound', new=AsyncMock(side_effect=save)))
            notify = stack.enter_context(patch('webapp.home_page.ui.notify'))
            client = stack.enter_context(Client(page('/favorite-test'), request=None))
            home_page(Request({'type': 'http', 'query_string': b'tab=outfits', 'headers': []}))
            button = next(e for e in client.elements.values() if 'se-favorite' in e._classes)
            handler = next(e.handler for e in button._event_listeners.values() if e.type == 'click')
            handler = inspect.getclosurevars(handler).nonlocals['callback']
            reads = store.read.call_count
            element_ids = set(client.elements)

            task = asyncio.create_task(handler())
            await asyncio.sleep(0)
            self.assertEqual(button._props['icon'], 'favorite')
            self.assertEqual(button._props['aria-pressed'], 'true')
            self.assertFalse(task.done())
            await handler()  # A second click cannot race the pending write.
            self.assertEqual(persist.await_count, 1)
            gate.set()
            await task
            persist.assert_awaited_once_with(favorites.set, 'outfit', 'outfit-1', True)
            self.assertEqual(store.read.call_count, reads)
            self.assertEqual(set(client.elements), element_ids)
            favorites.list.assert_not_called()

            persist.side_effect = ValueError('Could not save')
            await handler()
            self.assertEqual(button._props['icon'], 'favorite')
            self.assertEqual(button._props['aria-pressed'], 'true')
            notify.assert_called_once_with('Could not save', type='warning')

            persist.side_effect = save
            await handler()
            self.assertEqual(button._props['icon'], 'favorite_border')
            self.assertEqual(button._props['aria-pressed'], 'false')
            self.assertEqual(store.read.call_count, reads)


if __name__ == '__main__':
    unittest.main()
