# Accessibility review

Reviewed 16 November 2026 using the accessibility-a11y skill.

## Fixes

- Compose focuses the recipient field, shows a focus indicator, and restores focus when closed with Escape or the close/discard actions.
- The mobile mailbox menu has a close button, a labelled dialog state, keyboard focus containment, and focus return. Closed menu links are hidden and inert; the background is inert while the menu is open.
- Email/Apps tabs support arrow keys, Home, and End, with linked panels and one active tab stop.
- The reading pane receives focus and returns it to the email link on closing. A short status announces loading instead of treating the entire email as a live region.
- Inbox checkboxes have 44-pixel targets. Message controls include the subject, and unread state is available as text to screen readers.
- Lazy loading preserves focus; automatic refresh pauses while focus is in the message list or reading pane.
- Sign-in loading focuses Cancel and returns focus to the initiating control after cancellation.
- Dashboard account controls keep an accessible name on mobile. Dashboard and Inbox use one main landmark each; email headings match the page or pane context.
- Onboarding has a skip link, Telegram fields have visible keyboard focus, and the Privacy table supports keyboard scrolling.
- Loading indicators respect both saved and system reduced-motion preferences.
- Settings navigation has a rounded outer container without clipping link focus indicators.

## Verification

All 63 Python tests passed, including rendered landmark, field-name, ARIA-reference, and email-heading regressions. All ten app scripts and 18 rendered inline scripts passed syntax checks.

Firefox keyboard checks passed for tabs, Compose, reading-pane focus, mobile menu containment/return, sign-in cancellation, and lazy-loading focus. System and saved reduced-motion checks passed.

Axe-core found no violations for the tested WCAG A/AA rules on Landing, Login, Register, Onboarding, Dashboard, Settings, Integrations, Inbox, Message, Privacy, and Terms in light/dark themes, at 320/768-pixel widths, and at verified 200% browser zoom. Mobile menu interactions were also checked at 390 pixels.

Manual screen-reader and user testing were not performed. Browser checks used local message fixtures; arbitrary received HTML emails depend on their sender's markup. These checks do not establish full WCAG conformance.
