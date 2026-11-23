#!/usr/bin/env bash
set -Eeuo pipefail

# BB-CORE: instalação rootless no Fedora Silverblue 44.
# Não altera /usr, não usa rpm-ostree, não exige sudo.
PROJECT_ROOT="/run/media/jpereiratrindade/labeco10T/dev/cpp"
APP_DIR="$PROJECT_ROOT/bb-core"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CONFIG_DIR="$HOME/.config/bb-core"
DATA_DIR="$HOME/.local/share/bb-core"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/bb-core.service"
SECRET_FILE="$CONFIG_DIR/secret.env"
PYTHON="$(command -v python3 || true)"

fail() { echo "ERRO: $*" >&2; exit 1; }
[[ -n "$PYTHON" ]] || fail 'python3 não encontrado no host. Instale via toolbox ou disponibilize python3 no host.'
"$PYTHON" -c 'import sqlite3; assert sqlite3.sqlite_version_info >= (3, 35); import _sqlite3' || fail 'Python/SQLite indisponível'
[[ -d "$PROJECT_ROOT" ]] || fail "Volume não montado: $PROJECT_ROOT"
[[ -w "$PROJECT_ROOT" ]] || fail "Sem escrita no volume: $PROJECT_ROOT"
[[ -f "$SOURCE_DIR/bbcore/server.py" ]] || fail 'Pacote incompleto'
[[ "$(id -u)" -ne 0 ]] || fail 'Execute como usuário, nunca com sudo.'

if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  if [[ -e "$APP_DIR" ]]; then
    fail "Destino já existe: $APP_DIR. Não sobrescrevo código existente. Faça backup/merge manual."
  fi
  mkdir -p "$APP_DIR"
  cp -a "$SOURCE_DIR/." "$APP_DIR/"
fi

mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$UNIT_DIR"
chmod 700 "$CONFIG_DIR" "$DATA_DIR"
if [[ ! -e "$SECRET_FILE" ]]; then
  umask 077
  "$PYTHON" - "$SECRET_FILE" <<'PY'
import secrets, sys
from pathlib import Path
p = Path(sys.argv[1]); flags = 'x'
with p.open(flags, encoding='utf-8') as f:
    for k in ('BB_READ_TOKEN', 'BB_WRITE_TOKEN'):
        f.write(f'{k}={secrets.token_urlsafe(48)}\n')
PY
  echo 'Tokens gerados em arquivo privado.'
else
  echo 'Arquivo de tokens existente preservado.'
fi
chmod 600 "$SECRET_FILE"

# Serviço de usuário só depende do Python do HOST, não do toolbox.
# Proteções compatíveis com gravação SQLite em ~/.local/share.
cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=BB-CORE — memória contextual de insights (MCP local)
After=default.target
ConditionPathIsDirectory=$APP_DIR

[Service]
Type=simple
WorkingDirectory=$APP_DIR
Environment=PYTHONDONTWRITEBYTECODE=1
EnvironmentFile=$SECRET_FILE
ExecStart=$PYTHON -m bbcore.server --host 127.0.0.1 --port 8789 --db $DATA_DIR/bb.sqlite
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR
PrivateTmp=true

[Install]
WantedBy=default.target
UNIT

cd "$APP_DIR"
"$PYTHON" -m unittest discover -s tests -v || fail 'Testes falharam; serviço não será iniciado.'
if ! command -v systemctl >/dev/null 2>&1; then
  echo 'systemctl indisponível. Arquivos instalados; execute manualmente conforme README-SILVERBLUE.md.'
  exit 0
fi
if ! systemctl --user daemon-reload; then
  echo 'Gerenciador systemd de usuário indisponível nesta sessão. Use o host Fedora, não toolbox.'
  exit 0
fi
systemctl --user enable --now bb-core.service || fail 'Falha ao iniciar. Consulte: journalctl --user -u bb-core -n 80 --no-pager'
# Não imprimir tokens nem colocá-los nos argumentos dos processos.
"$PYTHON" - "$SECRET_FILE" <<'PY'
from pathlib import Path
import json,sys,time,urllib.request
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
vals=dict(line.strip().split('=',1) for line in Path(sys.argv[1]).read_text().splitlines() if '=' in line)
for _ in range(20):
    try:
        req=urllib.request.Request('http://127.0.0.1:8789/health',headers={'Authorization':'Bearer '+vals['BB_READ_TOKEN']})
        with opener.open(req,timeout=2) as r:
            result=json.load(r)
        if result.get('status')=='READY':
            print('HEALTH READY — BB-CORE em http://127.0.0.1:8789/')
            break
    except Exception:
        time.sleep(.5)
else:
    sys.exit('Serviço iniciado, mas health não confirmou READY; consulte journalctl --user -u bb-core')
PY
printf '\nInstalado em: %s\nDados em: %s\nTokens em: %s\n' "$APP_DIR" "$DATA_DIR" "$SECRET_FILE"
