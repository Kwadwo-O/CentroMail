"""Open CentroMail in a dedicated Firefox profile for this local network."""

import subprocess
from pathlib import Path


profile = Path(__file__).resolve().parents[1] / 'instance' / 'browser-profile'
profile.mkdir(parents=True, mode=0o700, exist_ok=True)
profile.chmod(0o700)
(profile / 'user.js').write_text(
    '// Google connections stall over IPv6 on this network.\n'
    '// These settings apply only to this dedicated CentroMail browser profile.\n'
    'user_pref("network.dns.disableIPv6", true);\n'
    'user_pref("network.http.http3.enable", false);\n'
    'user_pref("browser.shell.checkDefaultBrowser", false);\n',
    encoding='utf-8',
)
print('Opening CentroMail at http://localhost:5000 in its dedicated Firefox profile.', flush=True)
subprocess.run(
    ['firefox', '--no-remote', '--new-instance', '--profile', str(profile), '--new-window', 'http://localhost:5000'],
    check=True,
)
