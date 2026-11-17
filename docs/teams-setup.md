# Microsoft Teams

Teams connects to an existing CentroMail account through Microsoft Graph OAuth. Use a Microsoft **work or school account**. Personal Teams accounts are not supported by these Graph endpoints.

In Microsoft Entra, use the same application registration and client secret as Outlook, or create a web application registration. Add this **Web** redirect URI:

```text
http://localhost:5000/auth/teams/callback
```

Set these values in the local `.env` file, then restart CentroMail:

```text
MICROSOFT_CLIENT_ID=your-application-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret-value
MICROSOFT_TENANT=organizations
MICROSOFT_TEAMS_REDIRECT_URI=http://localhost:5000/auth/teams/callback
```

An existing `common` tenant setting also works for work or school accounts. Keep the browser and redirect URI on the same hostname and port. Teams has its own callback; keep the existing Outlook redirect URI registered too.

Add these Microsoft Graph **delegated** permissions:

| Permission | Used for |
| --- | --- |
| `User.Read` | Account identity |
| `offline_access` | Refreshing access after sign-in |
| `Chat.Read` | Your chat list and messages |
| `ChatMessage.Send` | Sending to an existing chat |
| `Team.ReadBasic.All` | Your joined teams |
| `Channel.ReadBasic.All` | Channels in a selected team |
| `ChannelMessage.Read.All` | Channel posts and thread replies |
| `ChannelMessage.Send` | Channel posts and replies |

Your organisation may require administrator consent, especially for channel history. Approve the requested delegated permissions according to its policy. CentroMail does not request mail permissions when connecting Teams.

Open **Integrations → Microsoft Teams → Connect Microsoft Teams**, sign in and consent. Then open **Inbox → Apps → Microsoft Teams**. Choose **Chats** or **Team channels**, select a team and conversation, and use **Refresh** to check for updates. More teams, conversations, messages and replies load on request.

Channel replies load when you expand **View replies**. **Reply in thread** targets that post; **Back to channel** returns to a new channel post. Attachment names are shown, with **Open in Teams** when Microsoft supplies a link. Attachment downloads, creating chats, calling, meetings and automatic Teams polling are not implemented.

Failed sends keep the draft for the current page. A timeout cannot establish whether Microsoft accepted the message: check Teams before retrying. Teams tokens stay in the application database. Disconnecting Teams removes its local connection and leaves Outlook connected; revoke application consent in Microsoft separately if needed.
