# Mobile connection recovery

Every NiceGUI page keeps its server session for 120 seconds after a dropped
socket. Initial studio connections have 60 seconds to load their scripts and
connect. Heartbeats run every 15 seconds with a 30-second response timeout,
independent of the longer session retention period.

The connection adapter leaves the document, pattern, and browser-rendered
garment in place. Drops shorter than three seconds recover silently. Longer
interruptions show a small, nonmodal status notice with a Retry action. Network
return and returning to a backgrounded tab trigger another connection attempt.
The notice disappears after the server accepts the page handshake.

Server-backed controls pause while disconnected, preventing clicks, saves, and
edits from accumulating in the socket's offline buffer. Scrolling and local 3D
camera, pause, reset, and recenter controls remain available. This is connection
recovery, not a full offline editor. Drafts already applied by the server keep
using the existing automatic `pending_design` snapshot.

If the server restarted or the retained session expired, the page remains
visible and offers Reload. It does not loop through automatic reloads on a
weak connection. A reload restores the studio's last recovered draft; edits
that never reached the server cannot be guaranteed.

## NiceGUI 2.x integration

`webapp/connection.js` replaces only the socket's connect, disconnect,
connect_error, and try_reconnect handlers. NiceGUI still handles UI updates,
message replay, events, authentication, and normal navigation. An initial
handshake already sent by NiceGUI is adopted rather than sent twice.

`webapp/connection.py` also adapts the 2.24 orphan sweep. Its original page-age
check can delete old disconnected pages during an active reconnect deadline.
Pages with a pending disconnect task now use that task's deadline; abandoned
pages that never connected still get pruned. Review these two adapters before
upgrading NiceGUI beyond the current `<3` constraint.

Validation:

```
python -m unittest test_connection_recovery test_home_page test_wardrobe -q
node --test benchmarks/test_connection_recovery.mjs
```

Browser verification uses a local interruptible reverse proxy, never a
production outage. Check long and short drops, editing guards, identical
pattern/scene URLs after recovery, and explicit reload after a server restart.
