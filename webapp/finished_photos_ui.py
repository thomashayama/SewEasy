"""Real finished-piece photos, separate from simulated mannequin previews."""
from nicegui import run, ui
from webapp import finished_photos


def photo_gallery(photos):
    with ui.element('div').classes('grid grid-cols-2 gap-3 w-full'):
        for photo in photos:
            with ui.column().classes('gap-1 min-w-0'):
                with ui.link(target=photo['url'], new_tab=True).classes('w-full'):
                    ui.image(photo['url']).props('fit=cover loading=lazy').classes('w-full aspect-square rounded-md') \
                        ._props.update({'alt': photo['caption'] or 'Photograph of the physically made garment'})
                if photo['caption']:
                    ui.label(photo['caption']).classes('text-sm break-words')


def photos_dialog(store, kind, item, on_change=None):
    if not store.email:
        ui.notify('Sign in to add photos of your finished piece.', type='info')
        return
    try:
        store.revision(kind, item['id'])
    except ValueError as error:
        ui.notify(str(error), type='warning')
        return
    with ui.context.client, ui.dialog() as dialog, ui.card().classes('w-full max-w-lg gap-3'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            with ui.column().classes('gap-1 min-w-0'):
                ui.label('Made it').classes('se-section-label text-xl')
                ui.label(item['name']).classes('font-medium break-words')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close finished photos"')
        ui.label('Add photos after sewing this piece. They are visible to anyone who can access this design.').classes('text-sm')
        caption = ui.input('Caption (optional)', placeholder='Fabric, fit or details from your make').props('outlined dense maxlength=200').classes('w-full')
        async def upload(event):
            uploader.disable()
            try:
                raw = event.content.read(finished_photos.MAX_BYTES + 1)
                await run.io_bound(finished_photos.add, store, kind, item['id'], raw, caption.value)
                caption.set_value('')
                gallery.refresh()
                if on_change:
                    on_change()
                ui.notify('Finished photo added', type='positive')
            except ValueError as error:
                ui.notify(str(error), type='warning')
            finally:
                uploader.reset()
                uploader.enable()
        uploader = ui.upload(label='Add a finished photo', on_upload=upload, auto_upload=True,
                             max_file_size=finished_photos.MAX_BYTES,
                             on_rejected=lambda: ui.notify('Choose a JPEG, PNG or WebP photo under 8 MB.', type='warning')) \
            .props('accept="image/jpeg,image/png,image/webp" hide-upload-btn').classes('w-full')
        ui.label('Up to 8 photos, 8 MB each. Location metadata is removed.').classes('se-param-label text-xs')

        @ui.refreshable
        def gallery():
            photos = finished_photos.list_photos(store, kind, item['id'])
            if not photos:
                ui.label('Your finished-piece photos will appear here.').classes('se-param-label py-3')
            for photo in photos:
                with ui.row(wrap=False).classes('w-full gap-3 items-center'):
                    ui.image(photo['url']).props('fit=cover').classes('w-24 h-24 rounded-md shrink-0') \
                        ._props.update({'alt': photo['caption'] or 'Finished garment photo'})
                    ui.label(photo['caption'] or 'Finished piece').classes('grow text-sm break-words')
                    def remove(_, identity=photo['id']):
                        try:
                            finished_photos.remove(store, identity)
                            gallery.refresh()
                            if on_change:
                                on_change()
                        except ValueError as error:
                            ui.notify(str(error), type='warning')
                    ui.button(icon='delete_outline', on_click=remove).props('flat round aria-label="Remove finished photo"')
        gallery()
    dialog.on('hide', dialog.delete)
    dialog.open()
