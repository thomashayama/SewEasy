# SewEasy MCP

Connect an agent to `https://seweasy.thomashayama.com/mcp/` using Streamable HTTP.
The service runs with the web app; it uses the official Python MCP SDK. The
container and development server now require Python 3.10+ (Docker uses 3.11).

## Connect your account

Sign in to SewEasy, open **Account → Agent connections**, name the connection,
and create an access token. Copy it once and store it as `SEWEASY_TOKEN` in the
environment used to launch your agent. Tokens expire after 90 days and can be
revoked on the same page. Only a token hash is stored in the database.

Access is limited to that account's base garments, wardrobe, accessible shared
items, and renders. Tools cannot change account settings, read body measurement
profiles, or change sharing permissions. Nothing is made public by creating it.
Do not put actual tokens in source control, prompts or screenshots.

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.seweasy]
url = "https://seweasy.thomashayama.com/mcp/"
bearer_token_env_var = "SEWEASY_TOKEN"
tool_timeout_sec = 180
```

Restart the client after setting the environment variable. The endpoint requires
Bearer authentication; it does not provide an OAuth login flow. See the
[official Codex MCP configuration](https://developers.openai.com/codex/mcp/).

### Claude Code

With `SEWEASY_TOKEN` set, in Bash:

```sh
claude mcp add --transport http seweasy https://seweasy.thomashayama.com/mcp/ --header "Authorization: Bearer $SEWEASY_TOKEN"
```

In PowerShell use `$env:SEWEASY_TOKEN` in that header instead. This command stores
the header in Claude's local configuration; keep that configuration private.
See the [official Claude MCP documentation](https://code.claude.com/docs/en/mcp).

### Claude Desktop / stdio clients

Clone this repository and install `uv`. Add the following server to your client's
MCP configuration, replacing the absolute script path and token locally:

```json
{
  "mcpServers": {
    "seweasy": {
      "command": "uv",
      "args": ["run", "/absolute/path/to/SewEasy/integrations/seweasy_mcp.py"],
      "env": {"SEWEASY_TOKEN": "YOUR_PRIVATE_TOKEN"}
    }
  }
}
```

The lightweight bridge installs its own MCP dependencies; users do not need the
sewing framework or a backend GPU. It forwards the same tools, resources,
ownership checks and image results. `SEWEASY_URL` optionally selects another
installation (HTTPS required, except localhost). It never launches a browser or
executes uploaded garment programs.

## Tools and workflow

1. `list_base_garments` and `get_base_garment`: discover templates and settings.
2. `create_base_garment`: save a reusable variant of a standard/custom base.
   `upload_base_garment`: upload JSON/YAML files defining new geometry/defaults.
3. `create_garment`: create a named instance with its own parameters/appearance.
4. `create_outfit`: assemble 1–8 saved garments, optionally adjusting each inside
   the outfit without altering the source garments.
5. `render_item`: generate real SVG/PNG artifacts and optionally a 3D viewer.
6. Open the viewer in a WebGPU browser. It simulates cloth and saves a 384×448
   WebP thumbnail to the stable garment/outfit ID. `get_render` returns status
   and an MCP image once available. `view="2d"` returns the PNG immediately.

`list_library`, `get_item`, `update_garment`, `update_outfit`, and `save_copy`
support editing. Updates require the last `updated_at` timestamp, so a stale
agent cannot silently overwrite a browser edit. Copies get a new ID and default
to “Name (copy)”. Saving an existing item retains its ID. For another person's
item, `save_copy(shared=true, item_id="<share ID>")` enforces link/invitation
access again and creates a private copy.

The backend only drafts and meshes on CPU. **3D completion requires opening the
viewer in a WebGPU browser** (the user or an agent with browser access). A pending
render is explicitly reported as `awaiting_browser`; a tool never substitutes
a placeholder for a finished render. No Modal job or server GPU is needed.

Render URLs are unguessable, read/write capabilities for that single preview,
valid for 24 hours. Keep them private. Up to 20 active jobs are retained per
account; `delete_render` frees one and invalidates its URLs without deleting the
item or attached thumbnail. Expired jobs are removed when another job is made.
Changes to the saved design invalidate its thumbnail; stale render completions
cannot overwrite a newer design's thumbnail.

## Uploads

Read [the upload format](MCP-upload.md), also available as the MCP resource
`seweasy://upload-guide`. Upload original UTF-8 file text through the tool.
The same upload flow is available in **Account → Base garments**. Saved bases
appear in New garment and the outfit's Add garment chooser.
Limits and formats are validated before persistence. Pattern geometry remains
at its authored dimensions, with explicit width/height scaling; it is not
automatically graded to arbitrary body measurements. Arbitrary Python program
execution requires a separate isolated worker and is not enabled here.

## Local verification

Install the repository dependencies, then run:

```sh
python -m unittest test_mcp_server test_design_number
python gui.py
```

Set `APP_URL` to the exact local origin (e.g. `http://127.0.0.1:8081`) before
launching a development server. MCP validates Host and Origin against that
value. Anonymous, expired and revoked credentials return HTTP 401. The normal
web sign-in creates the account used by tokens; browser cookies alone never
authenticate the MCP endpoint.
