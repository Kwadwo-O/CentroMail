"""Choose sender logos from the From address without making network requests."""

import re
from email.utils import parseaddr


_BRAND_LOGOS = {
    'amazon.co.uk': 'images/senders/amazon.ico',
    'amazon.com': 'images/senders/amazon.ico',
    'amazon.de': 'images/senders/amazon.ico',
    'amazon.fr': 'images/senders/amazon.ico',
    'amazon.it': 'images/senders/amazon.ico',
    'amazon.es': 'images/senders/amazon.ico',
    'amazon.ca': 'images/senders/amazon.ico',
    'amazon.com.au': 'images/senders/amazon.ico',
    'amazon.in': 'images/senders/amazon.ico',
    'amazon.co.jp': 'images/senders/amazon.ico',
    'github.com': 'images/senders/github.png',
    'studysmarter.co.uk': 'images/senders/studysmarter.svg',
    'studysmarter.de': 'images/senders/studysmarter.svg',
    'linkedin.com': 'images/senders/linkedin.png',
    'facebook.com': 'images/integrations/facebook.svg',
    'instagram.com': 'images/integrations/instagram.svg',
    'x.com': 'images/integrations/x.svg',
    'twitter.com': 'images/integrations/x.svg',
    'threads.net': 'images/integrations/threads.svg',
    'threads.com': 'images/integrations/threads.svg',
    'reddit.com': 'images/integrations/reddit.svg',
    'slack.com': 'images/integrations/slack.svg',
    'discord.com': 'images/integrations/discord.svg',
    'pinterest.com': 'images/integrations/pinterest.svg',
    'tiktok.com': 'images/integrations/tiktok.svg',
    'twitch.tv': 'images/integrations/twitch.svg',
    'tumblr.com': 'images/integrations/tumblr.svg',
    'whatsapp.com': 'images/integrations/whatsapp.svg',
    'telegram.org': 'images/integrations/telegram.svg',
    'bsky.app': 'images/integrations/bluesky.svg',
    'mastodon.social': 'images/integrations/mastodon.svg',
    'google.com': 'images/Google_Favicon_2025.svg.webp',
    'microsoft.com': 'images/Microsoft_Favicon_2025.webp',
}

# Provider domains identify a person's mailbox, rather than the sender's brand.
_PERSONAL_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com',
    'outlook.com', 'hotmail.com', 'hotmail.co.uk', 'hotmail.fr', 'hotmail.de',
    'outlook.co.uk', 'outlook.fr', 'outlook.de', 'live.com', 'live.co.uk',
    'live.fr', 'live.de', 'msn.com',
    'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in', 'yahoo.in', 'yahoo.ca',
    'yahoo.com.au', 'yahoo.co.jp', 'yahoo.fr', 'yahoo.de', 'yahoo.it',
    'yahoo.es', 'yahoo.com.br', 'ymail.com', 'rocketmail.com',
    'icloud.com', 'me.com', 'mac.com', 'aol.com', 'aim.com',
    'proton.me', 'protonmail.com', 'pm.me', 'tuta.com', 'tutanota.com',
    'gmx.com', 'gmx.net', 'gmx.de', 'mail.com', 'fastmail.com', 'fastmail.fm',
    'hey.com', 'zoho.com',
})
_NONPUBLIC_DOMAINS = frozenset({
    'example.com', 'example.net', 'example.org',
    'example', 'invalid', 'test', 'localhost', 'local', 'localdomain',
    'internal', 'intranet', 'lan', 'home', 'corp', 'private', 'onion', 'alt', 'arpa',
})
_DNS_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


def _within(domain, root):
    return domain == root or domain.endswith('.' + root)


def sender_logo_source(value):
    """Return a local static filename or ``None`` for the initials fallback.

    Known brands use bundled images. Personal, unknown, and nonpublic addresses
    keep the initials fallback; display names never select a logo. No sender
    information is included in external URLs.
    """
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        return None
    try:
        address = parseaddr(value)[1]
        if address.count('@') != 1:
            return None
        local, domain = address.rsplit('@', 1)
        if not local:
            return None
        domain = domain.removesuffix('.').encode('idna').decode('ascii').lower()
    except (TypeError, ValueError, UnicodeError):
        return None

    labels = domain.split('.')
    if (len(domain) > 253 or len(labels) < 2
            or not all(_DNS_LABEL.fullmatch(label) for label in labels)
            or not re.fullmatch(r'[a-z]{2,}|xn--[a-z0-9-]+', labels[-1])):
        return None
    if any(_within(domain, root) for root in _NONPUBLIC_DOMAINS | _PERSONAL_DOMAINS):
        return None
    for root, logo in _BRAND_LOGOS.items():
        if _within(domain, root):
            return logo
    return None
