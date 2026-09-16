"""Mobile connection recovery for the NiceGUI 2.x page lifecycle."""
import asyncio
from pathlib import Path
import time

from nicegui import Client, core, ui

RECONNECT_TIMEOUT = 120
INITIAL_CONNECT_TIMEOUT = 60


def prune_unconnected_clients(cls, *, client_age_threshold=60):
    """Keep an established page while its own reconnect deadline is pending.

    NiceGUI 2.24's orphan sweep uses page creation time, which otherwise deletes
    an older page on the next sweep even if reconnect_timeout hasn't elapsed.
    The framework's pending disconnect task still expires and deletes it normally.
    """
    for client in list(cls.instances.values()):
        if (not client.shared and not client.has_socket_connection
                and not client._delete_tasks
                and client.created <= time.time() - client_age_threshold):
            client.delete()


async def wait_for_session_end(client):
    # disconnected() first waits for a socket with a three-second timeout if
    # a drop happens during initial drafting. Wait for actual disposal instead.
    while client.id in client.instances:
        await asyncio.sleep(.5)


def setup(app):
    root = Path(__file__).parent
    app.add_static_file(url_path='/connection.js', local_file=root / 'connection.js')
    app.add_static_file(url_path='/connection.css', local_file=root / 'connection.css')
    ui.add_head_html('<link rel="stylesheet" href="/connection.css?v=2">'
                     '<script type="module" src="/connection.js?v=2"></script>', shared=True)
    Client.prune_instances = classmethod(prune_unconnected_clients)

    def heartbeat():
        # Session retention and detecting a dead connection are separate limits.
        core.sio.eio.ping_interval = 15
        core.sio.eio.ping_timeout = 30
    app.on_startup(heartbeat)
