"""Numeric editing accepts exploratory values without saving invalid drafts."""
import unittest

from gui.design_number import DesignNumberInput, parse_number
from nicegui import ui

test_container = ui.column()


class DesignNumberTests(unittest.IsolatedAsyncioTestCase):
    def test_unbounded_numbers(self):
        self.assertEqual(parse_number(' -2.75 ', 'float'), -2.75)
        self.assertEqual(parse_number('1e3', 'int'), 1000)
        for value in ('', '-', 'NaN', 'Infinity', '1e9999', 'abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_number(value, 'float')
        with self.assertRaisesRegex(ValueError, 'whole'):
            parse_number('1.2', 'int')

    async def test_apply_and_invalid_edits(self):
        param = {'v': 1.4, 'type': 'float', 'range': [1.1, 1.7]}
        applied = []

        async def apply(value):
            param['v'] = value
            applied.append(value)

        with test_container:
            field = DesignNumberInput('Length', param, apply)
        field.set_value('1.85')
        self.assertTrue(await field.commit())
        self.assertTrue(await field.commit())
        self.assertEqual(applied, [1.85])
        field.set_value('-')
        self.assertFalse(await field.commit())
        self.assertEqual(param['v'], 1.85)
        field.set_number(1.5)
        param['v'] = 1.6  # generator changed a dependent value
        self.assertTrue(await field.commit())
        self.assertEqual(param['v'], 1.6)
        self.assertIsNone(field.error)


if __name__ == '__main__':
    unittest.main()
