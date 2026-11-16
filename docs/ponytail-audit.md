What this repo does: CentroMail is a local Flask app with SQLite accounts, cached email, and saved provider connections. It now reads and sends Gmail, Microsoft Graph mail, and compatible IMAP/SMTP mail, alongside messaging integrations. Assumed one local user, with the WhatsApp webhook potentially reachable through a public tunnel.

This follow-up records the requested fixes to the previous audit. Reviewed authentication boundaries, webhook writes, outbound provider requests, email account isolation, caches, latency, preference wiring, and the connected tests.

## Resolved findings

| Previous finding | Implemented fix | Evidence |
| --- | --- | --- |
| 1. Unsigned WhatsApp callbacks could forge mail | Validate raw-body HMAC with the Meta app secret. Missing configuration returns 503; absent, malformed, and incorrect signatures return 403. | Signed/unsigned/malformed signature and missing-secret tests. |
| 2. Dashboard invented Sent totals | Count SENT-labelled cached messages, and explicitly label all four metrics as cached values. | Empty-cache and Sent-label checks. |
| 3. Mastodon input could reach private destinations | Validate HTTPS instance names, reject private addresses and redirects, and pin a public resolved IP while verifying TLS against the original hostname. | Destination, pinned-request, certificate, and redirect checks. |
| 4. Integrations waited for live previews | Render saved connection information immediately. Telegram/Discord previews load separately with retry and bounded waits. | Render-without-provider-calls and protected-preview tests. |
| 5. Confirmation preference did nothing | Shared form handler and inbox Trash actions read the saved setting, with confirmations enabled by default. | JavaScript and Firefox cancellation checks. |
| 6. Apps inbox had dead actions | Link Connect an app to Integrations, remove unsupported conversation actions, and disable Email search while Apps is selected. | Firefox workspace checks. |
| 7. Unused Gmail sync engine remained | Delete the unused full-mailbox engine and private state; retain the lazy loader, shared detail helper, and database cleanup. | Source caller checks and Gmail regression tests. |

## Checks added with email support

- IMAP message IDs include account, folder, UIDVALIDITY, and UID, so identical server IDs in different folders cannot change the wrong message.
- Microsoft IDs are account-bound; cursor links must point to the expected Graph host and folder path. Bulk IDs are validated before the first mutation.
- IMAP/SMTP requires verified TLS. Optional server login names and separate SMTP passwords stay out of rendered HTML and preference exports.
- IMAP moves use UID MOVE or a copy/delete fallback. Global EXPUNGE is never used, avoiding deletion of unrelated messages.
- SMTP delivery and Sent-copy failure are distinguished to avoid prompting duplicate sends. Microsoft saves its Sent copy through Graph.
- Read/star changes update cached labels as well as visible state. New message bodies reuse the isolated safe HTML/Markdown reader.

Verdict: All seven prior findings are resolved for the documented local usage. All 61 Python tests, three JavaScript regression checks, and the described Firefox checks pass. See [the change review](ponytail-review.md) and [provider setup](email-provider-setup.md).

Not checked: Live provider authentication, delivery/publishing, public webhook deployment, production load, package internals, Android hardware, or manual screen-reader use. Provider passwords and tokens are stored locally without encryption at rest. Custom IMAP servers intentionally permit local/self-hosted destinations for the owner, including Proton Bridge; hosted access by untrusted users would require destination restrictions and a separate security review.
