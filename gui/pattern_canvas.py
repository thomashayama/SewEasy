"""Browser-local pattern picking; only selection changes cross the connection."""
from pathlib import Path

from nicegui import ui
from nicegui.elements.mixins.source_element import SourceElement
from nicegui.element import Element


class PatternCanvas(SourceElement, component='pattern_canvas.js'):
    def __init__(self):
        super().__init__(source='')
        ui.add_css(Path(__file__).with_name('fabric_editor.css').read_text())
        self._props.update(pieces=[], selected=[], viewbox='0 0 1 1')

    def configure(self, **props):
        self._props.update(props)
        self.update()


class FabricPanel(Element, component='fabric_panel.js'):
    def __init__(self):
        super().__init__()
        self._props.update(selection=[], open=True, available=0, busy=False)

    def configure(self, **props):
        self._props.update(props)
        self.update()
