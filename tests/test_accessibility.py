"""Check rendered landmarks, form names, and ARIA references without live accounts."""
import unittest
from html.parser import HTMLParser
from unittest.mock import patch

import app as application
import test_auth


class PageMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.parents = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append((tag, attributes, 'label' in self.parents))
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.parents.append(tag)

    def handle_endtag(self, tag):
        if tag in self.parents:
            self.parents = self.parents[:len(self.parents) - 1 - self.parents[::-1].index(tag)]


class AccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.auth = test_auth.AuthTests()
        self.auth.setUp()
        self.addCleanup(self.auth.doCleanups)

    def check_page(self, html):
        elements = PageMarkup(html).elements
        ids = [attrs['id'] for _, attrs, _ in elements if 'id' in attrs]
        labels = {attrs['for'] for tag, attrs, _ in elements if tag == 'label' and 'for' in attrs}
        self.assertEqual(len(ids), len(set(ids)), 'IDs must be unique')
        self.assertEqual(sum(tag == 'main' for tag, _, _ in elements), 1)
        for tag, attrs, wrapped in elements:
            for attribute in ('aria-labelledby', 'aria-describedby', 'aria-controls'):
                for reference in attrs.get(attribute, '').split():
                    self.assertIn(reference, ids, (tag, attribute, reference))
            if tag in {'input', 'select', 'textarea'} and attrs.get('type') != 'hidden':
                self.assertTrue(wrapped or attrs.get('id') in labels or attrs.get('aria-label') or attrs.get('aria-labelledby'), (tag, attrs))

    def test_pages_have_named_fields_and_valid_landmarks(self):
        for route in ('/', '/login', '/register', '/onboarding'):
            with self.subTest(route=route):
                self.check_page(self.auth.client.get(route).text)
        self.auth.register()
        for route in ('/dashboard', '/settings', '/integrations', '/inbox', '/privacy', '/terms'):
            with self.subTest(route=route):
                self.check_page(self.auth.client.get(route).text)

    def test_message_heading_matches_page_or_reading_pane(self):
        self.auth.register()
        message = {**self.auth.mail_metadata('accessible'), 'body': {'text': 'An email body.'}}
        with patch.object(application, 'fetch_gmail_message', return_value=message):
            self.check_page(self.auth.client.get('/message/accessible').text)
            for query, heading in (('', 'h1'), ('?pane=1', 'h2')):
                with self.subTest(query=query):
                    elements = PageMarkup(self.auth.client.get('/message/accessible' + query).text).elements
                    subjects = [tag for tag, attrs, _ in elements if attrs.get('class') == 'reader-subject']
                    self.assertEqual(subjects, [heading])

    def test_both_settings_menus_reach_every_section(self):
        self.auth.register()
        elements = PageMarkup(self.auth.client.get('/settings').text).elements
        sections = {attrs['data-settings-section'] for _, attrs, _ in elements if 'data-settings-section' in attrs}
        desktop = {attrs['data-settings-nav'] for _, attrs, _ in elements if 'data-settings-nav' in attrs}
        mobile = {attrs['value'] for tag, attrs, _ in elements if tag == 'm3e-menu-item'}
        self.assertEqual(desktop, sections)
        self.assertEqual(mobile, sections)


if __name__ == '__main__':
    unittest.main()
