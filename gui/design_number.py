"""Unbounded numeric design input; preset ranges are suggestions for exploration."""
from decimal import Decimal, InvalidOperation
import inspect
import math

from nicegui import ui


def parse_number(text, kind):
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a number.') from None
    if not value.is_finite() or not math.isfinite(float(value)):
        raise ValueError('Enter a finite number.')
    if kind == 'int':
        if value != value.to_integral_value():
            raise ValueError('Enter a whole number.')
        return int(value)
    return float(value)


class DesignNumberInput(ui.input):
    def __init__(self, label, parameter, on_commit):
        self.parameter = parameter
        self.commit_value = on_commit
        self.committed_text = str(parameter['v'])

        def validate(text):
            try:
                parse_number(text, parameter['type'])
            except ValueError as error:
                return str(error)
            return None

        super().__init__(label=label, value=str(parameter['v']), validation=validate,
                         on_change=lambda e: setattr(e.sender, 'error', None))
        self.without_auto_validation()
        self.classes('w-full').props('outlined dense debounce=0 inputmode=decimal')
        suggested = parameter.get('range')
        if suggested:
            self._props['hint'] = f'Suggested: {suggested[0]:g}–{suggested[1]:g}'
            self.props('hide-hint')
        self.on('keydown.enter.prevent', self.commit)
        self.on('blur', self.commit)

    async def commit(self):
        if self.is_ignoring_events:
            return True
        # Drafting can adjust dependent parameters. An untouched field must not
        # overwrite those changes when Save commits the focused input.
        if self.value == self.committed_text:
            return True
        if not self.validate():
            return False
        value = parse_number(self.value, self.parameter['type'])
        self.committed_text = self.value
        if value != self.parameter['v']:
            result = self.commit_value(value)
            if inspect.isawaitable(result):
                await result
        return True

    def set_number(self, value):
        self.committed_text = str(value)
        self.set_value(str(value))
        self.error = None
