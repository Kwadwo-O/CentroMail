# Public email transport checks

Checked 2026-11-16 from the development machine. These are anonymous TLS/STARTTLS handshakes only: no login, credentials, email reads, or sends. A successful handshake confirms encryption and hostname trust from this network; it does not confirm account eligibility or server login. An unavailable result may be a firewall, DNS, regional setting, or provider restriction. Proton Bridge and custom servers require your local configuration and were skipped.

First pass: 66 of 98 distinct public endpoints completed verified TLS handshakes. After trying 24 alternate SMTP endpoints, 89 of the 98 endpoints used by the current presets completed verified TLS. A total of 122 distinct endpoints were attempted.

| Preset | IMAP | SMTP |
| --- | --- | --- |
| Yahoo Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| iCloud Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| AOL Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Fastmail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Zoho Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| GMX | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Mail.com | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| WEB.DE | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Yandex Mail | Unavailable or timed out from this machine | Unavailable or timed out from this machine |
| QQ Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| NetEase 163 | Unavailable or timed out from this machine | TLS verified (TLSv1.3) |
| NetEase 126 | Unavailable or timed out from this machine | TLS verified (TLSv1.3) |
| Naver Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Daum Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Orange Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Free.fr | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| La Poste | TLS verified (TLSv1.2) | Unavailable or timed out from this machine |
| Posteo | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Mailbox.org | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Runbox | TLS verified (TLSv1.2) | Unavailable or timed out from this machine |
| StartMail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Hushmail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| IONOS | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Namecheap Private Email | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| GoDaddy Professional Email | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Titan Email | TLS verified (TLSv1.2) | Unavailable or timed out from this machine |
| Rackspace Email | TLS verified (TLSv1.2) | TLS verified (TLSv1.2) |
| OVH Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Google Workspace / Gmail IMAP | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Mail.ru | Unavailable or timed out from this machine | Unavailable or timed out from this machine |
| Rambler Mail | Unavailable or timed out from this machine | Unavailable or timed out from this machine |
| BT Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Sky Yahoo Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| TalkTalk Mail | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Virgin Media Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Xfinity / Comcast | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| AT&T Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Telstra / BigPond | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Seznam Email | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Centrum.cz | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Onet Poczta | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| WP Poczta | TLS verified (TLSv1.2) | TLS verified (TLSv1.3) |
| Interia Poczta | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| T-Online | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| STRATO Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| Aruba Mail | TLS verified (TLSv1.3) | TLS verified (TLSv1.3) |
| GMX Germany | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Zoho Mail Europe | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |
| Zoho Mail India | TLS verified (TLSv1.3) | Unavailable or timed out from this machine |

## Alternate SMTP TLS checks

The initial STARTTLS endpoints on port 587 were unavailable from this network. The following checks try implicit TLS on port 465; they do not test login. Verified alternatives are used as preset defaults. Providers without a verified alternative retain their documented STARTTLS default.

| SMTP server | TLS on port 465 |
| --- | --- |
| smtp.mail.yahoo.com | TLS verified (TLSv1.3) |
| smtp.mail.me.com | Unavailable or timed out from this machine |
| smtp.aol.com | TLS verified (TLSv1.3) |
| smtp.fastmail.com | TLS verified (TLSv1.3) |
| smtp.zoho.com | TLS verified (TLSv1.3) |
| mail.gmx.com | TLS verified (TLSv1.3) |
| smtp.mail.com | TLS verified (TLSv1.3) |
| smtp.web.de | TLS verified (TLSv1.3) |
| smtp.orange.fr | TLS verified (TLSv1.3) |
| smtp.free.fr | TLS verified (TLSv1.3) |
| smtp.laposte.net | TLS verified (TLSv1.3) |
| posteo.de | TLS verified (TLSv1.3) |
| smtp.mailbox.org | TLS verified (TLSv1.3) |
| mail.runbox.com | TLS verified (TLSv1.2) |
| smtp.ionos.com | TLS verified (TLSv1.3) |
| mail.privateemail.com | TLS verified (TLSv1.3) |
| smtp.titan.email | TLS verified (TLSv1.2) |
| ssl0.ovh.net | TLS verified (TLSv1.3) |
| smtp.gmail.com | TLS verified (TLSv1.3) |
| smtp.talktalk.net | TLS verified (TLSv1.3) |
| smtp.comcast.net | TLS verified (TLSv1.3) |
| mail.gmx.net | TLS verified (TLSv1.3) |
| smtp.zoho.eu | TLS verified (TLSv1.3) |
| smtp.zoho.in | TLS verified (TLSv1.3) |
