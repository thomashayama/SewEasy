"""Small fabric workbench for exercising the U3M storage/import/export path."""
from pathlib import Path
import re

from nicegui import run, ui
from sqlalchemy.exc import SQLAlchemyError

from webapp import fabric_favorites, fabrics
from webapp import fabric_formats as formats
from webapp.fabric_catalog import evidence_label, metadata, standard_fabrics
from webapp.garment_materials import SUPPORT

# What a garment drape does with a property; the swatch uses all of them.
DRAPE_SCOPE = {'piece': 'drapes each piece', 'garment': 'drapes the whole garment', 'stored': 'swatch tests only'}


async def fabric_library(email, choose=None):
    """The account's fabric library. With `choose`, the same list becomes the studio's picker."""
    ui.add_css(Path(__file__).with_name('fabrics.css').read_text(encoding='utf-8'))
    async def edit(identity):
        record = await run.io_bound(fabrics.get_fabric, email, identity)
        content = record['content']
        standard = record['standard']
        inputs, initial, restored = {}, {}, {}
        # An edit or a cleared field can hide what the original file measured.
        imported = (await run.io_bound(fabrics.imported_properties, email, identity)
                    if record.get('has_source') else {})
        with ui.context.client, ui.dialog().props('persistent') as dialog, ui.card().classes('se-stitch-card w-full max-w-xl gap-4'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label('Fabric properties').classes('se-section-label text-lg')
                ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close fabric editor"')
            name = ui.input('Fabric name', value=record['name']).props('outlined dense maxlength=120').classes('w-full')
            description = ui.textarea('Notes', value=content['description']).props('outlined dense rows=2 maxlength=4000').classes('w-full')
            if standard:
                name.props('readonly')
                description.props('readonly')
                ui.label('Standard fabric · Save a copy to make it your own.').classes('se-param-label text-sm')
            catalog = metadata(content.get('catalog'))
            if catalog:
                ui.label(f'{catalog["composition"]} · {catalog["construction"]}').classes('text-sm')
                with ui.expansion('Sources and assumptions', icon='info_outline').classes('w-full'):
                    ui.label(catalog['notes']).classes('text-sm mb-3')
                    for reference in catalog['references']:
                        ui.link(reference['title'], reference['url'], new_tab=True).classes('text-sm')
                        ui.label(reference['authors']).classes('se-param-label text-xs')
                        ui.link(reference['license'], reference['license_url'], new_tab=True).classes('text-xs mb-3')
                    if not catalog['references']:
                        ui.label('SewEasy estimates · No published measurements used.').classes('se-param-label text-sm')
            for warning in content.get('physics_normalization', {}).get('warnings', []):
                ui.label(warning['message']).classes('se-param-label text-sm').props('role=note')

            def field(key, label):
                prop = content['properties'][key]
                initial[key] = '' if prop['value'] is None else f'{prop["value"]:.8g}'
                with ui.column().classes('gap-1 min-w-0'):
                    inputs[key] = ui.input(label, value=initial[key], placeholder='Unknown',
                                           on_change=lambda: refresh()).props(
                        'outlined dense clearable inputmode=decimal').classes('w-full')
                    if standard:
                        inputs[key].props('readonly').props(remove='clearable')
                    origin = {'unknown': 'Not supplied', 'user': 'Your value', 'reported': 'Reported value',
                              'measured': 'Measured', 'estimated': 'Estimate'}[prop['origin']]
                    scope, effect = SUPPORT[key]
                    with ui.label(f'{origin} · {DRAPE_SCOPE[scope]}').classes('se-param-label text-xs'):
                        ui.tooltip(' '.join(filter(None, [prop.get('source'), effect]))).classes('max-w-sm')
                    original = imported.get(key) or {}
                    if not standard and original.get('value') is not None and original['value'] != prop['value']:
                        text = f'{original["value"]:.8g}'

                        def restore(key=key, text=text):
                            restored[key] = text
                            inputs[key].set_value(text)
                        # The file's own measurement survives an override or a cleared field.
                        with ui.row().classes('items-center gap-1'):
                            ui.label(f'Imported: {text}').classes('se-param-label text-xs')
                            ui.button('Restore', on_click=restore).props(
                                f'flat dense no-caps size=sm aria-label="Restore imported {label}"')

            with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-3'):
                field('weight', 'Weight (g/m²)')
                field('thickness', 'Thickness (mm)')
                field('friction', 'Friction coefficient')
                initial_color = (content.get('appearance') or {}).get('display_color', '')
                with ui.column().classes('gap-1 min-w-0 col-span-2 sm:col-span-1'):   # a phone clips the hex
                    color = ui.color_input('Display color', value=initial_color, on_change=lambda: refresh()).props(
                        'outlined dense clearable').classes('w-full')
                    if standard:
                        color.props('readonly').props(remove='clearable')
                    ui.label('Pieces cut from this fabric start this color.').classes('se-param-label text-xs')
            with ui.expansion('Additional physical properties').classes('w-full'):
                ui.label('Swatch tests use every value here. A garment drape uses weight and bending per piece, '
                         'and damping, friction and thickness for the whole garment; stretch and shear are '
                         'swatch-only. Leave unknown values blank.').classes('se-param-label mb-3')
                with ui.grid(columns=2).classes('w-full gap-3'):
                    for key, label in (
                        ('stretch_warp', 'Warp stretch stiffness (N/m)'), ('stretch_weft', 'Weft stretch stiffness (N/m)'),
                        ('bend_warp', 'Warp bending rigidity (N·m)'), ('bend_weft', 'Weft bending rigidity (N·m)'),
                        ('shear', 'Shear stiffness (N/m)'), ('damping', 'Damping rate (1/s)'),
                    ):
                        field(key, label)
            if content.get('source'):
                source = content['source']
                ui.label(f'Source: {source.get("filename", source["format"])}').classes('se-param-label break-all')
                if source.get('has_raw_measurements'):
                    ui.label('Original test curves are preserved. Editing these values does not change the source file.').classes('se-param-label')
            textures = content.get('textures') or []
            if textures:
                warnings = [t for t in textures if t['warning']]
                with ui.expansion(f'{len(textures)} texture references', value=bool(warnings)).classes('w-full'):
                    for texture in textures:
                        size = ' · '.join(filter(None, [
                            '×'.join(str(p) for p in texture['pixels']) + ' px',
                            '×'.join(f'{mm:.4g}' for mm in texture['size_mm']) + ' mm'
                            if all(isinstance(mm, (int, float)) for mm in texture['size_mm']) else '']))
                        ui.label(f'{texture["role"]} · {texture["format"]} · {size}').classes('text-sm break-all')
                        # The stored message names its role; the heading above already does.
                        ui.label(texture['warning'].replace(texture['role'], 'This file', 1)
                                 if texture['warning'] else texture['path']).classes(
                            'se-param-label text-xs mb-2' + (' text-warning' if texture['warning'] else ''))
                    ui.label('Texture files are stored exactly as uploaded. The swatch preview does not '
                             'render them yet, so these sizes are not applied to a garment.').classes('se-param-label text-xs')
                if warnings:
                    ui.label('One texture reference declares a size that does not match its image.'
                             if len(warnings) == 1 else
                             f'{len(warnings)} texture references declare sizes that do not match their images.'
                             ).classes('se-param-label text-sm').props('role=note')
            if not standard:
                ui.label('Garments already cut from this fabric keep their saved copy. Choose the fabric '
                         'again in the sewing pattern to apply a change.').classes('se-param-label text-sm')
            error = ui.label('').classes('text-negative text-sm').props('role=alert')

            def dirty():
                return (name.value != record['name'] or (description.value or '') != content['description']
                        or (color.value or '') != initial_color
                        or any((item.value or '') != initial[key] for key, item in inputs.items()))

            def refresh():
                if standard or 'save' not in controls:
                    return
                unsaved = dirty()
                controls['state'].set_text('Unsaved changes' if unsaved else 'All changes saved')
                controls['cancel'].set_text('Discard changes' if unsaved else 'Close')
                controls['save'].set_enabled(unsaved)

            async def save():
                controls['save'].disable()
                try:
                    # A restored field returns with its provenance; an edit after restoring is an edit.
                    back = {key for key, text in restored.items() if (inputs[key].value or '') == text}
                    changed = {key: item.value for key, item in inputs.items()
                               if (item.value or '') != initial[key] and key not in back}
                    await run.io_bound(fabrics.update_fabric, email, identity, record['edit_token'],
                                       name=name.value, description=description.value or '', values=changed,
                                       restore=back, display_color=color.value or '')
                    dialog.close()
                    listing.refresh()
                    ui.notify('Fabric saved', type='positive')
                except ValueError as exc:
                    error.set_text(str(exc))
                    controls['save'].enable()
            controls = {}
            with ui.row().classes('w-full items-center justify-end gap-2'):
                if not standard:
                    controls['state'] = ui.label('All changes saved').classes('se-param-label text-sm mr-auto').props('role=status')
                controls['cancel'] = ui.button('Close', on_click=dialog.close).props('flat no-caps')
                if standard:
                    async def make_copy():
                        dialog.close()
                        await copy(identity)
                    ui.button('Save a copy', icon='content_copy', on_click=make_copy).props('unelevated no-caps')
                else:
                    controls['save'] = ui.button('Save', on_click=save).props('unelevated no-caps')
                    controls['save'].disable()
            name.on_value_change(lambda: refresh())
            description.on_value_change(lambda: refresh())
        dialog.open()
        await dialog
        dialog.delete()

    async def import_dialog():
        with ui.context.client, ui.dialog().props('persistent') as dialog, ui.card().classes('se-stitch-card w-full max-w-lg gap-3'):
            ui.label('Import a fabric').classes('se-section-label text-lg')
            ui.label('U3M 1.1 · up to 20 MB. Include companion textures and measurement files in a U3MA or ZIP '
                     'package. U3M 1.0 files must be re-exported as 1.1.').classes('se-param-label')
            status = ui.label('').classes('text-negative text-sm').props('role=alert')

            async def import_bytes(raw, filename):
                upload.disable(); sample.disable()
                status.set_text('Reading fabric…')
                try:
                    record = await run.io_bound(fabrics.import_fabric, email, raw, filename)
                    dialog.submit(record)
                except ValueError as exc:
                    status.set_text(str(exc))
                finally:
                    upload.enable(); sample.enable()

            async def uploaded(event):
                await import_bytes(event.content.read(formats.MAX_UPLOAD + 1), event.name)

            upload = ui.upload(on_upload=uploaded, auto_upload=True, max_file_size=formats.MAX_UPLOAD,
                               on_rejected=lambda: status.set_text('Choose a U3M/U3MA/ZIP file under 20 MB.')) \
                .props('accept=".u3m,.u3ma,.zip" hide-upload-btn label="Choose fabric file"').classes('w-full')

            async def use_sample():
                await import_bytes(await run.io_bound(formats.sample_package), 'SU-1098 Cupro.u3ma')

            sample = ui.button('Try the measured cupro sample', icon='science', on_click=use_sample).props('flat no-caps')
            ui.label('Published Browzwear measurements from the U3M reference repository, packaged by SewEasy. No appearance textures.').classes('se-param-label text-xs')
            ui.button('Cancel', on_click=dialog.close).props('flat no-caps').classes('self-end')
        dialog.open()
        result = await dialog
        dialog.delete()
        if result:
            listing.refresh()
            await edit(result['id'])

    async def new_fabric():
        with ui.context.client, ui.dialog() as dialog, ui.card().classes('se-stitch-card w-full max-w-sm'):
            ui.label('New fabric').classes('se-section-label')
            name = ui.input('Fabric name').props('outlined dense maxlength=120').classes('w-full')
            error = ui.label('').classes('text-negative text-sm')

            async def create():
                button.disable()
                try:
                    record = await run.io_bound(fabrics.create_fabric, email, name.value)
                    dialog.submit(record)
                except ValueError as exc:
                    error.set_text(str(exc))
                finally:
                    button.enable()
            with ui.row().classes('justify-end w-full'):
                ui.button('Cancel', on_click=dialog.close).props('flat no-caps')
                button = ui.button('Create', on_click=create).props('unelevated no-caps')
        dialog.open()
        result = await dialog
        dialog.delete()
        if result:
            listing.refresh()
            await edit(result['id'])

    async def copy(identity):
        try:
            record = await run.io_bound(fabrics.copy_fabric, email, identity)
            listing.refresh()
            await edit(record['id'])
        except ValueError as exc:
            ui.notify(str(exc), type='negative')

    async def compare(identity):
        from webapp.fabric_preview import comparison_dialog
        try:
            await comparison_dialog(email, identity)
        except ValueError as exc:
            ui.notify(str(exc), type='negative')

    async def download(record, original=False):
        try:
            if original:
                filename, raw = await run.io_bound(fabrics.original_file, email, record['id'])
            else:
                raw = await run.io_bound(fabrics.export_fabric, email, record['id'])
                filename = re.sub(r'[^\w .()-]', '_', record['name']) + '.u3ma'
            ui.download(raw, filename=filename, media_type='application/octet-stream')
        except ValueError as exc:
            ui.notify(str(exc), type='negative')

    hearts = await run.io_bound(fabric_favorites.keys, email)
    pending_hearts = set()

    def heart_button(record):
        """The wardrobe's heart: optimistic, reverted if the save fails."""
        identity = record['id']

        def update():
            selected = identity in hearts
            button.props(f'icon={"favorite" if selected else "favorite_border"} aria-pressed={str(selected).lower()}')
            button.classes(add='is-favorite' if selected else '', remove='' if selected else 'is-favorite')
            button._props['aria-label'] = (f'{"Remove" if selected else "Add"} {record["name"]} '
                                           f'{"from" if selected else "to"} favorites')
            button.update()

        async def toggle():
            if identity in pending_hearts:
                return
            if not email:
                ui.notify('Sign in to save favorites.', type='info')
                return
            selected = identity in hearts
            pending_hearts.add(identity)
            (hearts.discard if selected else hearts.add)(identity)
            update()
            try:
                await run.io_bound(fabric_favorites.set_favorite, email, identity, not selected)
            except (ValueError, SQLAlchemyError) as error:
                (hearts.add if selected else hearts.discard)(identity)
                ui.notify(str(error) if isinstance(error, ValueError) else
                          'Could not save favorite. Please try again.', type='warning')
            finally:
                pending_hearts.discard(identity)
                update()
                if collection.value == 'favorites':
                    listing.refresh()

        button = ui.button(on_click=toggle, color=None).props('flat round dense :ripple=false').classes('se-fabric-heart')
        update()

    with ui.row().classes('w-full items-center justify-between gap-3'):
        with ui.column().classes('gap-1'):
            ui.label('Choose a fabric' if choose else 'Fabrics').classes('se-section-label text-2xl')
            ui.label('It is applied to the selected pieces.' if choose else
                     'Your materials, measurements, and original files.').classes('se-param-label')
        if not choose:
            with ui.row().classes('gap-2'):
                ui.button('New fabric', on_click=new_fabric).props('flat no-caps')
                ui.button('Import U3M', icon='file_upload', on_click=import_dialog).props('unelevated no-caps')
    if not choose:
        ui.label('Try a swatch, inspect its sources, or save a copy to edit. '
                 'Cut pieces from a fabric under Fabric type in the sewing pattern.').classes('se-param-label')
    with ui.row().classes('w-full items-center justify-between gap-3'):
        # A guest studio has no account library or hearts to show.
        views = {'favorites': 'Favorites', 'saved': 'My fabrics', 'common': 'Common fabrics'} if email else {
            'common': 'Common fabrics'}
        collection = ui.toggle(views, value='favorites' if choose and hearts else 'common',
                               on_change=lambda: listing.refresh()).props('no-caps unelevated')
        with ui.row().classes('items-center gap-2 w-full sm:w-auto'):
            # A label, not an aria-label prop: Quasar puts that on a wrapper, not the combobox.
            weight = ui.select({'': 'Any weight', **fabrics.WEIGHT_CLASSES}, value='', label='Weight',
                               on_change=lambda: listing.refresh()).props(
                'outlined dense options-dense').classes('w-full sm:w-52')
            search = ui.input('Search fabrics', placeholder='Name, fiber, or weave',
                              on_change=lambda: listing.refresh()).props('outlined dense clearable debounce=250').classes('w-full sm:w-64')

    listing_generation = 0

    @ui.refreshable
    async def listing():
        nonlocal listing_generation
        listing_generation += 1
        generation = listing_generation
        query = search.value or ''
        loading = ui.row().classes('items-center gap-2 py-4')
        with loading:
            ui.spinner(size='sm')
            ui.label('Loading fabrics…').classes('se-param-label').props('role=status')
        try:
            if collection.value == 'common':
                records = standard_fabrics()
            elif collection.value == 'favorites':
                records = await run.io_bound(fabric_favorites.favorites, email)
            else:
                records = await run.io_bound(fabrics.list_fabrics, email)
        except (ValueError, SQLAlchemyError):
            records = None
        # A filter/tab change can finish before an older database read. Only
        # the latest render may populate the refreshable container.
        if generation != listing_generation:
            return
        loading.delete()
        if records is None:
            ui.label('Your fabrics could not be loaded. Check your connection and try again.').classes(
                'se-param-label py-4').props('role=alert')
            return
        total = len(records)
        records = [record for record in records if fabrics.matches(record, query, weight.value)]
        if not records:
            empty = {'favorites': 'Tap a heart to keep a fabric here. Nothing is copied.',
                     'saved': 'Save a copy from Common fabrics, import a material, or create your own.',
                     'common': 'No common fabrics are available.'}[collection.value]
            ui.label('No fabrics match your search or weight.' if total else empty).classes('se-param-label py-4')
        for record in records:
            values = record['content']['properties']
            summary = []
            for key, unit in (('weight', 'g/m²'), ('thickness', 'mm')):
                if values[key]['value'] is not None:
                    summary.append(f'{values[key]["value"]:.4g} {unit}')
            with ui.card().classes('se-stitch-card w-full p-3 gap-1'):
                with ui.row().classes('w-full items-center justify-between gap-3'):
                    with ui.column().classes('gap-0 min-w-0'):
                        with ui.row(wrap=False).classes('items-center gap-2'):
                            shade = (record['content'].get('appearance') or {}).get('display_color')
                            if shade:
                                ui.element('span').classes('se-fabric-chip').style(f'background:{shade}').props(
                                    f'role=img aria-label="Display color {shade}"')
                            if choose and not email:
                                ui.label(record['name']).classes('font-medium')     # Properties need an account.
                            else:
                                ui.button(record['name'], on_click=lambda _, i=record['id']: edit(i)).props('flat no-caps align=left').classes('font-medium' + ('' if shade else ' -ml-3'))
                        catalog = record['content'].get('catalog')
                        if catalog:
                            ui.label(f'{catalog["composition"]} · {catalog["construction"]}').classes('se-param-label text-sm')
                        ui.label(' · '.join(summary) or 'Physical properties not supplied').classes('se-param-label')
                        ui.label(evidence_label(record['content'])).classes('se-param-label text-xs mt-1')
                    with ui.row(wrap=False).classes('se-fabric-actions items-center gap-1'):
                        heart_button(record)
                        if choose:
                            # The studio keeps its selection; only the fabric comes back.
                            ui.button('Use fabric', on_click=lambda _, i=record['id']: choose(i)).props(
                                f'unelevated no-caps aria-label="Use {record["name"]}"')
                            continue
                        if values['weight']['value'] is not None:
                            ui.button('Test swatch', icon='science', on_click=lambda _, i=record['id']: compare(i)).props('flat no-caps')
                        if record['standard']:
                            ui.button('Save a copy', icon='content_copy', on_click=lambda _, i=record['id']: copy(i)).props('flat no-caps')
                        with ui.button(icon='more_horiz').props('flat round aria-label="Fabric actions"'):
                            with ui.menu():
                                ui.menu_item('View properties' if record['standard'] else 'Edit', on_click=lambda _, i=record['id']: edit(i))
                                if not record['standard']:
                                    ui.menu_item('Save a copy', on_click=lambda _, i=record['id']: copy(i))
                                ui.menu_item('Export U3MA', on_click=lambda _, r=record: download(r))
                                if record['has_source']:
                                    ui.menu_item('Download original', on_click=lambda _, r=record: download(r, True))
    await listing()
