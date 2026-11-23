# Ingestão documental local

O documento preservado e o registro intelectual elaborado a partir dele são objetos distintos. Ingerir um arquivo não cria um achado, não confirma seu conteúdo e não executa instruções contidas nele.

## Modelo persistente

- `document_contents`: bytes originais em BLOB SQLite, tamanho e SHA-256. Um conteúdo ocupa uma entrada mesmo quando recebido várias vezes.
- `documents`: identidade documental interna e identificador externo declarado, quando disponível. Nomes de arquivo não são usados para inventar identidade.
- `document_versions`: versão declarada e vínculo com o conteúdo. Rótulos de versão não são ordenados nem inferidos pelo sistema. Versão desconhecida permanece nula.
- `document_receipts`: eventos de recebimento, cada um com arquivo, procedência, responsável declarado, data documental opcional, instante de entrada, hash recebido e resultado. Um novo pedido produz um novo evento, mesmo para bytes idênticos. Reenviar exatamente o mesmo pedido com o mesmo UUID retorna o mesmo recibo.
- `insights` e `record_elaborations`: formulação, limitações, gênese, tipo, estado do trabalho, origem da formulação e confirmação humana declarada. Reutilizam o acervo existente sem alterar suas capturas anteriores.
- `document_anchors`: vínculos muitos-para-muitos entre registros, versões e recebimentos, com trecho literal, papel e offsets em bytes UTF-8. Um registro pode apoiar-se em vários documentos; um documento pode sustentar vários registros.

A inicialização acrescenta tabelas com `CREATE TABLE IF NOT EXISTS`, preservando o banco anterior. Não converte automaticamente fontes legadas em documentos nem modifica registros existentes. A deduplicação por hash se aplica à nova camada documental; fontes legadas permanecem intactas.

## Receber, revisar e confirmar

A seção “Receber documentos” aceita arquivos Markdown e TXT em UTF-8, até 256000 bytes, ou texto colado. Arquivos conservam seus bytes, inclusive BOM e quebras de linha. Texto colado tem como original o texto efetivamente recebido do navegador; não se afirma identidade com um arquivo anterior. Não há interpretação de Markdown como HTML nem extração por IA.

O operador confere a prévia e informa procedência e responsável. Identificador, versão e data documental são opcionais e não são extraídos automaticamente. Somente a confirmação explícita grava o documento. O recibo distingue `PRESERVED`, `RECEIVED_AGAIN` e `VERSION_CONFLICT`.

Mesmo identificador externo e versão declarada com hash diferente gera HTTP 409 **e preserva um evento de conflito com seus próprios bytes**, mantendo a versão aceita. O conteúdo divergente pode ser baixado no histórico, mas não pode fundamentar novos registros. Não há resolução automática. Uma revisão com identidade de versão corrigida deve ser recebida explicitamente; o evento de conflito permanece. Não se declara o conflito resolvido apenas porque outra versão foi recebida.

Documentos sem identificador externo reutilizam a identidade interna somente para conteúdo e versão declarada coincidentes; uma alteração não é inferida como revisão. Cada procedência continua registrada separadamente.

## Elaborar registros

O operador abre o documento, seleciona um trecho no texto original e usa “Vincular seleção”. Pode reunir até 16 âncoras, cada uma de até 20000 bytes, inclusive de documentos diferentes. O servidor verifica os offsets, o conteúdo, o hash, o recebimento e a versão antes de gravar.

| Tipo | Estado do trabalho permitido |
|---|---|
| Achado conceitual | Proposta |
| Decisão metodológica | Proposta ou decisão adotada no trabalho |
| Questão aberta | Em aberto |
| Relato empírico | Relato atribuído |

Esses estados não certificam verdade científica. Uma decisão adotada continua sendo um relato documental do processo. Uma questão aberta não se torna uma conclusão. O estado epistemológico legado (`REPORTED` ou `INFERRED_CANDIDATE`) é mantido separado do estado do trabalho.

A origem da formulação é declarada como formulação humana ou trecho documental. No segundo caso, o enunciado deve coincidir com uma das âncoras. Nome e confirmação ficam registrados com timestamp; não são autenticação de identidade civil. Esta etapa não aceita sugestões por IA e não usa serviço de IA.

O campo opcional de revisão cria um **novo registro**, vinculado ao anterior do mesmo tipo, sem sobrescrevê-lo. A recuperação do anterior informa seus revisores. Não há edição destrutiva, homologação ou transições automáticas de estado.

## API local

- `POST /api/documents`: recebimento confirmado, conteúdo em base64 para preservar bytes.
- `GET /api/documents?offset=0`: catálogo paginado, 100 versões por página.
- `GET /api/documents/{version_id}`: texto, versões, recebimentos e registros vinculados.
- `GET /api/documents/{version_id}/original`: bytes originais conferidos.
- `GET /api/receipts/{receipt_id}/original`: bytes específicos do recebimento, incluindo conflitos.
- `POST /api/document-records`: registro confirmado com âncoras documentais.
- `GET /api/insights/{id}/context`: elaboração, histórico e fontes recuperáveis, incluindo âncoras documentais.

A sessão do navegador permite leitura local e apenas as duas operações documentais confirmadas acima. A escrita exige cookie HttpOnly/SameSite=Strict, conexão loopback, Host e Origin locais correspondentes, JSON e confirmação no payload. A sessão não concede escrita nas rotas legadas. As APIs também mantêm o suporte existente a token de escrita; nenhum token é exposto pela interface. Não há isolamento multiusuário nesta etapa. O acesso à sessão local do computador implica capacidade de registrar documentos e formulações.

## Validação e operação

`python3 -m unittest discover -s tests -v` verifica preservação dos bytes, múltiplas procedências, reenvio idempotente, conflitos persistidos, novas versões, dois tipos de registro MÉTIS, múltiplos documentos por registro, revisão imutável, offsets Unicode, corrupção, reinicialização e restrições de acesso HTTP.

`scripts/register-metis-document.py` registra de forma idempotente o documento MÉTIS e dois registros por extração literal de seções conhecidas: decisão de consolidar R e questão científica da emergência. Usa a API local autenticada, preserva o registro legado e grava um recibo em `docs/reference`. Executar novamente repete os mesmos pedidos, sem criar novas ocorrências. Testes de conflito artificial devem usar banco temporário, nunca poluir o acervo operacional.

Antes da primeira ativação da camada documental, foi criado backup privado do banco por `sqlite3.Connection.backup`. Código de execução é atualizado por `bash scripts/install-local-runtime.sh`.

Continuam fora desta etapa: PDF/OCR, extração assistida por IA, resolução formal de conflitos, autenticação de autoria, homologação científica, HTTPS/OAuth novos, integração NOESE e descoberta automática de relações.
