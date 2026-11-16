# Email provider setup

CentroMail supports Gmail through the Gmail API, Outlook/Hotmail/Live/Microsoft 365 through Microsoft Graph, and standards-compatible mailboxes through IMAP and SMTP. The provider menu contains 51 options, including regional variants, Proton Bridge, and a custom server option.

The protocol and account flows are tested with simulated servers. Real sign-in, delivery, regional server settings, and plan availability need your provider credentials. Anonymous transport results are recorded in [Public email transport checks](email-provider-connectivity.md). Presets are editable starting points; check your provider's current mail-client instructions if connection fails.

## Connect an account

1. Sign in to your existing CentroMail account.
2. Open **Integrations**. Choose **Connect Microsoft**, **Connect Google**, or an IMAP/SMTP provider.
3. For IMAP/SMTP, enable IMAP in the provider's web settings and create an app password where required. Enter your email address and that password.
4. Expand **Server settings** to override regional servers, ports, separate login usernames, or a separate SMTP password. Blank usernames use your email address; a blank SMTP password uses the account password.
5. Choose whether CentroMail should save a Sent copy. Choose **Server saves Sent automatically** for Gmail IMAP and Proton Bridge (their preset defaults), or any server that already saves sent mail. This prevents duplicates.
6. Click **Connect email**. CentroMail verifies both IMAP and SMTP login before saving the connection. Open Inbox and use the account selector to switch accounts.

Connections use verified TLS or verified STARTTLS. Unencrypted mail login is unavailable. The inbox requests 25 headers at a time, and loads the full message only when opened. IMAP starred mail searches the Inbox; other discovered folders are listed separately. Archive, Trash, Drafts, Spam, and Sent appear when the server exposes those folders. No unsupported folder is invented.

If delivery succeeds but the Sent copy fails, CentroMail reports that the message was sent. Do not send it again. Correct the server's Sent folder or automatic-save option instead. Disconnect and reconnect an account to change its saved server settings.

To reply, open an email and choose **Reply** in the reading pane or full message page. CentroMail selects that mailbox as the sender and fills the recipient and `Re:` subject. This action replies to one recipient; you can edit the address before sending. Existing mail read/send permissions cover replies, so there is no extra provider setup. Conversation threading is sent using Gmail's thread ID and mail headers, Microsoft's reply endpoint, or IMAP/SMTP mail headers, depending on the connected account. Live delivery still needs a connected account with valid credentials.

## Gmail and Google Workspace OAuth

1. Open [Google Cloud Console](https://console.cloud.google.com/), select/create a project, and enable **Gmail API**.
2. Configure the OAuth consent screen. If the app is in testing, add your Google email to its test users. Workspace administrators can restrict third-party applications.
3. Create an OAuth client of type **Web application**. Add this exact authorised redirect URI: `http://localhost:5000/auth/google/callback`.
4. Put the following in the project's private `.env` file, replacing placeholders, then restart CentroMail:

```dotenv
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
```

Keep browser and callback hostnames consistent: `localhost` and `127.0.0.1` have different cookies. For a hosted deployment, register and configure its exact HTTPS callback. Google may require verification before a public app can request Gmail scopes.

The **Google Workspace / Gmail IMAP** preset is an alternative when your account permits app passwords. Usually this requires two-step verification; organisational policy and Advanced Protection can disable app passwords. Your normal Google password does not work for IMAP. Prefer OAuth where app passwords are unavailable.

## Outlook, Hotmail, Live, and Microsoft 365 OAuth

1. Open [Microsoft Entra app registrations](https://entra.microsoft.com/) and create an app registration.
2. For both personal Outlook accounts and organisations, choose **Accounts in any organisational directory and personal Microsoft accounts**. A company-only app can use its tenant ID instead.
3. Add a **Web** redirect URI: `http://localhost:5000/auth/microsoft/callback`.
4. Add Microsoft Graph **delegated** permissions: `User.Read`, `Mail.ReadWrite`, and `Mail.Send`. The OAuth request also asks for `offline_access` so the connection can refresh. Do not configure application-wide mailbox permissions for this flow.
5. Create a client secret and copy its **value**, not its secret ID. Set these private `.env` values and restart:

```dotenv
MICROSOFT_CLIENT_ID=your-application-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret-value
MICROSOFT_TENANT=common
MICROSOFT_REDIRECT_URI=http://localhost:5000/auth/microsoft/callback
```

Use `consumers` for personal accounts only, `organizations` for organisational accounts only, or your tenant ID for a single tenant. The app registration's supported account types must match. Your organisation may require administrator consent. A Microsoft account also needs a provisioned Outlook/Exchange Online mailbox; an identity without mail cannot use Graph mail.

Sign in to CentroMail first, then choose **Connect Microsoft** in Integrations. This adds a mailbox to the current CentroMail user; it does not create a new CentroMail login. Graph saves sent messages automatically. Exchange on-premises without Graph can use **Custom / self-hosted IMAP** only if its administrator enables IMAP and an authentication method this password connector supports.

## IMAP/SMTP presets

All remote IMAP presets below use **993 / TLS**. SMTP **465 / TLS** and **587 / STARTTLS** are both encrypted, but must match the selected port. Proton Bridge uses its local ports instead. Regional, reseller, and legacy accounts may use different servers.

| Provider | IMAP server / port | SMTP server / port | SMTP security |
| --- | --- | --- | --- |
| Yahoo Mail | imap.mail.yahoo.com / 993 | smtp.mail.yahoo.com / 465 | TLS |
| iCloud Mail | imap.mail.me.com / 993 | smtp.mail.me.com / 587 | STARTTLS |
| AOL Mail | imap.aol.com / 993 | smtp.aol.com / 465 | TLS |
| Fastmail | imap.fastmail.com / 993 | smtp.fastmail.com / 465 | TLS |
| Zoho Mail | imap.zoho.com / 993 | smtp.zoho.com / 465 | TLS |
| GMX | imap.gmx.com / 993 | mail.gmx.com / 465 | TLS |
| Mail.com | imap.mail.com / 993 | smtp.mail.com / 465 | TLS |
| WEB.DE | imap.web.de / 993 | smtp.web.de / 465 | TLS |
| Yandex Mail | imap.yandex.com / 993 | smtp.yandex.com / 465 | TLS |
| QQ Mail | imap.qq.com / 993 | smtp.qq.com / 465 | TLS |
| NetEase 163 | imap.163.com / 993 | smtp.163.com / 465 | TLS |
| NetEase 126 | imap.126.com / 993 | smtp.126.com / 465 | TLS |
| Naver Mail | imap.naver.com / 993 | smtp.naver.com / 465 | TLS |
| Daum Mail | imap.daum.net / 993 | smtp.daum.net / 465 | TLS |
| Orange Mail | imap.orange.fr / 993 | smtp.orange.fr / 465 | TLS |
| Free.fr | imap.free.fr / 993 | smtp.free.fr / 465 | TLS |
| La Poste | imap.laposte.net / 993 | smtp.laposte.net / 465 | TLS |
| Posteo | posteo.de / 993 | posteo.de / 465 | TLS |
| Mailbox.org | imap.mailbox.org / 993 | smtp.mailbox.org / 465 | TLS |
| Runbox | mail.runbox.com / 993 | mail.runbox.com / 465 | TLS |
| StartMail | imap.startmail.com / 993 | smtp.startmail.com / 465 | TLS |
| Hushmail | imap.hushmail.com / 993 | smtp.hushmail.com / 465 | TLS |
| IONOS | imap.ionos.com / 993 | smtp.ionos.com / 465 | TLS |
| Namecheap Private Email | mail.privateemail.com / 993 | mail.privateemail.com / 465 | TLS |
| GoDaddy Professional Email | imap.secureserver.net / 993 | smtpout.secureserver.net / 465 | TLS |
| Titan Email | imap.titan.email / 993 | smtp.titan.email / 465 | TLS |
| Rackspace Email | secure.emailsrvr.com / 993 | secure.emailsrvr.com / 465 | TLS |
| OVH Mail | ssl0.ovh.net / 993 | ssl0.ovh.net / 465 | TLS |
| Google Workspace / Gmail IMAP | imap.gmail.com / 993 | smtp.gmail.com / 465 | TLS |
| Mail.ru | imap.mail.ru / 993 | smtp.mail.ru / 465 | TLS |
| Rambler Mail | imap.rambler.ru / 993 | smtp.rambler.ru / 465 | TLS |
| BT Mail | mail.btinternet.com / 993 | mail.btinternet.com / 465 | TLS |
| Sky Yahoo Mail | imap.tools.sky.com / 993 | smtp.tools.sky.com / 465 | TLS |
| TalkTalk Mail | mail.talktalk.net / 993 | smtp.talktalk.net / 465 | TLS |
| Virgin Media Mail | imap.virginmedia.com / 993 | smtp.virginmedia.com / 465 | TLS |
| Xfinity / Comcast | imap.comcast.net / 993 | smtp.comcast.net / 465 | TLS |
| AT&T Mail | imap.mail.att.net / 993 | smtp.mail.att.net / 465 | TLS |
| Telstra / BigPond | imap.telstra.com / 993 | smtp.telstra.com / 465 | TLS |
| Seznam Email | imap.seznam.cz / 993 | smtp.seznam.cz / 465 | TLS |
| Centrum.cz | imap.centrum.cz / 993 | smtp.centrum.cz / 465 | TLS |
| Onet Poczta | imap.poczta.onet.pl / 993 | smtp.poczta.onet.pl / 465 | TLS |
| WP Poczta | imap.wp.pl / 993 | smtp.wp.pl / 465 | TLS |
| Interia Poczta | poczta.interia.pl / 993 | poczta.interia.pl / 465 | TLS |
| T-Online | secureimap.t-online.de / 993 | securesmtp.t-online.de / 465 | TLS |
| STRATO Mail | imap.strato.de / 993 | smtp.strato.de / 465 | TLS |
| Aruba Mail | imaps.aruba.it / 993 | smtps.aruba.it / 465 | TLS |
| GMX Germany | imap.gmx.net / 993 | mail.gmx.net / 465 | TLS |
| Zoho Mail Europe | imap.zoho.eu / 993 | smtp.zoho.eu / 465 | TLS |
| Zoho Mail India | imap.zoho.in / 993 | smtp.zoho.in / 465 | TLS |
| Custom / self-hosted IMAP | Your server / 993 | Your server / 587 | STARTTLS |
| Proton Mail Bridge | 127.0.0.1 / 1143 | 127.0.0.1 / 1025 | STARTTLS |

### Provider requirements and exceptions

- **iCloud:** enable two-factor authentication and generate an app-specific password at [account.apple.com](https://account.apple.com/). Server logins can differ from your public alias; use the optional login fields if Apple's instructions require it.
- **Yahoo, AOL, Sky Yahoo, Mail.ru, Rambler:** create an app/client password if required. Yahoo/AOL may restrict app-password creation for new or managed accounts.
- **Fastmail, StartMail, Posteo, Mailbox.org, Runbox, Hushmail:** external mail-client access depends on the plan and security settings. Use a dedicated app/device password where offered. Fastmail plans without IMAP access cannot use this connection.
- **Zoho:** external IMAP access can require a paid plan or older eligible account. Pick the matching region, and use `imappro`/`smtppro` servers if your account's instructions specify them. An organisation may disable external clients.
- **GMX, Mail.com, WEB.DE:** enable external-client/IMAP access in web settings. Some regions or account tiers require a paid plan. GMX `.net` and `.com` settings differ.
- **Yandex:** enable IMAP and app passwords in the account's mail/security settings.
- **QQ and NetEase 163/126:** enable IMAP/SMTP and use the generated authorisation code as the password. Do not enter your usual website password. Some accounts require provider-specific client identification and may reject this generic connector; no such live exception has been verified here.
- **Naver and Daum:** enable IMAP/SMTP, and create an app password if two-step verification is enabled. Kakao-linked accounts can have different login requirements.
- **AT&T:** use an AT&T secure mail key when required; some legacy Yahoo-hosted addresses use different settings. **Xfinity/Comcast:** enable access through third-party email programs. **BT, TalkTalk, Virgin Media, Telstra:** use current client instructions for your specific legacy mailbox and subscription; providers may close or restrict old accounts.
- **T-Online:** create the separate password for external email programs. **Seznam, Centrum, Onet, WP, Interia:** enable external-client access and app passwords when required; paid access/security rules vary.
- **IONOS, STRATO, Aruba, Namecheap, Titan, Rackspace, OVH:** use the actual hosting product's servers. A reseller-branded Microsoft 365 account belongs under **Connect Microsoft**, not a legacy IMAP preset. GoDaddy's Microsoft 365 product also uses Microsoft OAuth.
- **Orange, Free.fr, La Poste:** follow current authentication rules and enable authenticated SMTP; a legacy mailbox or security restriction may require an app password or different login.

## Proton Mail Bridge

Proton's normal encrypted mailbox does not expose ordinary IMAP/SMTP. Install [Proton Mail Bridge](https://proton.me/mail/bridge), use an eligible paid plan, and keep Bridge running on the same machine as CentroMail.

1. Sign into Bridge and copy its generated IMAP/SMTP credentials. Use the **Bridge password**, not your Proton account password.
2. Choose the Proton Bridge preset and replace the hostnames, ports, login usernames, and security modes with those displayed by Bridge. Split-address mode may provide different logins.
3. Export Bridge's TLS certificate or trusted CA to a PEM file. Add its absolute path to `.env`:

```dotenv
CENTROMAIL_MAIL_CA_FILE=/absolute/path/to/proton-bridge-certificate.pem
```

4. Restart CentroMail. The mail hostname must match the certificate's names, and the certificate must be trusted and valid. This setting adds trust for the supplied certificate alongside the normal system certificate roots, so other email providers remain trusted. TLS verification stays enabled; certificate import does not bypass hostname checking.

If Bridge cannot supply a certificate compatible with verified TLS for its configured hostname, fix its certificate/hostname first. Bridge running on your Android phone is not supported; Android's browser can access CentroMail while Bridge runs on the computer hosting it.

## Other providers and self-hosted mail

Choose **Custom / self-hosted IMAP** for any standards-compatible server, including cPanel, Plesk, DirectAdmin, Dovecot/Postfix, Zimbra, mailcow, Mail-in-a-Box, Migadu, MXroute, Purelymail, hosted domains, institutional mail, or additional regional providers. Use the hosting company's documented hostname, credentials, and verified TLS settings. A custom CA can be provided with `CENTROMAIL_MAIL_CA_FILE`; restart after changing it.

**Tuta/Tutanota and HEY** do not expose a general-purpose IMAP mailbox or a compatible public mail-reading API. They cannot connect through this adapter. Sending-only services such as Amazon SES, SendGrid, Mailgun, and Brevo are not inbox providers and cannot pass the required IMAP check. Local Exchange EWS-only installations and providers requiring a separate OAuth mechanism need another adapter or enabled IMAP authentication. No unofficial scraping, password sharing with third parties, or false Connected state is used to claim support.

## Storage and troubleshooting

Mail passwords and OAuth refresh tokens are stored in the local `centro.db` database, not browser storage. They are currently not encrypted at rest; protect the machine and database backups, and use scoped app passwords. Disconnect removes that account's local credentials and cache; revoke the provider's app password/consent separately if desired. Appearance preference exports contain no account secrets.

The development network could not reach public SMTP on port 587. Verified port-465 TLS alternatives are now preset defaults where available. **iCloud still requires its documented SMTP port 587**, so permit that outbound port or use a network that allows it. Yandex, Mail.ru, Rambler, and the NetEase IMAP endpoints were also unavailable from this machine; consult the connectivity report and your regional provider settings.

A successful connection validates login, not every provider feature. Check IMAP enablement, app passwords, plan limits, regional hosts, TLS trust, and network reachability first. A timeout or blocked outbound port can require firewall/network changes. Folder names are discovered from the server; create/configure its standard Sent/Archive/Trash folders if missing. IMAP fallback moves hide only the selected originals and never expunge unrelated deleted mail; servers without UIDPLUS may retain hidden originals until another client cleans them up.

## WhatsApp webhook setup after the audit fixes

Inbound WhatsApp callbacks now require Meta's signed request header. Set `WHATSAPP_APP_SECRET` to the **Meta app secret** in `.env`, then restart. This is different from the access token and webhook verify token. Configure the public callback URL and GET verification token in Meta as before. An absent app secret returns 503; a missing or invalid signature returns 403.
