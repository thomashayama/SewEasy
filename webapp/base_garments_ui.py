"""Human-facing uploads use the same validation and persistence as MCP."""
from nicegui import run, ui
from webapp import base_garments


def base_library(email):
    from webapp.garment_catalog import standard_garments
    pending = {}
    with ui.card().classes('se-stitch-card w-full gap-3'):
        ui.label('Your base garments').classes('se-section-label text-lg')
        ui.label('Upload a pattern definition to reuse its construction in new garments. '
                 'JSON geometry keeps its original sizing; parameter files customize a selected template.').classes('se-param-label')
        name = ui.input('Base garment name').props('outlined dense maxlength=100').classes('w-full')
        template = ui.select({b['id']: b['name'] for b in standard_garments()}, label='Template for parameter-only uploads',
                             clearable=True).props('outlined dense').classes('w-full')
        file_list = ui.label('No files selected.').classes('text-sm')

        def uploaded(event):
            try:
                raw = event.content.read(base_garments.MAX_BYTES + 1)
                if len(raw) > base_garments.MAX_BYTES or len(pending) >= 8:
                    raise ValueError('Use up to eight files totaling less than 2 MB.')
                pending[event.name] = raw.decode('utf-8-sig')
                if sum(len(v.encode()) for v in pending.values()) > base_garments.MAX_BYTES:
                    pending.pop(event.name)
                    raise ValueError('The combined files must be under 2 MB.')
                file_list.set_text(', '.join(pending))
            except (UnicodeDecodeError, ValueError) as error:
                ui.notify(str(error), type='negative')

        upload = ui.upload(on_upload=uploaded, multiple=True, auto_upload=True,
                           max_files=8, max_file_size=base_garments.MAX_BYTES, max_total_size=base_garments.MAX_BYTES,
                           on_rejected=lambda: ui.notify('Choose up to eight JSON/YAML files totaling under 2 MB.', type='warning')) \
            .props('accept=".json,.yaml,.yml" hide-upload-btn').classes('w-full')
        def removed(event):
            for filename in event.args:
                pending.pop(filename, None)
            file_list.set_text(', '.join(pending) or 'No files selected.')
        upload.on('removed', removed, js_handler='files => emit(files.map(file => file.name))')
        def clear():
            pending.clear(); upload.reset(); file_list.set_text('No files selected.')
        ui.button('Clear files', on_click=clear).props('flat size=sm')
        status = ui.label('').classes('text-sm')

        async def save():
            save_button.disable()
            status.set_text('Checking pattern…')
            try:
                result = await run.io_bound(base_garments.create_base, email, name.value or '', template.value, None,
                                           [dict(name=k, content=v) for k, v in pending.items()])
                status.set_text(f'{result["name"]} is ready in New garment.')
                name.set_value(''); clear(); listing.refresh()
            except Exception as error:
                status.set_text(str(error))
            finally:
                save_button.enable()
        save_button = ui.button('Save base garment', icon='add', on_click=save).props('unelevated')
        ui.link('Pattern file format', 'https://github.com/thomashayama/SewEasy/blob/main/docs/MCP-upload.md', new_tab=True)

    @ui.refreshable
    def listing():
        bases = [b for b in base_garments.list_bases(email) if not b.get('standard')]
        with ui.column().classes('w-full gap-2'):
            for base in bases:
                with ui.card().classes('se-stitch-card w-full'):
                    ui.label(base['name']).classes('font-medium')
                    ui.label('Uploaded pattern' if base['params'].get('_custom_pattern') else 'Parametric template').classes('se-param-label')
            if not bases:
                ui.label('No custom bases yet. Standard garments are available from New garment.').classes('se-param-label')
    listing()
