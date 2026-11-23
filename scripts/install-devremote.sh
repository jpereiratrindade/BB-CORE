#!/usr/bin/env bash
set -euo pipefail
if ! command -v cloudflared >/dev/null 2>&1; then
  echo 'ERRO: cloudflared ausente. Instale-o a partir da distribuição oficial antes de continuar.' >&2
  exit 1
fi
if ! systemctl --user cat bb-core.service >/dev/null 2>&1; then
  echo 'ERRO: bb-core.service não existe. Instale o BB-CORE primeiro.' >&2
  exit 1
fi
install -d -m 700 "$HOME/.local/bin" "$HOME/.config/systemd/user"
cat > "$HOME/.local/bin/bb-core-tunnel-run" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
# URL e tokens não devem ser enviados por argumentos para o túnel.
exec cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8789
RUN
chmod 700 "$HOME/.local/bin/bb-core-tunnel-run"
install -m 600 "$(dirname "$0")/../deploy/bb-core-tunnel.service" "$HOME/.config/systemd/user/bb-core-tunnel.service"
systemctl --user daemon-reload
systemctl --user enable --now bb-core-tunnel.service
printf '\nTúnel iniciado. Para ver URL: bash scripts/bb-remote.sh url\n'
printf 'Aviso: túnel expõe o servidor HTTP inteiro; não use dados sensíveis neste experimento.\n'
