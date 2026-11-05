#!/usr/bin/env bash
# mac-control 引擎安装/修复：装 Peekaboo 到稳定路径并检查权限
set -euo pipefail
VER="${1:-4.9.7}"
DEST="$HOME/.local/share/mac-control/peekaboo-$VER"
BIN="$HOME/.local/bin/peekaboo"
REG="${NPM_REGISTRY:-https://registry.npmmirror.com}"

mkdir -p "$HOME/.local/share/mac-control" "$HOME/.local/bin"
if [ -x "$DEST/peekaboo" ]; then
  echo "already installed: $DEST"
else
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  ( cd "$TMP" && npm install --silent --no-audit --no-fund --registry="$REG" "@steipete/peekaboo@$VER" )
  cp -R "$TMP/node_modules/@steipete/peekaboo" "$DEST"
  chmod +x "$DEST/peekaboo"
  xattr -d com.apple.quarantine "$DEST/peekaboo" 2>/dev/null || true
  echo "installed: $DEST"
fi
ln -sf "$DEST/peekaboo" "$BIN"
"$BIN" --version
"$BIN" permissions status || true
