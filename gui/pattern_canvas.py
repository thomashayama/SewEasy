"""Browser-local pattern picking; only selection changes cross the connection."""
from pathlib import Path
from base64 import b64encode

from nicegui import ui
from nicegui.elements.mixins.source_element import SourceElement
from nicegui.element import Element
from .fabric_library import FABRIC_PRESETS


class PatternCanvas(SourceElement, component='pattern_canvas.js'):
    def __init__(self):
        super().__init__(source='')
        ui.add_css(Path(__file__).with_name('fabric_editor.css').read_text())
        self._props.update(pieces=[], selected=[], viewbox='0 0 1 1')

    def set_source(self, source):
        # The small SVG travels with its picking paths in the same UI update.
        # Avoid a second HTTP request (and a new static-file route every edit).
        if source:
            source = 'data:image/svg+xml;base64,' + b64encode(Path(source).read_bytes()).decode('ascii')
        super().set_source(source)

    def configure(self, **props):
        self._props.update(props)
        self.update()


class FabricPanel(Element, component='fabric_panel.js'):
    def __init__(self):
        super().__init__()
        self._props.update(selection=[], open=False, available=0, busy=False,
                           materials=list(FABRIC_PRESETS))

    def configure(self, **props):
        self._props.update(props)
        self.update()
