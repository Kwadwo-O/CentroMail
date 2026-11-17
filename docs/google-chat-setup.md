# Google Chat setup

CentroMail uses the same Google OAuth client, connected account, stored token and token refresh as Gmail. Chat uses Google's separate Chat API; Gmail permissions alone cannot access Chat messages.

## Connect

1. Open the Google Cloud project used for CentroMail's Gmail connection. Enable **Google Chat API** under **APIs & Services → Library**.
2. Open **Google Chat API → Configuration** and configure the app name, avatar and description. This integration uses user authentication; interaction handlers and a bot webhook are unnecessary. Save the configuration. See [Google's user authentication guide](https://developers.google.com/workspace/chat/authenticate-authorize-chat-user).
3. In **Google Auth Platform → Data Access**, add `chat.spaces`, `chat.messages` and `chat.memberships.readonly`. Keep the existing Gmail scopes and OAuth callback. For a testing OAuth app, add your account under Audience → Test users. A Workspace administrator may need to allow the app and these scopes.
4. In CentroMail, open **Inbox → Apps → Google Chat → Connect Google Chat** (also available in Integrations), choose your Gmail account and accept Chat permissions. Google Chat appears in Apps before connecting. Existing connections need to reconnect to grant the additional access.
5. Open **Inbox → Apps → Google Chat**. Disconnecting Chat removes its local configuration while retaining Gmail.

The API returns conversations accessible to the signed-in user. Account eligibility, organization policies and Google Chat availability still apply. If Google rejects the request, CentroMail displays the provider's permission/setup error.

## Supported actions

- Browse direct messages, group chats and named spaces, including older history and more conversations.
- Create direct messages, group chats or named spaces using participants' email addresses.
- Send text and attachments; reply with a quote and retain the thread in named spaces.
- Edit and delete your own messages, with an explicit option to also delete threaded replies.
- Add/remove emoji reactions, copy text, download Chat attachments or open Drive attachments through Google.
- Incoming messages, edits, deletions and reactions refresh every 10 seconds while visible. Changes to the last 50 loaded messages are checked; use Refresh for earlier history.

Messages have Google's 32,000-byte limit. CentroMail uploads/downloads files up to 64 MB; open Google Chat for larger files. Rich cards, calls and space administration remain in Google's app.

Drafts, reply targets and attachments survive conversation switching in the current page. An unchanged send retry reuses its request ID to prevent duplicate delivery. After an unconfirmed request, refresh to check delivery before retrying. Reloading the page clears drafts.

## Verification

Automated checks use disposable accounts and mocked Google responses for OAuth, shared token refresh, account isolation, history, retries, replies, ownership, reactions and attachments. Live delivery needs a configured Google Cloud project and a connected eligible Google account.
