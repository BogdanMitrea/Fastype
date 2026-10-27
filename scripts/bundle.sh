#!/bin/zsh
# Builds Fastype.app and installs it into ~/Applications.
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f assets/Fastype.icns ]] || .venv/bin/python scripts/make_icon.py
.venv/bin/pyinstaller --noconfirm --clean --log-level WARN \
  --distpath build/dist --workpath build/work Fastype.spec

mkdir -p ~/Applications
rm -rf ~/Applications/Fastype.app
cp -R build/dist/Fastype.app ~/Applications/
echo "Installed ~/Applications/Fastype.app"
