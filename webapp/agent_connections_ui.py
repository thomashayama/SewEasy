"""Create and revoke personal MCP access without exposing tokens in URLs."""
from nicegui import ui
from webapp import agent_tokens
from webapp.config import APP_URL


def connections(email):
    with ui.card().classes('se-stitch-card w-full gap-3'):
        ui.label('Connect Claude or Codex').classes('se-section-label text-lg')
        ui.label('Let your agent create base garments, garments and outfits in your library, '
                 'upload pattern files, and prepare renders.').classes('se-param-label')
        ui.label('Connections can read and edit your wardrobe. They cannot access your measurement '
                 'profiles, change sharing permissions or manage your account. Access expires after 90 days.').classes('text-sm')
        ui.input('MCP endpoint', value=APP_URL + '/mcp/').props('readonly outlined dense').classes('w-full')
        name = ui.input('Connection name', placeholder='My Codex or Claude').props('outlined dense maxlength=80').classes('w-full')

        async def create():
            try:
                token = agent_tokens.create(email, name.value or '')
            except ValueError as error:
                ui.notify(str(error), type='negative')
                return
            name.set_value('')
            rows.refresh()
            with ui.dialog() as dialog, ui.card().classes('w-full max-w-xl gap-3'):
                ui.label('Copy your access token').classes('se-section-label text-lg')
                ui.label('Shown once. Store it in your agent’s environment as SEWEASY_TOKEN.').classes('text-sm')
                ui.input(value=token, password=True, password_toggle_button=True).props('readonly outlined dense').classes('w-full')
                ui.button('Copy token', icon='content_copy', on_click=lambda: ui.clipboard.write(token)).props('outline')
                ui.button('Done', on_click=dialog.close).props('flat')
            dialog.on('hide', lambda: dialog.delete())
            dialog.open()

        ui.button('Create access token', icon='add', on_click=create).props('unelevated')
        with ui.expansion('Codex setup').classes('w-full'):
            ui.label('Set SEWEASY_TOKEN in the environment used to launch Codex, then add this to your Codex config.').classes('text-sm')
            ui.code(f'[mcp_servers.seweasy]\nurl = "{APP_URL}/mcp/"\nbearer_token_env_var = "SEWEASY_TOKEN"\ntool_timeout_sec = 180', language='toml').classes('w-full')
        with ui.expansion('Claude setup').classes('w-full'):
            ui.label('For Claude Code, set SEWEASY_TOKEN, then connect over HTTP:').classes('text-sm')
            ui.code(f'claude mcp add --transport http seweasy {APP_URL}/mcp/ --header "Authorization: Bearer $SEWEASY_TOKEN"', language='bash').classes('w-full')
            ui.label('For Claude Desktop, use the stdio bridge documented in docs/MCP.md in the SewEasy repository.').classes('text-sm')
        ui.link('Connection and upload documentation', 'https://github.com/thomashayama/SewEasy/blob/main/docs/MCP.md', new_tab=True)

    @ui.refreshable
    def rows():
        tokens = agent_tokens.list_tokens(email)
        with ui.card().classes('se-stitch-card w-full'):
            ui.label('Active connections').classes('se-section-label')
            if not tokens:
                ui.label('No agents connected.').classes('se-param-label')
            for token in tokens:
                with ui.row().classes('w-full items-center gap-3'):
                    with ui.column().classes('gap-0 grow'):
                        ui.label(token['name']).classes('font-medium')
                        ui.label(f'{token["prefix"]}… · expires {token["expires_at"][:10]}').classes('se-param-label')
                    def revoke(identity=token['id']):
                        agent_tokens.revoke(email, identity)
                        rows.refresh()
                    ui.button('Revoke', on_click=revoke).props('flat color=negative')
    rows()
