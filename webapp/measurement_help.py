"""How to take a measurement: its diagram, a photo of it being taken, and the steps.

Shared by the account's measurement editor and the studio's Customize
measurements dialog, so both explain a measurement the same way.
"""
from nicegui import ui

from webapp import measurement_guide as guide

CSS = '''
/* Quasar caps dialog cards at 560px; the diagram and photo need more. */
.q-dialog__inner--minimized > .se-measure-help { max-width: min(820px, calc(100vw - 32px)); }
.se-measure-help-body { display: grid; gap: 16px; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); align-items: start; }
@media (max-width: 599px) { .se-measure-help-body { grid-template-columns: minmax(0, 1fr); } }
.se-measure-help figure { margin: 0; display: grid; gap: 4px; width: 100%; }
.se-measure-help .se-measure-diagram { width: 100%; aspect-ratio: 4 / 5; border-radius: 8px; overflow: hidden; background: #f6f3ed; }
.se-measure-help .se-measure-photo { width: 100%; border-radius: 8px; overflow: hidden; }
.se-measure-help figcaption { font-size: 11px; line-height: 1.4; opacity: .75; overflow-wrap: anywhere; }
.se-measure-overview ol { margin: 6px 0 0; padding-left: 22px; columns: 2; column-gap: 20px; font-size: 13px; }
.se-measure-overview li { break-inside: avoid; }
'''


def _style():
    ui.add_css(CSS)


def show_measurement_help(key):
    """Open the help for one measurement key (including the virtual inseam)."""
    _style()
    label = guide.label_for(key)
    entry = guide.GUIDE.get(key, {})
    photo = guide.photo_for(key)
    # At the page root: a field's row is re-drawn with the editor, taking a dialog inside it along.
    with ui.context.client, ui.dialog() as dialog, ui.card().classes('se-measure-help w-full gap-3'):
        with ui.row().classes('w-full items-center justify-between no-wrap'):
            ui.label(label).classes('text-lg font-semibold')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense aria-label="Close"')
        with ui.element('div').classes('se-measure-help-body'):
            ui.image(f'{guide.DIAGRAM_URL}/{key}.svg').props(
                f'fit=contain alt="Where to measure: {label}"').classes('se-measure-diagram')
            with ui.column().classes('gap-3 min-w-0'):
                if photo:
                    with ui.element('figure'):
                        ui.image(photo['url']).props(f'alt="Someone measuring: {label}"').classes('se-measure-photo')
                        with ui.element('figcaption'):
                            ui.link(photo['credit'], photo['link'], new_tab=True).props('rel="noopener noreferrer"')
                ui.label(entry.get('how', '')).classes('text-sm')
                if key == 'inseam':
                    ui.label('Hip to crotch is then worked out from your height, head length, back length and '
                             'waist to hip, so trousers and the mannequin share the same leg length.') \
                        .classes('text-xs opacity-75')
    dialog.on('hide', dialog.delete)
    dialog.open()


def help_button(key):
    """The small ? next to a measurement field."""
    return ui.button(icon='help_outline', on_click=lambda: show_measurement_help(key)) \
        .props(f'flat dense round size=sm color=grey-7 aria-label="How to measure {guide.label_for(key)}"') \
        .tooltip('How to take this measurement')


def measurement_overview():
    """Where each essential measurement is taken, numbered in measuring order."""
    _style()
    with ui.element('div').classes('se-measure-overview w-full'):
        ui.image(guide.OVERVIEW_DIAGRAM).props(
            'fit=contain alt="Front, side and back of the mannequin with each measurement numbered"') \
            .classes('w-full rounded')
        with ui.element('ol'):
            for key, entry in guide.GUIDE.items():
                if entry['essential']:
                    with ui.element('li'):
                        ui.button(entry['label'], on_click=lambda _, k=key: show_measurement_help(k)) \
                            .props('flat dense no-caps padding="0 4px"').classes('text-sm')
