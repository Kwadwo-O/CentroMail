# Connecting apps to CentroMail

Open **Integrations**, search for an app, and choose **Connect** or **Set up**.
Each app shows its connection method, current capabilities, and a setup guide.
Connected apps have a **Manage** action. Email accounts open in Inbox; supported
messaging conversations open in **Inbox → Apps**.

**Check connection** only checks account/API access. It does not send messages
or publish posts, and does not guarantee every permission or webhook is working.
Posting and sending actions are explicitly labelled and require message text.
Credentials are saved in the database on the server running CentroMail; they are
not mirrored into browser storage.

## Browser OAuth sign-in provided by CentroMail

| App | What the app owner must configure | What the person connecting does |
| --- | --- | --- |
| Gmail | Google Cloud web OAuth client; `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; enable Gmail API; consent screen and test users or verification as appropriate. | Sign in with Google and grant Gmail access. |
| Google Chat | Same Google client as Gmail; enable/configure Google Chat API and grant the extra Chat scopes. Workspace policy may require admin approval. | Connect/reconnect Google Chat and grant Chat access. |
| Outlook | Microsoft Entra web app; `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`; delegated `User.Read`, `Mail.ReadWrite`, `Mail.Send`, `offline_access`. Select supported account types for your users. | Sign in with Microsoft; an organisation may require admin consent. |
| Teams | Same Microsoft client as Outlook, a separate Teams callback, and delegated Chat/Team/Channel permissions. Use a work/school account with Teams access. | Sign in separately for Teams; request admin consent when required. |

The app dialogs show **Setup required** when client credentials are missing.
Configured credentials alone cannot verify provider API activation, consent,
client validity, or administrator approval.

Register the exact callback URL shown in each dialog. Local defaults are:

- Google (Gmail and Chat): `http://localhost:5000/auth/google/callback`
- Outlook: `http://localhost:5000/auth/microsoft/callback`
- Teams: `http://localhost:5000/auth/teams/callback`

Use the same hostname in the browser and registration (`localhost` and
`127.0.0.1` are different). Override callbacks with `GOOGLE_REDIRECT_URI`,
`MICROSOFT_REDIRECT_URI`, and `MICROSOFT_TEAMS_REDIRECT_URI` when needed. Restart
CentroMail after editing `.env`. Use HTTPS for a deployed server.

See [Google Chat setup](google-chat-setup.md), [Teams setup](teams-setup.md),
and [email provider setup](email-provider-setup.md) for full permissions.

## Tokens, bots, and app passwords

Telegram, other email, Discord, WhatsApp Business, Slack, Mastodon, and Bluesky
keep their guided connection forms. They use their existing bot, instance-token,
or app-password workflows.

| App | Authentication and setup | Implemented features |
| --- | --- | --- |
| Telegram | Your API ID/hash from [my.telegram.org/apps](https://my.telegram.org/apps), phone, login code, optional 2FA password. Uses Telethon account authorization, not OAuth or a bot token. | Chats, messages, files, replies, reactions, and own-message actions in Apps. |
| Other email | Provider IMAP/SMTP settings, email, and an app password where required. Enable IMAP. Proton Mail needs Bridge and its trusted certificate. | Email inbox, reading, sending, and supported mailbox actions. |
| Discord | [Developer app and bot](https://docs.discord.com/developers/topics/oauth2); invite with the OAuth2 bot installation flow; View Channel, Read Message History, Send Messages; Message Content access when needed; bot token and channel ID. | Read a channel and send as the bot. Personal account automation is unsupported. |
| WhatsApp Business | [Meta Business Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started); phone number ID and access token with `whatsapp_business_messaging`/`whatsapp_business_management`. Set `WHATSAPP_APP_SECRET`; register a public HTTPS webhook with the shown verify token and subscribe to messages. | Receive webhook messages; send text during the customer service window. Personal WhatsApp is unsupported. Temporary dashboard tokens expire. |
| Slack | [Create/install a Slack app through OAuth](https://docs.slack.dev/authentication/installing-with-oauth); `chat:write` bot scope; invite bot to channel; paste `xoxb` token and channel ID. Admin approval may be required. | Workspace check and sending text to the configured channel. Channel history is not implemented. |
| Mastodon | Preferences → Development on your instance; [create an application/token](https://docs.joinmastodon.org/client/token/) with `read:accounts`, `write:statuses`; instance domain. Supports OAuth; this UI accepts an instance-issued token. | Profile check and text statuses. |
| Bluesky | Handle and [app password](https://bsky.app/settings/app-passwords). Bluesky supports OAuth, but this integration uses an app-password session at `bsky.social`. | Profile connection and text posting. |

## Coming soon: deferred OAuth apps

X (Twitter), Reddit, LinkedIn, TikTok, Pinterest, Tumblr, and Twitch are
placeholders until the hosted domain and provider application setup are ready.
Their cards show **Coming soon**. Connection forms, connection checks, and
posting endpoints are disabled; existing saved credentials are retained.
There is no setup to complete for these apps now.

The requirements below are a reference for enabling them later. These features
are unavailable while the apps are placeholders.

| App | Future authentication and setup | Existing implementation to revisit |
| --- | --- | --- |
| X | [OAuth 2.0 user authorization with PKCE](https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code); `tweet.read`, `users.read`, `tweet.write`; appropriate developer/API access, possibly paid. | Profile check and text posting. |
| LinkedIn | Developer app with OIDC Sign In product and [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin); `openid`, `profile`, `w_member_social`; user OAuth token. | Member profile check and text posting. |
| Reddit | Register an app and confirm access under the [current Data API policy](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Reddit-Data-API-Wiki); user OAuth token with `identity`. | Profile check. Post browsing/publishing is not implemented. |
| TikTok | Developer app with Login Kit and [basic profile access](https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info/); `user.info.basic` OAuth token. | Basic profile check. Videos and publishing are not implemented. |
| Pinterest | Developer app with approved [trial or production API access](https://developers.pinterest.com/docs/getting-started/authentication/); `user_accounts:read` OAuth token. Trial test tokens can expire after 24 hours. | Profile check. Boards and Pins are not implemented. |
| Tumblr | [Register an app](https://www.tumblr.com/docs/en/api/v2); OAuth 2.0 user token with `basic`. | Profile check and blog count. Post browsing/publishing is not implemented. |
| Twitch | [Register an app and obtain a user OAuth token](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/); paste the matching client ID. | Channel profile check. Live chat and stream controls are not implemented. |

Provider access policies and approval requirements can change. The official
setup link in each app dialog is the reference for current requirements.
