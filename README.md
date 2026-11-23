# BB-CORE — memória investigativa local

Preserva documentos originais e registros intelectuais distintos — achados conceituais, decisões metodológicas, questões abertas e relatos empíricos — ligados por trechos verificáveis. Confirmação humana de um registro não constitui validação científica.

O insight possui identidade autônoma; compartilhar uma fonte não cria influência nem relações entre registros. A [continuidade orientada a eventos](docs/EVENTS.md) mantém acontecimentos, revisões e atribuições documentadas em um diário verificável, sem inventar trajetórias para o acervo anterior.

## Usar o acervo local

Abra http://127.0.0.1:8789/ no computador do serviço. A entrada mostra os cards do acervo. Selecionar um card abre uma janela de leitura exclusiva; Fechar ou Esc devolve à lista. A navegação separa Documentos, Receber documentos e a elaboração contextual de registros. A interface permite consultar registros, receber Markdown/TXT UTF-8 de até 256000 bytes, revisar metadados e confirmar a preservação. Depois, selecione trechos no documento original para elaborar registros com contexto e limitações. Não há extração por IA nesta etapa.

Os bytes ficam preservados por hash; recebimentos e procedências permanecem separados. Conteúdo divergente com o mesmo identificador e versão gera conflito preservado, sem substituição. Registros podem referenciar vários documentos e revisões criam novos registros ligados aos anteriores.

- [Contrato de ingestão, estados e limites](docs/DOCUMENT-INGESTION.md)
- [Processo local e registro MÉTIS](docs/LOCAL-PROCESS.md)
- [Plano de evolução](docs/PLAN.md)

O serviço instalado usa código em `~/.local/lib/bb-core` e banco privado em `~/.local/share/bb-core/bb.sqlite`. Para atualizar a execução a partir deste repositório: `bash scripts/install-local-runtime.sh`. O acesso à sessão local do computador permite recebimento e elaboração confirmados na interface. Tokens e banco ficam fora do Git.

## Verificar

```bash
python3 -m unittest discover -s tests -v
```

A conexão pública não é necessária para ingestão local. HTTPS e integração remota continuam pendentes.

## DEV-REMOTE — Fedora Silverblue 44

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
