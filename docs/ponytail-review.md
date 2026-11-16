What this change does: CentroMail now has organised Settings with 59 working preferences, including 49 additional controls, shared across the app. Email connections support Gmail OAuth, Microsoft Graph OAuth, 51 IMAP/SMTP provider options, multiple account selection, and lazy message pages.

Reviewed the connected Flask routes, account persistence, protocol adapters, templates, shared preference scripts, and tests. Assumed one person running the local Flask application.

Looks good for local use. Ship.

Validation:

- All 64 Python tests pass. New checks cover rendered accessibility markup and Settings menu coverage, verified TLS, 25-header IMAP pages, account/folder/UIDVALIDITY isolation, safe moves, SMTP Sent-copy failures, account routing and disconnect scope, Microsoft callback ownership and page-link validation, and malformed webhook signatures.
- Three JavaScript regression checks pass for invalid saved preferences, scoped resets, and confirmation behaviour. All ten app scripts pass syntax checks in their browser module context where required.
- Firefox checks cover all 59 controls, category navigation and search, group resets, validated JSON import, theme generation/reset races, shared text sizing, sidebar width, logo sizing, inbox visibility options, dashboard options, provider prefill, and confirmations.
- Settings search now uses the M3E Search CSS contract, one rounded focus indicator, and a working clear action. Settings categories use the M3E Menu CSS contract; dashboard/inbox account and workspace dropdowns use the actual vendored M3E Menu element, including keyboard navigation and shared theme/logout handling. Browser search, menu, and accessibility checks pass.
- Mobile Settings uses a compact M3E category menu, collapsible preview, full-width controls/actions, and less card padding. All categories and larger text fit 320–900 pixels; short-screen keyboard scrolling, both themes, desktop navigation, and 200% zoom checks pass.
- The follow-up [accessibility review](accessibility-review.md) covers keyboard focus, mobile sidebar containment, linked tabs, reduced-motion indicators, and verified 200% zoom. Manual screen-reader testing remains outstanding.
- Follow-up screenshot fixes centre the dashboard within a full-width page, preserve the stacked layout through 1050 pixels, and align Settings navigation icons, labels, and counts even with narrow sidebars and larger text. Firefox checks pass in light and dark themes.
- The tested Settings, Integrations, Dashboard, Inbox, landing, login, and register pages fit 320, 390, 768, and 1440 pixels. Larger saved text also fits the tested mobile pages.
- Axe-core found no WCAG A/AA violations in tested categories and main-page light/dark states, including high-contrast Settings. Dashboard label contrast, login overflow, and overlapping inbox link targets were corrected. No visible drop shadows remain in checked pages.
- Anonymous transport probes verified 89 of the 98 current public preset endpoints; 23 SMTP defaults now use verified port-465 TLS alternatives. Login and delivery were not attempted. See [the transport report](email-provider-connectivity.md).
- The setup requirements and unsupported-provider limits are documented in [Email provider setup](email-provider-setup.md).

Verdict: Ship for local use. The app has been restarted with these changes.

Not checked: Live provider credentials or delivery, Google/Microsoft consent with a real account, Proton Bridge certificates, Android hardware, manual screen-reader operation, or production concurrency. Browser mail used disposable rendered accounts and simulated responses. Provider presets are editable defaults, not evidence of a live connection. Passwords and refresh tokens remain in the local SQLite database without encryption at rest; hosted multi-user deployment requires a separate security review.
