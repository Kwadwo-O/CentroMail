# CentroMail

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

## Installation

CentroMail can be run locally on UNIX-based systems and Windows.

Before installing, make sure you have Git and Python installed. Python 3.10 or newer is recommended.

### UNIX installation guide

This guide covers Linux distributions and macOS.

#### 1. Install the required dependencies

**Debian / Ubuntu**

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential libffi-dev libssl-dev pkg-config
````

Fedora

```bash
sudo dnf install -y git python3 python3-pip python3-devel gcc gcc-c++ libffi-devel openssl-devel pkgconf-pkg-config
```

Arch Linux

```bash
sudo pacman -Syu --needed git python python-pip base-devel libffi openssl pkgconf
```

macOS

Install Homebrew if it is not already installed, then run:

```bash
brew install git python
```

### 2\. Clone the repository

```bash
git clone https://github.com/Kwadwo-O/CentroMail.git
cd CentroMail
```

### 3\. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4\. Install Python dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5\. Run CentroMail

```bash
python app.py
```

Open \*\*[http://127.0.0.1:5000/login\*\*](http://127.0.0.1:5000/login**?utm_source=chatgpt.com) in your browser.

HTML templates must be served by Flask; opening `templates/login.html` directly as a file does not run the login backend or resolve its CSS links.

To run CentroMail again later, navigate to the project directory, activate the virtual environment and start the application:

```bash
cd CentroMail
source .venv/bin/activate
python app.py
```

### Windows installation guide

This guide covers Windows 10 and Windows 11 using PowerShell.

### 1\. Install the required dependencies

Install the following:

* [Python](https://www.python.org/downloads/?utm_source=chatgpt.com)

* [Git](https://git-scm.com/downloads?utm_source=chatgpt.com)

During Python installation, enable Add Python to PATH.

Verify that both tools are available:

```powershell
py --version
git --version
```

### 2\. Clone the repository

```powershell
git clone https://github.com/Kwadwo-O/CentroMail.git
cd CentroMail
```

### 3\. Create a virtual environment

```powershell
py -m venv .venv
```

### 4\. Install Python dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5\. Run CentroMail

```powershell
.\.venv\Scripts\python.exe app.py
```

Open  **http://127.0.0.1:5000/login** in your browser.

HTML templates must be served by Flask; opening `templates/login.html` directly as a file does not run the login backend or resolve its CSS links.

To run CentroMail again later, navigate to the project directory and execute:

```powershell
.\.venv\Scripts\python.exe app.py
```

### Creating an account

Create an account using the Create account link on the login card. Enter a name, email, and matching passwords of at least 12 characters. New passwords must also include an uppercase letter, a number, and a special character, and cannot be a common password or contain your name or email address. The sign-up form shows a live checklist of these rules.

Registration signs you in and opens the dashboard. Log out to test signing back in.

The Get started link opens `/onboarding`, where Continue with Email checks whether the address needs login or registration.

Accounts persist in `centro.db`, created automatically on startup. Passwords are stored as hashes, and each account has a unique email address regardless of letter case. Existing account databases receive the missing name field automatically.

The Remember me option keeps a login for up to 30 days; otherwise the cookie lasts for the browser session.

### Local configuration

A local session secret is generated once in `instance/.secret_key`. Keep this file private and retain it across restarts, or set the `SECRET_KEY` environment variable to a strong random secret.

Set `CENTROMAIL_DATABASE` to choose a different SQLite file.

For hosting over HTTPS, set `CENTROMAIL_COOKIE_SECURE=1` and use a production WSGI server. `FLASK_DEBUG=1` enables local debug mode.

### Google sign-in

In Google Cloud Console, configure an OAuth client ID for a Web application.

Add the following as an authorized redirect URI:

```text
http://localhost:5000/auth/google/callback
```

Before starting Flask, provide the client credentials.

UNIX

```bash
export GOOGLE_CLIENT_ID="your-client-id"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export GOOGLE_REDIRECT_URI="http://localhost:5000/auth/google/callback"
python app.py
```

Windows PowerShell

```powershell
$env:GOOGLE_CLIENT_ID = "your-client-id"
$env:GOOGLE_CLIENT_SECRET = "your-client-secret"
$env:GOOGLE_REDIRECT_URI = "http://localhost:5000/auth/google/callback"
.\.venv\Scripts\python.exe app.py
```

The callback URI can be overridden with `GOOGLE_REDIRECT_URI` if it differs from the local address above.

The URI must match exactly; `localhost` and `127.0.0.1` are different hosts, so add both callback URIs in Google Cloud if you use both addresses.

Keep the client secret private.

Google sign-in creates a CentroMail account for a new verified email or signs into an existing account with the same email, then opens the dashboard.

To connect another Gmail address, sign in to CentroMail and choose **Add Gmail** in the inbox or Integrations. Google opens its account picker. Each Gmail connection has its own token and local message cache, and adding one keeps your existing CentroMail login. Use **Email account** in the inbox to switch mailboxes. The Gmail API must be enabled for the Google Cloud project.

The inbox opens from a small local preview and loads Gmail in batches of 25 messages as you scroll. Refresh checks the current folder again; search and the Primary, Updates and Social tabs query Gmail across the mailbox.

Sidebar links open Inbox, Starred, Snoozed, Sent and Drafts, with additional folders under More. Folder counts come from Gmail.

On screens at least 1200 pixels wide, selecting an email opens a reading pane beside the inbox. Smaller screens open a full message page. Drag the divider between the inbox and the reading pane to resize it, or focus the divider and use the arrow keys. The width is remembered per browser. HTML emails use an isolated reader that preserves safe typography, table formatting, and hidden preview text. Previously cached HTML refreshes once when opened after a formatting update. The message body fits its content, with one scrolling area and a toolbar that stays visible. Full-page desktop readers retain the app navigation and use a rounded panel sized to the email.

Keyboard shortcuts work with a physical keyboard on desktop and mobile. Press `?` for the full list, `/` to focus search, `c` to compose, and `g` followed by `i`, `s`, `d`, `t`, or `a` to open a mail folder. In the inbox, `j`/`k` or the arrow keys move between messages, `Enter` opens, `s` stars, `x` selects, `e` archives, `#` moves to Trash, `u` toggles unread, and `r` replies. The inbox help dialog also has a **Keyboard shortcuts** button for touch devices.

Gmail read/unread changes made outside CentroMail are checked when you return to the inbox and at the configured auto-refresh interval (60 seconds by default). Checks update loaded rows in place, keeping your selection and reading pane; larger lists are checked in rotating batches. Automatic checks pause while the tab is hidden or Apps is selected. No extra Google setup is required.

Successfully opening an unread email saves its read status to the connected provider and refreshes the inbox count. If that update fails, the email stays available to read and the reader explains how to retry. Disabled Reply buttons show an M3E tooltip on hover or keyboard focus explaining the no-reply restriction.

Open an email and choose **Reply** to fill in its recipient and subject. Replies use the account that received the message and follow its Reply-To address when present. Gmail and IMAP/SMTP replies include conversation headers; Outlook uses Microsoft Graph's reply action. The editor fills the screen on phones, preserves a draft when closed, and keeps it available after a failed send.

Explicit no-reply addresses are labelled **No reply** and their Reply button is disabled. A usable Reply-To address allows replies even when the sender is no-reply. **Sort loaded emails** puts replyable messages first by default; newest-first and no-reply-first are also available and saved in your preferences. Sorting covers the messages loaded so far, including new batches as you scroll.

Emails with one clearly identified verification or sign-in code show a **Copy code** button in the list and reader. Detection runs locally on the subject, preview, and opened message. It preserves leading zeroes and avoids offering ambiguous codes; it does not validate whether a code is still usable.

Archiving, moving to Trash, changing read status and starring messages require Google’s `gmail.modify` permission. Accounts connected before this permission was added must reconnect Google and accept the updated access request.

Microsoft Outlook mail now connects to an existing CentroMail account through OAuth and Microsoft Graph. Gmail OAuth and 51 IMAP/SMTP provider options are available in Integrations. See [Email provider setup](docs/email-provider-setup.md) for credentials, app registration, regional servers, Proton Bridge, and provider limitations.

### Local integrations

Open Integrations after signing in.

Connected services appear in **Inbox → Apps** with their logo, account or channel details, and connection status. Opening a service loads its recent messages; **Refresh** checks again. Telegram supports private chats, regular groups, and forum groups with a topic picker, profile pictures, text sending, and automatic incoming-message checks while the chat is visible. Discord shows its configured bot channel, and WhatsApp Business shows locally received webhook messages. Other connected integrations appear with a management link; message feeds depend on the provider capabilities supported by CentroMail. See [Telegram setup and chat support](docs/telegram-setup.md).

Connections are stored in `centro.db` on this machine, and non-secret UI state is mirrored to browser `localStorage`.

| Service  | What is needed                                                                                                                                                                                                             |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gmail    | Google OAuth with the Gmail API enabled.                                                                                                                                                                                   |
| Telegram | A Telegram account plus an API ID/API hash from my.telegram.org/apps. CentroMail signs in to your own account and stores the session locally; a login code and, if enabled, a two-step verification password are required. |
| WhatsApp | A Meta WhatsApp Cloud API phone number ID and access token. Personal WhatsApp accounts do not have an official API. Inbound messages require a publicly reachable webhook URL and WHATSAPP_APP_SECRET set to the Meta app secret. Unsigned callbacks are rejected.               |
| Discord  | A Discord application bot token plus a channel ID. Invite the bot with View Channels, Read Message History and Send Messages. Discord does not permit automating personal user accounts.                                   |

Telegram account support uses the `telethon` package from `requirements.txt`.

### Testing

Run the authentication integration tests with:

UNIX

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### The idea

### Features

| Feature            | Description                                         |
| ------------------ | --------------------------------------------------- |
| Unified inbox      | Bring supported conversations into one interface.   |
| Multiple accounts  | Keep different email accounts together.             |
| Smart organisation | Make conversations easier to sort and prioritise.   |
| Quick replies      | Reply using the correct connected account.          |
| Integrations       | Expand CentroMail with supported services.          |
| Local messaging    | Explore communication between CentroMail users.     |
| Customisation      | A consistent, modern and expressive interface.      |
| Privacy-focused    | Keep control of connected accounts and permissions. |

Features are planned and under development. Availability will depend on the progress of development and the capabilities of each service.

### Integrations

CentroMail is being designed around an extensible integration system.

### Categorised integration groups

Integrations are organised into three logical groups for easier navigation:

| Group                          | Services                                                                                                                 |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Email accounts                 | Gmail                                                                                                                    |
| Chats and communities          | Telegram, WhatsApp, Discord                                                                                              |
| Social networks and workspaces | X (Twitter), LinkedIn, Reddit, Mastodon, Bluesky, TikTok, Pinterest, Tumblr, Twitch, Slack |

Each group has a collapsible "How to connect" guide accessible via the disclosure marker next to the service name. The guides walk through the required setup steps for each provider.

### Adding new integration categories

The integration system is extensible. New categories can be added by:

* Defining a new group heading in `templates/integrations.html`

* Adding service cards with provider logo SVGs from `static/images/integrations/`

* Including connection guide markup using native `<details>` elements

* Updating `static/css/integrations.css` for any new layout needs

Provider logo SVGs should be named consistently (e.g., `<service-name>.svg`) and placed in `static/images/integrations/`.

### Integration connection guides

Each unconnected integration shows a native accessible dropdown with setup instructions:

* Gmail – Google OAuth with Gmail API enabled

* Telegram – API ID/API hash from `my.telegram.org/apps`, optional two-step verification

* WhatsApp – Meta WhatsApp Cloud API phone number ID and access token

* Discord – Application bot token, channel ID, and required permissions

* All social integrations – Platform-specific app creation and setup links

These guides use `<details>`/`<summary>` for accessibility and respect `prefers-reduced-motion`.

Third-party integrations are subject to provider APIs, permissions and restrictions. Not every platform allows external applications to access or send messages.

### Design philosophy

CentroMail takes inspiration from Google's Material 3 Expressive design language.

The aim is to create an interface that feels:

* Clean — uncluttered layouts that keep conversations at the centre.

* Expressive — rounded shapes, fluid animations and thoughtful interactions.

* Adaptive — designed for different screen sizes.

* Personal — customisable appearance and themes.

* Accessible — clear navigation, readable typography and intuitive controls.

### Sender logos

Set `CDN_PUBLIC_KEY` to your Logo.dev publishable key (`pk_...`) in the project-root `.env`, then restart the app. Inbox rows and opened emails load company logos by sender domain. The browser uses the publishable key; `LOGO_API_SECRET_KEY` is never sent to the browser and is not needed for displaying logos.

If Logo.dev has no image or cannot load, CentroMail falls back to a bundled logo or sender initials. Without a publishable key, bundled logos continue to work. Personal email providers keep initials. No full sender address or email content is included in logo requests.

### Project status

CentroMail is actively being developed. Its features, integrations and overall design may change as the project evolves.

The current focus is establishing the core experience and building a reliable foundation for connected communication services.

### Roadmap

* Core CentroMail interface

* Unified inbox

* Account management

* Google Gmail integration

* Message synchronisation

* Sending and replying

* Multiple email accounts

* Microsoft Outlook integration

* Additional messaging integrations

* Native CentroMail messaging

* Themes and personalisation

* Privacy and security improvements

* Wider release

### Get involved

CentroMail is a growing project, and there's plenty of room for ideas, feedback and contributions.

You can help by:

* Suggesting features and improvements.

* Reporting bugs.

* Sharing ideas for integrations.

* Providing feedback on the interface.

* Contributing to development.

Keep an eye on this repository for updates as CentroMail develops.

### Disclaimer

CentroMail is an independent project and is not affiliated with, endorsed by or officially connected to Google, Microsoft or any other third-party service provider. All product names and trademarks belong to their respective owners.
