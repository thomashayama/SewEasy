"""Skin tone and hair controls for a measurement profile's mannequin.

Both are part of a body profile, edited beside its measurements and saved
with them. Each editor reports changes through an async callback so the page
can redraw its mannequin, and exposes the value to save.
"""
from nicegui import ui

from seweasy.meshgen import hair as hair_model
from webapp import measurement_guide as guide

UNDERTONE_HINT = ('Undertone is the colour beneath the surface: rosy (cool), peach (neutral), '
                  'golden (warm) or a muted green-gold (olive). If the veins at your wrist look '
                  'blue or purple, try cool; green suggests warm or olive; both suggests neutral.')


class SkinToneEditor:
    """Depth (fair to deep) and undertone; saved as a '#rrggbb' colour."""

    def __init__(self, stored, readonly, on_change):
        self.stored, self.touched, self.on_change = stored, False, on_change
        depth, undertone = guide.skin_tone_params(stored) if stored else (.3, 'neutral')
        with ui.column().classes('se-skin-editor w-full gap-1 mt-2'):
            with ui.row(wrap=False).classes('se-skin-row items-center gap-3 w-full'):
                ui.label('Skin tone').classes('se-param-label w-24')
                self.undertone = ui.toggle(guide.SKIN_UNDERTONES, value=undertone, on_change=self._changed) \
                    .props('no-caps unelevated rounded dense toggle-color=primary padding="2px 10px"') \
                    .classes('se-skin-undertone')
            with ui.row(wrap=False).classes('se-skin-row items-center gap-3 w-full'):
                ui.label('Fair').classes('se-param-label se-skin-end')
                self.slider = ui.slider(value=depth, min=0., max=1., step=.01) \
                    .props('dense aria-label="Skin depth, fair to deep"').classes('se-skin-slider grow') \
                    .on('update:model-value', lambda e: self._paint(float(e.args)), throttle=.05) \
                    .on('change', self._changed)
                ui.label('Deep').classes('se-param-label se-skin-end')
            self.note = ui.label('' if stored else 'Not set: the mannequin is plain muslin until you choose.') \
                .classes('se-param-label')
            ui.label(UNDERTONE_HINT).classes('se-param-label se-skin-hint')
        self._paint(depth)
        if readonly:
            self.undertone.disable()
            self.slider.disable()

    @property
    def value(self):
        """The colour to save: the chosen one once touched, else what was stored."""
        return self.color() if self.touched else self.stored

    def color(self):
        return guide.skin_tone_hex(self.slider.value, self.undertone.value)

    def _paint(self, depth=None):
        depth = self.slider.value if depth is None else depth
        track = ', '.join(guide.skin_tone_gradient(self.undertone.value))
        self.slider.style(f'color: {guide.skin_tone_hex(depth, self.undertone.value)}; '
                          f'--se-skin-track: linear-gradient(90deg, {track})')

    async def _changed(self, _=None):
        self.touched = True
        self.note.set_text('')
        self._paint()
        await self.on_change(self.color())


class HairEditor:
    """A starting style, a colour, then every part of it adjustable."""

    def __init__(self, hair, readonly, on_change):
        self.value = hair_model.clean_hair(hair)
        self.touched, self.on_change, self._syncing = False, on_change, False
        self.controls = []
        with ui.column().classes('se-hair-editor w-full gap-2 mt-4'):
            ui.label('Hair').classes('se-section-label')
            with ui.row().classes('se-hair-presets gap-1'):
                self.presets = {
                    key: ui.button(label, on_click=lambda _, k=key: self.choose(k))
                    .props('dense no-caps outline size=sm').classes('se-hair-preset')
                    for key, (label, _) in hair_model.PRESETS.items()}
            with ui.row().classes('se-hair-colors items-center gap-2'):
                self.swatches = {}
                for color, label in hair_model.HAIR_COLORS.items():
                    self.swatches[color] = ui.button(on_click=lambda _, c=color: self.set(color=c)) \
                        .props(f'round dense unelevated aria-label="{label}"').classes('se-hair-swatch') \
                        .style(f'background: {color} !important').tooltip(label)
                with ui.button(icon='colorize').props('round dense flat aria-label="Another colour"') \
                        .classes('se-hair-custom').tooltip('Another colour') as custom:
                    ui.color_picker(on_pick=lambda e: self.set(color=e.color))
                self.controls.append(custom)
            with ui.element('div').classes('se-hair-adjust w-full'):
                self.length_label = self._label('Length')
                self.length = self._slider(0, hair_model.MAX_LENGTH, .1, 'length', 'Hair length')
                self._label('Volume')
                self.volume = self._slider(0, 1, .05, 'volume', 'Hair volume')
                self._label('Texture')
                self.texture = self._toggle(hair_model.TEXTURES, 'texture')
                self._label('Tied')
                self.tie = self._toggle(hair_model.TIES, 'tie')
                self._label('Fringe')
                self.fringe = self._toggle(hair_model.FRINGES, 'fringe')
                self._label('Parting')
                self.part = self._toggle(hair_model.PARTS, 'part')
                self._label('Hairline')
                with ui.row(wrap=False).classes('items-center gap-2 w-full'):
                    ui.label('Full').classes('se-param-label se-skin-end')
                    self.recede = self._slider(0, 1, .05, 'recede', 'Receding hairline')
                    ui.label('Receding').classes('se-param-label se-skin-end')
        self.controls += [*self.presets.values(), *self.swatches.values()]
        self._sync()
        if readonly:
            for control in self.controls:
                control.disable()

    def _label(self, text):
        return ui.label(text).classes('se-param-label se-hair-label')

    def _slider(self, low, high, step, key, name):
        slider = ui.slider(min=low, max=high, step=step, value=self.value[key]) \
            .props(f'dense aria-label="{name}"').classes('grow') \
            .on('update:model-value', lambda e: key == 'length' and self._show_length(float(e.args)), throttle=.05) \
            .on('change', lambda e: self.set(**{key: float(e.args)}))
        self.controls.append(slider)
        return slider

    def _toggle(self, options, key):
        toggle = ui.toggle(options, value=self.value[key],
                           on_change=lambda e: None if self._syncing else self.set(**{key: e.value})) \
            .props('no-caps unelevated rounded dense toggle-color=primary padding="2px 9px"').classes('se-hair-toggle')
        self.controls.append(toggle)
        return toggle

    def _show_length(self, length):
        stop = hair_model.LENGTH_STOPS[int(round(length))]
        self.length_label.set_text(f'Length · {stop}')

    async def choose(self, key):
        """Start from a preset, keeping the chosen colour."""
        await self._apply(hair_model.preset(key, color=self.value['color']))

    async def set(self, **changes):
        await self._apply({**self.value, **changes})

    async def _apply(self, hair):
        hair = hair_model.clean_hair(hair)
        hair['style'] = hair_model.matching_preset(hair) or 'custom'
        if hair == self.value:
            return
        self.value, self.touched = hair, True
        self._sync()
        await self.on_change(hair)

    def _sync(self):
        """Show the current values: highlight the preset and colour, grey out what doesn't apply."""
        hair = self.value
        self._syncing = True
        try:
            for key, button in self.presets.items():
                button.props('unelevated color=primary' if key == hair['style'] else 'outline color=primary',
                             remove='unelevated outline')
            for color, swatch in self.swatches.items():
                swatch.classes(add='is-active' if color == hair['color'] else '',
                               remove='' if color == hair['color'] else 'is-active')
            for key in ('length', 'volume', 'recede'):
                getattr(self, key).value = hair[key]
            for key in ('texture', 'tie', 'fringe', 'part'):
                getattr(self, key).value = hair[key]
        finally:
            self._syncing = False
        self._show_length(hair['length'])
        bald = not hair_model.has_hair(hair)
        tied = hair['tie'] != 'none'
        for control, off in ((self.volume, bald), (self.texture, bald), (self.tie, bald or hair['length'] < 3),
                             (self.fringe, bald or tied), (self.part, bald or tied)):
            control.props('disable' if off else '', remove='' if off else 'disable')
