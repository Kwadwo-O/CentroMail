"""Rebuild component tokens from the installed M3E package (npm install first)."""

import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
package = root / "node_modules/@kyralabs/m3e-tokens"
version = json.loads((package / "package.json").read_text())["version"]
sources = sorted((package / "dist/generated/components").glob("*.css"))
if not sources:
    raise SystemExit("No M3E component tokens found. Run npm install first.")
header = f"/* M3E {version} component tokens, vendored from @kyralabs/m3e-tokens (Apache-2.0). */\n"
(root / "static/css/m3e-component-tokens.css").write_text(
    header + "".join(source.read_text() + "\n" for source in sources)
)
