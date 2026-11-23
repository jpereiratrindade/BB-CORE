# Instalação BB-CORE no Fedora Silverblue 44

## Instalar (terminal do HOST, sem sudo e fora de toolbox)

1. Monte o volume `labeco10T` e confirme que existe `/run/media/jpereiratrindade/labeco10T/dev/cpp/`.
2. Extraia `BB-CORE-Silverblue44-instalacao.zip` em `~/Downloads`.
3. Execute:

```bash
cd ~/Downloads/bb-core
bash scripts/install-silverblue.sh
```

O instalador recusa sobrescrever um diretório `bb-core` já existente. Se o ZIP for extraído diretamente no destino, execute o script de lá. Ele cria os tokens uma única vez, em `~/.config/bb-core/secret.env` (0600), e preserva tokens existentes. O banco fica em `~/.local/share/bb-core/bb.sqlite` (não no disco removível), para reduzir riscos de desconexão do volume durante gravações. O serviço depende do volume montado para acessar o código; **não remova/desmonte o volume enquanto o serviço estiver ativo**.

## Verificar

```bash
systemctl --user status bb-core.service --no-pager
journalctl --user -u bb-core.service -n 80 --no-pager
curl -I http://127.0.0.1:8789/
```

A página está em http://127.0.0.1:8789/ . O endpoint `/health` exige token Bearer. Para testar sem imprimir tokens:

```bash
python3 - <<'PY'
from pathlib import Path
import urllib.request, json
p=Path.home()/'.config/bb-core/secret.env'
t=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line)
r=urllib.request.Request('http://127.0.0.1:8789/health',headers={'Authorization':'Bearer '+t['BB_READ_TOKEN']})
with urllib.request.urlopen(r) as response:
    print(json.dumps(json.load(response),indent=2))
PY
```

## Operação

```bash
systemctl --user restart bb-core.service
systemctl --user stop bb-core.service
systemctl --user start bb-core.service
systemctl --user disable --now bb-core.service
```

O `disable --now` não apaga o banco. Para backup consistente, pare o serviço antes de copiar `~/.local/share/bb-core/` ou utilize a API de backup SQLite. **Não envie `secret.env` ao GitHub, ChatGPT ou colegas.**

## Limites atuais

- Funciona no host Fedora com Python 3.11+ e SQLite com FTS5; não é necessário `rpm-ostree install` nem Toolbox.
- A interface é local; MCP remoto para ChatGPT requer HTTPS e autenticação compatível, ainda não homologados.
- Não há ACL multiusuário/multissistema; tokens locais dão acesso ao acervo inteiro.
- O serviço `systemd --user` inicia quando a sessão do usuário e o volume estão disponíveis. Para inicialização sem login, há requisitos adicionais de montagem persistente e `loginctl enable-linger` que **não** são configurados automaticamente.
- O instalador não altera o NOESE, MÉTIS ou SisTer.
