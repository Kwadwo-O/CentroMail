# CentroMail

## Run locally

From this folder in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000/login** in your browser. HTML templates must be
served by Flask; opening `templates/login.html` directly as a file does not run
the login backend or resolve its CSS links.

Create an account using the **Create account** link on the login card. Enter a
name, email, and matching passwords of at least 12 characters. Registration
signs you in and opens the dashboard. Log out to test signing back in.
The **Get started** link opens `/onboarding`, where Continue with Email checks
whether the address needs login or registration.

Accounts persist in `centro.db`, created automatically on startup. Passwords
are stored as hashes, and each account has a unique email address regardless
of letter case. Existing account databases receive the missing name field
automatically. The **Remember me** option keeps a login for up to 30 days;
otherwise the cookie lasts for the browser session.

A local session secret is generated once in `instance/.secret_key`. Keep this
file private and retain it across restarts, or set the `SECRET_KEY` environment
variable to a strong random secret. Set `CENTROMAIL_DATABASE` to choose a
different SQLite file. For hosting over HTTPS, set `CENTROMAIL_COOKIE_SECURE=1`
and use a production WSGI server. `FLASK_DEBUG=1` enables local debug mode.

### Google sign-in

In Google Cloud Console, configure an OAuth client ID for a Web application.
Add `http://localhost:5000/auth/google/callback` as an authorized redirect URI.
Before starting Flask in PowerShell, provide the client credentials:

```powershell
$env:GOOGLE_CLIENT_ID = "your-client-id"
$env:GOOGLE_CLIENT_SECRET = "your-client-secret"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The callback URI can be overridden with `GOOGLE_REDIRECT_URI` if it differs
from the local address above. The URI must match exactly; `localhost` and
`127.0.0.1` are different hosts, so add both callback URIs in Google Cloud if
you use both addresses. Keep the client secret private. Google sign-in
creates a CentroMail account for a new verified email or signs into an existing
account with the same email, then opens the dashboard. Google sign-in does not
connect Gmail; inbox messages and sending remain demo features.

Microsoft sign-in still requires OAuth integration.

Run the authentication integration tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

<p align="center">
  <strong>Your conversations. One place.</strong>
  <br />
  A unified communication hub for email and messaging.
  <br /><br />
  <img src="https://img.shields.io/badge/Status-In%20Development-7CA982?style=for-the-badge" alt="In Development" />
  <img src="https://img.shields.io/badge/Platform-Cross--Platform-50745C?style=for-the-badge" alt="Cross Platform" />
  <img src="https://img.shields.io/badge/Focus-Privacy-243E36?style=for-the-badge" alt="Privacy Focused" />
</p>

---

## What is CentroMail?

CentroMail is an upcoming unified communication application that brings your email accounts and supported messaging services together in one place.

Instead of jumping between different apps to keep up with conversations, CentroMail aims to give you one clean, organised space to manage everything.

Designed with simplicity, customisation and privacy in mind, CentroMail is about making digital communication feel less fragmented.

## The idea

<details>
<summary><strong>One inbox. Multiple services.</strong></summary>

Bring supported email accounts and messaging integrations together without constantly switching applications.

</details>

<details>
<summary><strong>Stay in control.</strong></summary>

Manage multiple accounts, keep conversations organised and know exactly which account you're using when replying.

</details>

<details>
<summary><strong>Your space, your style.</strong></summary>

A modern, customisable interface designed to make everyday communication feel natural and intuitive.

</details>

<details>
<summary><strong>Privacy matters.</strong></summary>

A privacy-conscious approach to account connections, permissions and personal communications.

</details>

## Features

| Feature | Description |
|---|---|
| Unified inbox | Bring supported conversations into one interface. |
| Multiple accounts | Keep different email accounts together. |
| Smart organisation | Make conversations easier to sort and prioritise. |
| Quick replies | Reply using the correct connected account. |
| Integrations | Expand CentroMail with supported services. |
| Local messaging | Explore communication between CentroMail users. |
| Customisation | A consistent, modern and expressive interface. |
| Privacy-focused | Keep control of connected accounts and permissions. |

*Features are planned and under development. Availability will depend on the progress of development and the capabilities of each service.*

## Integrations

CentroMail is being designed around an extensible integration system.

Some of the services and technologies being explored include:

| Service | Planned integration |
|---|---|
| Gmail | Google Gmail API |
| Outlook | Microsoft Graph |
| Other email providers | IMAP / SMTP |
| Messaging platforms | Supported official APIs and protocols |
| CentroMail | Native messaging between users |

**Our goal:** make it possible to manage more of your communications without needing a separate application for every service.

Third-party integrations are subject to provider APIs, permissions and restrictions. Not every platform allows external applications to access or send messages.

## Design philosophy

CentroMail takes inspiration from Google's Material 3 Expressive design language.

The aim is to create an interface that feels:

- **Clean** — uncluttered layouts that keep conversations at the centre.
- **Expressive** — rounded shapes, fluid animations and thoughtful interactions.
- **Adaptive** — designed for different screen sizes.
- **Personal** — customisable appearance and themes.
- **Accessible** — clear navigation, readable typography and intuitive controls.

<p align="center">
  <strong>CentroMail — communication, simplified.</strong>
</p>

## Project status

<badge>In development</badge>

CentroMail is actively being developed. Its features, integrations and overall design may change as the project evolves.

The current focus is establishing the core experience and building a reliable foundation for connected communication services.

## Roadmap

- [ ] Core CentroMail interface
- [ ] Unified inbox
- [ ] Account management
- [ ] Google Gmail integration
- [ ] Message synchronisation
- [ ] Sending and replying
- [ ] Multiple email accounts
- [ ] Microsoft Outlook integration
- [ ] Additional messaging integrations
- [ ] Native CentroMail messaging
- [ ] Themes and personalisation
- [ ] Privacy and security improvements
- [ ] Wider release

## Get involved

CentroMail is a growing project, and there's plenty of room for ideas, feedback and contributions.

You can help by:

- Suggesting features and improvements.
- Reporting bugs.
- Sharing ideas for integrations.
- Providing feedback on the interface.
- Contributing to development.

Keep an eye on this repository for updates as CentroMail develops.

## Disclaimer

CentroMail is an independent project and is not affiliated with, endorsed by or officially connected to Google, Microsoft or any other third-party service provider. All product names and trademarks belong to their respective owners.

---

<p align="center">
  <strong>CentroMail</strong>
  <br />
</p>
