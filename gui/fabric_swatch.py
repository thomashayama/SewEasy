"""NiceGUI bridge for a synchronized browser-only fabric experiment."""
from pathlib import Path

from nicegui import ui
from nicegui.element import Element


class FabricSwatch(Element, component='fabric_swatch.js'):
    def __init__(self, identity, name, weight):
        super().__init__()
        # Registers the existing, versioned WebGPU module mount.
        from gui import browser_drape  # noqa: F401
        ui.add_css(Path(__file__).with_suffix('.css').read_text())
        self._props.update(scene_url=f'/fabric-preview/{identity}', fabric_name=name, weight_gsm=weight)
