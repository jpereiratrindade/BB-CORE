#!/usr/bin/env bash
set -Eeuo pipefail
APP=/run/media/jpereiratrindade/labeco10T/dev/cpp/bb-core
CFG="$HOME/.config/bb-core"
UNIT="$HOME/.config/systemd/user/bb-core.service"
[[ -f "$APP/bbcore/server.py" && -f "$UNIT" ]] || { echo 'Instale primeiro o BB-CORE v0.1.' >&2; exit 1; }
: "${BB_PUBLIC_URL:?Informe https://bb.seudominio.com}"
: "${BB_OAUTH_ISSUER:?Informe issuer HTTPS do IdP}"
: "${BB_OAUTH_JWKS_URL:?Informe JWKS HTTPS do IdP}"
[[ "$BB_PUBLIC_URL" == https://* && "$BB_OAUTH_ISSUER" == https://* && "$BB_OAUTH_JWKS_URL" == https://* ]] || { echo 'Somente HTTPS' >&2; exit 1; }
[[ "$BB_PUBLIC_URL" != *$'\n'* && "$BB_OAUTH_ISSUER" != *$'\n'* && "$BB_OAUTH_JWKS_URL" != *$'\n'* ]] || exit 1
python3 -m venv "$APP/.venv" || { echo 'python3 -m venv falhou; verifique python3-virtualenv no host.' >&2; exit 1; }
"$APP/.venv/bin/python" -m pip --version >/dev/null 2>&1 || { echo 'pip indisponível no venv. Configure pip sem alterar o Python do sistema.' >&2; exit 1; }
"$APP/.venv/bin/python" -m pip install 'PyJWT[crypto]>=2.9,<3' || exit 1
mkdir -p "$CFG"; chmod 700 "$CFG"
umask 077
printf 'BB_OAUTH_ISSUER=%s\nBB_OAUTH_JWKS_URL=%s\nBB_OAUTH_RESOURCE=%s\n' "${BB_OAUTH_ISSUER%/}" "$BB_OAUTH_JWKS_URL" "${BB_PUBLIC_URL%/}" > "$CFG/oauth.env"
chmod 600 "$CFG/oauth.env"
mkdir -p "$HOME/.config/systemd/user/bb-core.service.d"
cat > "$HOME/.config/systemd/user/bb-core.service.d/20-oauth.conf" <<OVERRIDE
[Service]
EnvironmentFile=$CFG/oauth.env
ExecStart=
ExecStart=$APP/.venv/bin/python -m bbcore.server --host 127.0.0.1 --port 8789 --db $HOME/.local/share/bb-core/bb.sqlite
OVERRIDE
systemctl --user daemon-reload
systemctl --user restart bb-core.service
systemctl --user --no-pager --full status bb-core.service
printf '\nOAuth ativado. Publique SOMENTE /mcp e /.well-known/oauth-protected-resource pelo proxy.\n'
