"""Regression tests for shared UI wiring."""

import unittest
from pathlib import Path

import app as application


class UiTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def test_material_symbols_class_loads_the_vendored_icon_font(self):
        theme = (self.root / "static/css/centromail-theme.css").read_text()
        self.assertIn('.material-symbols-rounded {', theme)
        self.assertIn('font-family: "Material Symbols Rounded";', theme)
        self.assertIn('font-feature-settings: "liga";', theme)

    def test_keyboard_shortcuts_and_reader_resizer_are_wired(self):
        base = (self.root / "templates/base.html").read_text()
        mail = (self.root / "templates/mail.html").read_text()
        script = (self.root / "static/js/keyboard-shortcuts.js").read_text()
        js = (self.root / "static/js/mail.js").read_text()
        css = (self.root / "static/css/mail.css").read_text()
        self.assertIn('js/keyboard-shortcuts.js', base)
        self.assertIn('id="reader-resizer"', mail)
        self.assertIn('show-shortcuts', mail)
        self.assertIn('CentroMailShortcuts.register(', script)
        self.assertIn("shortcuts.register('j'", js)
        self.assertIn("shortcuts.register('c'", js)
        self.assertIn('reader-resizer', js)
        self.assertIn('.reader-resizer-handle', css)

    def test_inbox_pagination_is_fifty_messages_per_page(self):
        messages = [{"id": str(index)} for index in range(123)]

        first = application.paginate_messages(messages, 1)
        second = application.paginate_messages(messages, 2)
        last = application.paginate_messages(messages, 99)

        self.assertEqual(len(first["messages"]), 50)
        self.assertEqual(first["first"], 1)
        self.assertEqual(first["last"], 50)
        self.assertEqual(second["messages"][0]["id"], "50")
        self.assertEqual(second["page"], 2)
        self.assertEqual(second["pages"], 3)
        self.assertEqual(last["page"], 3)
        self.assertEqual(len(last["messages"]), 23)


if __name__ == "__main__":
    unittest.main()
