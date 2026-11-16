"""HTML email clipping, safety and cache refresh regressions."""
import base64
from unittest.mock import Mock, patch

import app as a
from test_integrations import IntegrationFixture


class EmailFormattingTests(IntegrationFixture):
    html = '''<style>.preview {height:0;max-height:0;width:0;opacity:0;visibility:hidden;overflow:hidden}
        @media(max-width:600px){.desktop-only{display:none}}
        @import url(https://example.com/unsafe.css);</style>
        <div class="preview">Hidden preview</div>
        <div style="height:0;max-height:0;width:0;overflow:hidden;opacity:0;visibility:hidden;mso-hide:all">Hidden inline preview</div>
        <div hidden>Native hidden preview</div>
        <table width="512" style="width:512px;max-width:512px;margin:0 auto"><tr><td>
        <h2>Your weekly update</h2><p>A normally formatted message.</p>
        <a href="javascript:alert(1)" onclick="alert(1)">Read more</a>
        <img src="https://example.com/logo.png" onerror="alert(1)">
        <script>alert(1)</script></td></tr></table>'''

    def setUp(self):
        super().setUp()
        self.login()
        with a.app.app_context():
            a.store_google_token(self.user_id, {'access_token':'fixture-token', 'expires_at':a.time.time()+3600})

    def payload(self):
        return {'id':'sample', 'threadId':'thread', 'labelIds':['INBOX'],
                'payload':{'headers':[{'name':'From','value':'Sender <sender@example.com>'},
                                      {'name':'Subject','value':'Your weekly update'}],
                           'mimeType':'text/html', 'body':{'data':base64.urlsafe_b64encode(self.html.encode()).decode()}}}

    def test_hidden_preview_styles_survive_without_allowing_active_content(self):
        body=a.decode_gmail_body(self.payload()['payload'])
        for style in ('overflow:hidden','visibility:hidden','opacity:0','overflow:hidden;', 'mso-hide:all'):
            self.assertIn(style,body['html'])
        self.assertIn(' hidden',body['html'])
        self.assertIn('@media',body['html'])
        self.assertIn('width:512px',body['html'])
        for unsafe in ('@import','<script','onclick=','onerror=','javascript:'):
            self.assertNotIn(unsafe,body['html'])

    def test_old_html_is_refetched_once_and_current_formatting_is_cached(self):
        payload=self.payload()
        with a.app.app_context():
            a.gmail_cache_put(self.user_id,'sample',metadata=a.gmail_metadata_from_payload(payload,'sample'),
                             body={'text':'Old preview','html':'<div style="width:0;height:0">Broken preview</div>'})
            self.assertIsNone(a.gmail_cache_get(self.user_id,'sample',body=True))
        remote=Mock();remote.json.return_value=payload
        with patch.object(a.google_requests,'get',return_value=remote) as fetch:
            page=self.client.get('/message/sample?account=gmail')
            pane=self.client.get('/message/sample?account=gmail&pane=1')
        self.assertEqual(page.status_code,200)
        self.assertEqual(pane.status_code,200)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(fetch.call_args.kwargs['params']['format'],'full')
        self.assertIn(b'overflow:hidden',page.data)
        self.assertIn(b'overflow:hidden',pane.data)
        with a.app.app_context():
            cached=a.gmail_cache_get(self.user_id,'sample',body=True)
            self.assertEqual(cached['html_version'],a.EMAIL_HTML_VERSION)
            self.assertIn('visibility:hidden',cached['html'])

    def test_plain_text_cache_is_kept(self):
        with a.app.app_context():
            a.gmail_cache_put(self.user_id,'sample',metadata=a.gmail_metadata_from_payload(self.payload(),'sample'),
                             body={'text':'A plain text email'})
        with patch.object(a.google_requests,'get') as fetch:
            page=self.client.get('/message/sample?account=gmail')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'A plain text email',page.data)
        fetch.assert_not_called()
