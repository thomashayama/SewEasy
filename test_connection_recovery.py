"""Page cleanup must respect reconnect grace, including a drop during drafting."""
import asyncio
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from webapp.connection import prune_unconnected_clients, wait_for_session_end


class ConnectionRecoveryTest(unittest.IsolatedAsyncioTestCase):
    def test_orphan_sweep_keeps_disconnected_pages_with_pending_reconnect_deadlines(self):
        def client(**kwargs):
            return SimpleNamespace(**dict(shared=False, has_socket_connection=False,
                created=time.time()-600, _delete_tasks={}, delete=Mock(), **kwargs))
        pending=client(); pending._delete_tasks={'document':object()}
        connected=client(); connected.has_socket_connection=True
        fresh=client(); fresh.created=time.time()
        shared=client(); shared.shared=True
        orphan=client()
        prune_unconnected_clients(SimpleNamespace(instances=dict(enumerate([pending,connected,fresh,shared,orphan]))))
        for item in (pending,connected,fresh,shared):
            item.delete.assert_not_called()
        orphan.delete.assert_called_once()

    async def test_drafting_disconnect_waits_for_disposal_without_a_new_three_second_handshake(self):
        client=SimpleNamespace(id='page',instances={'page':object()},connected=Mock(),has_socket_connection=False)
        task=asyncio.create_task(wait_for_session_end(client))
        await asyncio.sleep(.01)
        self.assertFalse(task.done());client.connected.assert_not_called()
        client.instances.clear()
        await asyncio.wait_for(task,1)
