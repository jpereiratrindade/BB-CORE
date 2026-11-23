#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RUNTIME_DIR="$HOME/.local/lib/bb-core"
DROPIN_DIR="$HOME/.config/systemd/user/bb-core.service.d"
systemctl --user cat bb-core.service >/dev/null
mkdir -p "$RUNTIME_DIR/bbcore" "$RUNTIME_DIR/web" "$DROPIN_DIR"
cp "$SOURCE_DIR"/bbcore/*.py "$RUNTIME_DIR/bbcore/"
cp "$SOURCE_DIR/web/index.html" "$RUNTIME_DIR/web/"
cat > "$DROPIN_DIR/local-runtime.conf" <<EOF
[Unit]
ConditionPathIsDirectory=
ConditionPathIsDirectory=$RUNTIME_DIR
After=

[Service]
WorkingDirectory=$RUNTIME_DIR
ExecStart=
ExecStart=/usr/bin/python3 -m bbcore.server --host 127.0.0.1 --port 8789 --db $HOME/.local/share/bb-core/bb.sqlite
EOF
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable bb-core.service
systemctl --user restart bb-core.service
systemctl --user is-active bb-core.service
