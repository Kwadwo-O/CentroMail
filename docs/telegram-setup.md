# Telegram setup and chat support

CentroMail connects your Telegram account using the official Telegram client API through Telethon. Your account session stays on the CentroMail server; it is never sent to the browser.

## Connect your account

1. Install the Python requirements, including `telethon>=1.45,<2`.
2. Sign in to [my.telegram.org/apps](https://my.telegram.org/apps) and create an API application. Copy its API ID and API hash.
3. Sign in to CentroMail, open **Integrations → Telegram**, and enter the API ID, API hash, and your phone number in international format.
4. Enter the login code Telegram sends you. If two-step verification is enabled, enter its password in the next step.
5. Open **Inbox → Apps → Telegram** and choose a conversation. No bot token or webhook is required for this account connection.

Keep the API hash and saved Telegram session private. A saved session grants access to your Telegram account. Use Disconnect in Integrations to remove the local connection and attempt to log out its Telegram session.

## Chats, groups and topics

| Conversation | Reading and sending |
| --- | --- |
| Private chat | Read history and send text to that conversation. |
| Standard group, topics disabled | One shared history and a single message composer. |
| Forum group, topics enabled | Choose a topic/sub-channel before sending. History and sends stay in that topic. |
| General topic | Shown separately; messages from other topics are excluded. Sends use Telegram's normal General-topic behavior. |
| Closed or hidden topic | Read-only in CentroMail. |
| Broadcast channel | Sending is available only when the account has permission to post. |

The view lists your 50 most recent Telegram conversations. It loads 50 history messages at a time; **Load older messages** retrieves the preceding batch. Forum topic discovery returns up to 100 topics at a time. **Find topics** searches names on Telegram, including topics outside the initial list. Creating, renaming, closing or deleting topics remains available in Telegram's own apps.

## Sending, receiving and pictures

- **Send message** sends plain text, including emoji and line breaks. Telegram limits a message to 4,096 UTF-16 code units; some emoji use two units. Ctrl/Command + Enter sends; Enter adds a line break.
- Incoming messages are checked every 10 seconds while the selected chat is visible. Polling pauses when you open the Email tab, choose another integration, or hide the browser tab. This is periodic refresh, rather than a persistent push connection. Use **Refresh** to reload conversations and the current history.
- Failed or unconfirmed sends keep the draft in the current page. Retrying an unchanged draft reuses Telegram's message identifier to prevent duplicates. Refresh the conversation to check delivery before retrying an unconfirmed send. Drafts survive chat/topic switching within the page; a browser reload clears them.
- Conversation, group and account profile pictures load from Telegram as they become visible. Telegram's privacy settings apply. Initials remain when a picture is missing or unavailable. Browser photo copies remain in memory for the current page.
- Media and service messages currently show a text placeholder. File uploads, media downloads, reactions, voice messages and Secret Chats are not implemented.

## Verification

Local tests simulate the Telegram client to check account isolation, topic routing, permissions, request validation, retry identifiers and picture responses. Browser checks cover sending, incoming polling, draft retention, topic selection and mobile layouts. Live Telegram delivery and real-device behavior require a connected account and network access to Telegram.

Topic routing follows [Telegram's official forum API](https://core.telegram.org/api/forum): General has ID 1; other topic messages reply to their topic's root message.
