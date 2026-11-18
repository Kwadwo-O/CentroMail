"""Gmail promotional scan tests."""

from unittest.mock import Mock, patch

import app as application
from smart_cleanup import GMAIL_BASE, scan_promotions
from test_integrations import IntegrationFixture


class PromotionScannerTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.login()
        with application.app.app_context():
            application.store_google_token(
                self.user_id,
                {"access_token": "primary-token", "expires_at": application.time.time() + 3600},
            )

    def test_scanner_paginates_and_uses_exclusion_query_and_cap(self):
        first = Mock()
        first.json.return_value = {
            "messages": [{"id": "one"}, {"id": "two"}],
            "nextPageToken": "next-page",
        }
        second = Mock()
        second.json.return_value = {"messages": [{"id": "three"}, {"id": "four"}]}

        with patch("smart_cleanup.requests.get", side_effect=[first, second]) as get:
            messages = scan_promotions("access-token", max_messages=3)

        self.assertEqual(messages, [{"id": "one"}, {"id": "two"}, {"id": "three"}])
        first_params = get.call_args_list[0].kwargs["params"]
        second_params = get.call_args_list[1].kwargs["params"]
        self.assertEqual(first_params["q"], "category:promotions -in:trash -in:spam -is:starred -is:important")
        self.assertEqual(first_params["maxResults"], 3)
        self.assertEqual(second_params["maxResults"], 1)
        self.assertEqual(second_params["pageToken"], "next-page")
        self.assertEqual(get.call_args_list[0].args[0], f"{GMAIL_BASE}/users/me/messages")
        self.assertEqual(get.call_args_list[0].kwargs["headers"], {"Authorization": "Bearer access-token"})

    def test_scanner_caps_requests_and_rejects_invalid_limits(self):
        response = Mock()
        response.json.return_value = {"messages": [{"id": str(index)} for index in range(510)]}
        with patch("smart_cleanup.requests.get", return_value=response) as get:
            messages = scan_promotions("access-token", max_messages=600)
        self.assertEqual(len(messages), 500)
        self.assertEqual(get.call_args.kwargs["params"]["maxResults"], 500)
        with patch("smart_cleanup.requests.get") as get:
            self.assertEqual(scan_promotions("access-token", max_messages=0), [])
            get.assert_not_called()
            with self.assertRaises(ValueError):
                scan_promotions("access-token", max_messages=-1)
            get.assert_not_called()

    def test_cleanup_page_and_scan_require_login(self):
        anonymous = application.app.test_client()
        self.assertEqual(anonymous.get("/cleanup").status_code, 302)
        self.assertEqual(anonymous.get("/api/cleanup/promotions").status_code, 302)

        page = self.client.get("/cleanup?account=gmail")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Scan promotions", page.data)
        self.assertIn(b'id="cleanup-progress"', page.data)
        self.assertIn(b'id="cleanup-elapsed"', page.data)
        self.assertIn(b"cleanup=1", page.data)

    def test_scan_returns_account_scoped_ids_for_progressive_preview(self):
        account_key = "email:gmail:secondary"
        with application.app.app_context():
            application.save_integration(
                self.user_id,
                account_key,
                {
                    "kind": "gmail",
                    "name": "Secondary Gmail",
                    "email": "secondary@example.com",
                    "account_id": "secondary",
                    "token": {
                        "access_token": "secondary-token",
                        "expires_at": application.time.time() + 3600,
                    },
                },
            )

        with patch.object(application, "scan_promotions", return_value=[{"id": "raw-id"}]) as scan:
            response = self.client.get(f"/api/cleanup/promotions?account={account_key}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["count"], 1)
        self.assertEqual(response.json["message_ids"], ["gm-secondary-raw-id"])
        scan.assert_called_once_with("secondary-token")

    def test_details_check_progress_and_revalidate_promotion_exclusions(self):
        promotional = {
            "id": "raw-promo",
            "sender": "Offers <offers@example.com>",
            "subject": "Weekly offers",
            "date": "Nov 18, 2026",
            "preview": "A preview",
            "label_ids": ["CATEGORY_PROMOTIONS"],
        }
        protected = {**promotional, "id": "raw-starred", "label_ids": ["CATEGORY_PROMOTIONS", "STARRED"]}
        with patch.object(application, "fetch_cleanup_gmail_detail", side_effect=[promotional, protected]):
            response = self.client.get(
                "/api/cleanup/promotions/details?account=gmail&message_ids=raw-promo&message_ids=raw-starred"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["checked"], 2)
        self.assertEqual(response.json["messages"], [{
            "id": "raw-promo",
            "sender": "Offers <offers@example.com>",
            "subject": "Weekly offers",
            "date": "Nov 18, 2026",
            "preview": "A preview",
        }])

    def test_details_reject_foreign_account_ids(self):
        with patch.object(application, "fetch_cleanup_gmail_detail") as fetch:
            response = self.client.get(
                "/api/cleanup/promotions/details?account=gmail&message_ids=gm-secondary-raw-id"
            )
        self.assertEqual(response.status_code, 400)
        fetch.assert_not_called()

    def test_trash_revalidates_candidates_and_updates_gmail_and_local_cache(self):
        promotional = {
            "id": "raw-promo",
            "label_ids": ["CATEGORY_PROMOTIONS", "INBOX"],
        }
        protected = {
            "id": "raw-starred",
            "label_ids": ["CATEGORY_PROMOTIONS", "STARRED"],
        }
        cached = application.gmail_metadata_from_payload(
            {"id": "raw-promo", "labelIds": ["INBOX"], "payload": {"headers": []}},
            "raw-promo",
        )
        with application.app.app_context():
            application.gmail_cache_put(self.user_id, "raw-promo", metadata=cached)

        gmail_response = Mock()
        with (
            patch.object(application, "fetch_cleanup_gmail_detail", side_effect=[promotional, protected]),
            patch.object(application.google_requests, "post", return_value=gmail_response) as trash,
        ):
            response = self.post_form(
                "/api/cleanup/promotions/trash",
                {
                    "account": "gmail",
                    "message_ids": ["raw-promo", "raw-starred"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"trashed": 1, "skipped": 1, "ids": ["raw-promo"]})
        self.assertEqual(trash.call_args.kwargs["json"], {
            "ids": ["raw-promo"],
            "addLabelIds": ["TRASH"],
            "removeLabelIds": ["INBOX"],
        })
        with application.app.app_context():
            cached_row = application.get_db().execute(
                "SELECT 1 FROM gmail_cache WHERE user_id=? AND message_id=?",
                (self.user_id, "raw-promo"),
            ).fetchone()
        self.assertIsNone(cached_row)

    def test_trash_rejects_ids_from_another_gmail_account(self):
        with patch.object(application, "fetch_cleanup_gmail_detail") as fetch, patch.object(
            application.google_requests, "post"
        ) as trash:
            response = self.post_form(
                "/api/cleanup/promotions/trash",
                {
                    "account": "gmail",
                    "message_ids": ["gm-secondary-foreign-id"],
                },
            )
        self.assertEqual(response.status_code, 400)
        fetch.assert_not_called()
        trash.assert_not_called()

    def test_scan_rejects_non_gmail_accounts_without_scanning(self):
        account_key = "email:imap:mailbox"
        with application.app.app_context():
            application.save_integration(
                self.user_id,
                account_key,
                {"kind": "imap", "name": "IMAP", "email": "imap@example.com"},
            )
        with patch.object(application, "scan_promotions") as scan:
            response = self.client.get(f"/api/cleanup/promotions?account={account_key}")
        self.assertEqual(response.status_code, 400)
        scan.assert_not_called()

    def test_expired_gmail_access_returns_refresh_instruction_to_cleanup_client(self):
        error = application.requests.HTTPError("expired access token")
        error.response = Mock(status_code=401)
        with patch.object(application, "scan_promotions", side_effect=error):
            response = self.client.get("/api/cleanup/promotions?account=gmail")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.json["refresh_required"])

    def test_rate_limit_403_is_retried_and_not_reported_as_missing_permission(self):
        error = application.requests.HTTPError("rate limited")
        error.response = Mock(status_code=403)
        error.response.json.return_value = {
            "error": {"errors": [{"reason": "userRateLimitExceeded"}]}
        }
        with patch.object(application, "scan_promotions", side_effect=error):
            response = self.client.get("/api/cleanup/promotions?account=gmail")
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json["retryable"])
        self.assertNotIn("reconnect", response.json)

    def test_detail_retries_google_rate_limit_before_returning_message(self):
        error = application.requests.HTTPError("rate limited")
        error.response = Mock(status_code=403)
        error.response.json.return_value = {
            "error": {"errors": [{"reason": "rateLimitExceeded"}]}
        }
        message = {"id": "message"}
        with (
            patch.object(application, "_fetch_gmail_detail", side_effect=[error, message]) as fetch,
            patch.object(application.time, "sleep") as sleep,
        ):
            result = application.fetch_cleanup_gmail_detail({}, "message")
        self.assertEqual(result, message)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_insufficient_permission_403_asks_for_reconnect(self):
        error = application.requests.HTTPError("permission denied")
        error.response = Mock(status_code=403)
        error.response.json.return_value = {
            "error": {"errors": [{"reason": "insufficientPermissions"}]}
        }
        with patch.object(application, "scan_promotions", side_effect=error):
            response = self.client.get("/api/cleanup/promotions?account=gmail")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json["reconnect"])
        self.assertNotIn("retryable", response.json)

    def test_cleanup_refresh_forces_token_refresh_for_selected_account(self):
        with patch.object(application, "get_gmail_access_token", return_value="new-access-token") as refresh:
            response = self.post_form(
                "/api/cleanup/gmail/refresh",
                {"account": "gmail"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"reconnected": True})
        refresh.assert_called_once()
        self.assertTrue(refresh.call_args.kwargs["force_refresh"])

    def test_oauth_reconnect_returns_to_cleanup_and_resumes_scan(self):
        previous = {
            key: application.app.config[key]
            for key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
        }
        self.addCleanup(application.app.config.update, previous)
        application.app.config.update(
            GOOGLE_CLIENT_ID="client",
            GOOGLE_CLIENT_SECRET="secret",
            GOOGLE_REDIRECT_URI="http://localhost/auth/google/callback",
        )
        with patch.object(application.google, "authorize_redirect", return_value=application.redirect("/google")):
            response = self.client.get(
                "/auth/google?connect=1&cleanup=1&account=gmail"
            )
        self.assertEqual(response.location, "/google")

        token = {
            "access_token": "reconnected-token",
            "expires_at": application.time.time() + 3600,
            "userinfo": {
                "email": "integrations@example.com",
                "email_verified": True,
                "name": "Integration Tester",
            },
        }
        with patch.object(application.google, "authorize_access_token", return_value=token):
            response = self.client.get("/auth/google/callback")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/cleanup?account=gmail&resume=1")
