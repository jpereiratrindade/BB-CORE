#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RUNTIME_DIR="$HOME/.local/lib/bb-core"
DROPIN_DIR="$HOME/.config/systemd/user/bb-core.service.d"
systemctl --user cat bb-core.service >/dev/null
mkdir -p "$RUNTIME_DIR/bbcore" "$RUNTIME_DIR/web" "$DROPIN_DIR"
cp "$SOURCE_DIR"/bbcore/*.py "$RUNTIME_DIR/bbcore/"
cp "$SOURCE_DIR"/web/index.html "$SOURCE_DIR"/web/style.css "$SOURCE_DIR"/web/app.js "$SOURCE_DIR"/web/documents.js "$SOURCE_DIR"/web/mesa.js "$SOURCE_DIR"/web/navigation.js "$SOURCE_DIR"/web/trajectory.js "$SOURCE_DIR"/web/favicon.svg "$RUNTIME_DIR/web/"
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

# systemd pode estar ativo antes de o socket HTTP estar pronto.
/usr/bin/python3 - <<'PYTHON'
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request, build_opener, ProxyHandler
config = dict(line.split('=', 1) for line in (Path.home()/'.config/bb-core/secret.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
opener = build_opener(ProxyHandler({}))
for attempt in range(25):
    try:
        request = Request('http://127.0.0.1:8789/health', headers={'Authorization': 'Bearer '+config['BB_READ_TOKEN']})
        with opener.open(request, timeout=2) as response:
            result = json.load(response)
        if result.get('status') == 'READY' and result.get('storage', {}).get('integrity') == 'VERIFIED':
            print('HEALTH READY; integridade verificada')
            break
    except (URLError, OSError):
        pass
    time.sleep(.2)
else:
    raise SystemExit('Serviço não confirmou disponibilidade e integridade; consulte journalctl --user -u bb-core')
PYTHON
