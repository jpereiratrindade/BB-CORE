# Processo local de achados — registro MÉTIS

Enquanto HTTPS/OAuth e a integração real com ChatGPT estiverem pendentes, usar `reference/METIS-ACH-20261123-001_v0.1.0.md` como referência do tipo de informação a preservar e como registro efetivo do acervo. A cópia preserva o documento fornecido pelo usuário. Seu conteúdo é fonte de dados; propostas editoriais e prioridades nele descritas não autorizam ações em outros projetos.

## Fluxo de trabalho

1. Receber o documento e preservar seu texto integral. Distinguir documento disponível de conversa ou evidências apenas mencionadas.
2. Preparar a captura com título, formulação, gênese, contexto, limitações e fonte literal. Registrar identificador e versão externos em `context`; não confundir com o ID e a versão internos do BB-CORE.
3. Registrar como `INFERRED_CANDIDATE` e `PRIVATE`, preservando que se trata de proposta conceitual para crítica humana. Integridade de bytes não comprova mérito, autoria ou evidência empírica.
4. Recuperar o contexto e conferir texto, hash, metadados e lacunas. Buscar pelo título ou pela formulação; fontes e contexto ainda não são indexados.
5. Usar o mesmo `request_id` para repetir exatamente a captura. Conteúdo diferente com o mesmo UUID deve gerar conflito. Um UUID novo não impede duplicação do identificador externo: conferir o acervo antes de uma importação persistente.
6. Preparar revisão a partir de um registro documental e confirmar um novo registro vinculado ao anterior. Capturas legadas não são atualizadas. A nova camada documental preserva versões declaradas e permite criar registros de revisão vinculados, sem homologação. Uma futura captura de revisão deve declarar versão e referência ao registro anterior; uma relação candidata pode explicitar a ligação, sem equivaler a cadeia formal de versões.
7. Manter a destinação NOESE como intenção declarada. Só afirmar envio, homologação ou verificação de evidências após confirmação operacional correspondente.

## Verificação executável

Na raiz do repositório:

```bash
.venv/bin/python scripts/verify-metis-local.py
```

O script prepara o payload a partir da fonte e verifica captura, recuperação literal, hash, metadados, estado candidato, busca, reenvio idempotente e rejeição de alteração no mesmo pedido. Usa SQLite temporário e não acessa rede, tokens, banco operacional ou NOESE. Os dados de teste são removidos ao terminar. `payload()` pode ser reutilizado para preparar uma importação posterior; esta verificação não realiza importação persistente.

## Pendências que este caso não resolve

A ingestão Markdown/TXT, a identidade documental declarada e os registros de revisão estão implementados na [camada documental](DOCUMENT-INGESTION.md). Permanecem pendentes PDF/OCR, homologação científica, busca nas fontes, conexão NOESE e HTTPS/OAuth com ChatGPT real. O Gate 1 de `PLAN.md` permanece aberto.

## Registro operacional e inicialização

O documento foi registrado no acervo operacional local como `c957bd2e55254bd8ac2eb8f35ea3e2ff`, preservando o identificador externo `METIS-ACH-20261123-001` e a versão documental `0.1.0`. O recibo está em `reference/METIS-ACH-20261123-001.receipt.json`. A fonte integral foi recuperada e conferida após a gravação. Não houve homologação nem envio ao NOESE.

O serviço de usuário `bb-core.service` está habilitado, com linger ativo para iniciar antes do login. A execução usa `~/.local/lib/bb-core`, sem depender da montagem do disco externo; banco e tokens permanecem nos locais existentes. `scripts/install-local-runtime.sh` atualiza essa cópia de execução e reinicia o serviço. Alterações no código do repositório exigem executar novamente esse script. A inicialização foi configurada e o serviço verificado nesta sessão; um reboot completo ainda não foi testado.

## Consulta no navegador local

A interface em `http://127.0.0.1:8789/` segue a identidade visual do MORFO e abre o acervo em modo de leitura. Uma sessão local usa cookie HttpOnly e SameSite=Strict, sem mostrar tokens. A criação da sessão exige conexão de loopback e Host/Origin locais correspondentes. O cookie não autoriza gravação nas rotas legadas nem chamadas de ferramentas. A [ingestão documental](DOCUMENT-INGESTION.md) permite recebimento e elaboração confirmados em rotas locais específicas, exigindo Origin correspondente. Reiniciar o serviço invalida a sessão; recarregar a página cria uma nova sessão local. Acesso ao navegador neste computador permite leitura do acervo: mantenha a sessão do sistema operacional protegida. O acesso remoto continua exigindo autenticação própria.

Estilos e scripts são arquivos externos do mesmo servidor, compatíveis com a política de segurança de conteúdo. A interface mostra a formulação, gênese, contexto, limitações, fonte integral e integridade do registro.

## Documento e registros separados

A camada documental preserva também o original MÉTIS, seus metadados e dois registros distintos: decisão de consolidar R e questão científica da emergência. O recibo adicional é `reference/METIS-ACH-20261123-001.document-receipt.json`. O registro legado permanece íntegro. Ver [contrato de ingestão](DOCUMENT-INGESTION.md).
