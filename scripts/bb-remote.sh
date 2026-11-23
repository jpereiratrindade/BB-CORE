#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-status}"
case "$cmd" in
  start) systemctl --user start bb-core.service bb-core-tunnel.service ;;
  stop) systemctl --user stop bb-core-tunnel.service ;;
  restart) systemctl --user restart bb-core-tunnel.service ;;
  status) systemctl --user --no-pager status bb-core.service bb-core-tunnel.service ;;
  logs) journalctl --user -u bb-core-tunnel.service -n 60 --no-pager ;;
  url)
    # Busca URL nos logs do boot atual, sem inventar endereço quando indisponível.
    url="$(journalctl --user -b -u bb-core-tunnel.service --no-pager -o cat 2>/dev/null | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
    if [[ -z "$url" ]]; then echo 'URL ainda não disponível; consulte logs.' >&2; exit 1; fi
    printf '%s/mcp\n' "$url"
    ;;
  *) echo 'Uso: bb-remote.sh {start|stop|restart|status|logs|url}' >&2; exit 2 ;;
esac
