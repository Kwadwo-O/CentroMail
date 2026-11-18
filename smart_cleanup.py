import requests

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
MAX_PROMOTION_MESSAGES = 500


def scan_promotions(access_token, max_messages=MAX_PROMOTION_MESSAGES):
    if isinstance(max_messages, bool) or not isinstance(max_messages, int) or max_messages < 0:
        raise ValueError("max_messages must be a non-negative integer")
    if not access_token:
        raise ValueError("An access token is required")

    max_messages = min(max_messages, MAX_PROMOTION_MESSAGES)
    if max_messages == 0:
        return []

    headers = {"Authorization": f"Bearer {access_token}"}
    messages = []
    page_token = None

    while len(messages) < max_messages:
        params = {
            "q": (
                "category:promotions "
                "-in:trash -in:spam "
                "-is:starred -is:important"
            ),
            "maxResults": min(500, max_messages - len(messages)),
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            f"{GMAIL_BASE}/users/me/messages",
            headers=headers,
            params=params,
            timeout=(5, 20),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Gmail returned an invalid scan response")
        page_messages = data.get("messages", [])
        if not isinstance(page_messages, list):
            raise ValueError("Gmail returned an invalid message list")
        messages.extend(
            item for item in page_messages
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        messages = messages[:max_messages]
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return messages
