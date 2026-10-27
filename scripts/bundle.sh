#!/bin/zsh
# Builds Fastype.app and installs it into ~/Applications.
set -euo pipefail
cd "$(dirname "$0")/.."

LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

[[ -f assets/Fastype.icns ]] || .venv/bin/python scripts/make_icon.py
.venv/bin/pyinstaller --noconfirm --clean --log-level WARN \
  --distpath build/dist --workpath build/work Fastype.spec

mkdir -p ~/Applications
rm -rf ~/Applications/Fastype.app
# Move rather than copy, and make macOS forget the build location: otherwise the copy left
# in build/dist shows up as a second Fastype in Spotlight and the Apps launcher.
mv build/dist/Fastype.app ~/Applications/
"$LSREGISTER" -u "$PWD/build/dist/Fastype.app" 2>/dev/null || true
"$LSREGISTER" -f ~/Applications/Fastype.app
echo "Installed ~/Applications/Fastype.app"
