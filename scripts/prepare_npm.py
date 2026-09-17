"""Assemble the npm distribution from the already-built matching Python wheel."""

import json
from pathlib import Path
import shutil
import tomllib

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
package = root / "distributions/npm"
metadata = json.loads((package / "package.json").read_text())
if metadata["version"] != version:
    raise SystemExit("Python/npm versions differ")
wheel = root / "dist" / f"palgwae-{version}-py3-none-any.whl"
if not wheel.is_file():
    raise SystemExit("Build the Python wheel before assembling npm")
vendor = package / "vendor"
vendor.mkdir(exist_ok=True)
for old in vendor.glob("*.whl"):
    if old.name != wheel.name:
        raise SystemExit("Stale wheel in npm vendor directory; use a fresh checkout")
shutil.copy2(wheel, vendor / wheel.name)
shutil.copy2(root / "LICENSE", package / "LICENSE")
print(f"Prepared npm package with {wheel.name}")
