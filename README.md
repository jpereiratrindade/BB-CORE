# BB-CORE DEV-REMOTE — Fedora Silverblue 44

## Instalação

Copie o conteúdo deste patch para o diretório do projeto BB-CORE. Verifique primeiro `command -v cloudflared`. Não substitui nem altera banco de dados, tokens ou `bb-core.service`.

```bash
cd /run/media/jpereiratrindade/labeco10T/dev/cpp/bb-core
bash scripts/install-devremote.sh
bash scripts/bb-remote.sh url
```

## Operação

```bash
bash scripts/bb-remote.sh status
bash scripts/bb-remote.sh logs
bash scripts/bb-remote.sh url
bash scripts/bb-remote.sh restart
bash scripts/bb-remote.sh stop
```

Serviços de usuário iniciam na sessão do usuário e persistem sem terminal aberto. **Não ativamos linger** por padrão: para operar antes do login, seria necessário `loginctl enable-linger`, além de garantir que o volume externo esteja montado; não recomendado neste MVP. O `ConditionPathIsDirectory` do serviço BB-CORE não assegura que o disco esteja montado; valide montagem antes de confiar na inicialização.

## Limites de segurança

Quick Tunnel publica HTTP inteiro do BB-CORE; não é um gateway restritivo de rotas nem provedor OAuth. Endereço público não é segredo. A autenticação por Bearer estático não garante compatibilidade com o cadastro do ChatGPT. **Não publique dados sensíveis nem conceda token de escrita a clientes externos até validar gateway, autenticação e autorização.** O túnel pode mudar de URL após reinício/reconexão. O comando `url` lê logs, não prova que a URL ainda esteja ativa. Para testar use curl autenticado, sem mostrar tokens. A recuperação automática é best effort, sem SLA.
