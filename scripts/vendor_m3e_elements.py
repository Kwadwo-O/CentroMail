"""Copy the installed loading indicator, menus, tooltips and their dependencies for Flask."""
import json
import re
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
package = root / 'node_modules/@kyralabs/m3e-elements'
source = package / 'dist'
destination = root / 'static/vendor/m3e'
pending = [source / 'loading-indicator/index.js', source / 'menu/index.js', source / 'tooltip/index.js']
copied = set()
while pending:
    path = pending.pop().resolve()
    if path in copied:
        continue
    assert path.is_relative_to(source.resolve()) and path.is_file(), path
    target = destination / path.relative_to(source.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text()
    target.write_text(re.sub(r'^//# sourceMappingURL=.*$', '', text, flags=re.M).rstrip() + '\n')
    copied.add(path)
    pending.extend(path.parent / dependency for dependency in re.findall(r'(?:from\s*|import\s*)[\"\'](\.[^\"\']+)[\"\']', text))
for filename in ('LICENSE', 'NOTICE'):
    if (package / filename).exists():
        shutil.copyfile(package / filename, destination / filename)
(destination / 'VERSION').write_text(json.loads((package / 'package.json').read_text())['version'] + '\n')
assert (destination / 'loading-indicator/index.js').is_file()
assert (destination / 'menu/index.js').is_file()
assert (destination / 'tooltip/index.js').is_file()
tokens = root / 'node_modules/@kyralabs/m3e-tokens'
theme = (tokens / 'dist/theme.js').read_text()
assert not re.search(r'^import\s', theme, flags=re.M), 'Theme module must be self-contained.'
(destination / 'theme.js').write_text(re.sub(r'^//# sourceMappingURL=.*$', '', theme, flags=re.M).rstrip() + '\n')
if (tokens / 'NOTICE').exists():
    shutil.copyfile(tokens / 'NOTICE', destination / 'NOTICE.tokens')
print(f'Vendored {len(copied)} M3E component modules.')
