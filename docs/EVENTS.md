# Continuidade intelectual orientada a eventos — BB-EVENT-1

## Fundamento e revisão do modelo

Todo insight nasce como um registro intelectualmente autônomo, identificado e sustentado por fontes recuperáveis. Sua evolução é contingente e somente pode ser reconstruída a partir de acontecimentos efetivamente registrados. Suas relações com outros insights não são presumidas: podem ser propostas, examinadas, contestadas ou reconhecidas posteriormente, com proveniência e histórico preservados.

O modelo já preserva fontes, documentos, versões, recebimentos e âncoras. `insights` conserva formulações iniciais; `record_elaborations` distingue tipo e estado de trabalho; `revisions` conserva os registros legados de captura; `relations` conserva propostas candidatas. Não é necessário duplicar essas entidades ou importar seus conteúdos como uma história intelectual fictícia.

A extensão mínima acrescenta um diário de eventos e um cabeçalho de cadeia. Referências documentais e intelectuais reutilizam IDs existentes. A reprodução dos eventos gera uma projeção descartável da trajetória; não sobrescreve os insights nem promove suas hipóteses a fatos.

## Três dimensões independentes

1. Proveniência: os documentos, fontes, recebimentos, trechos e condições declaradas.
2. Trajetória: apenas acontecimentos efetivamente registrados; pode permanecer vazia.
3. Relações: propostas e atribuições de reconhecimento ou contestação, com sujeito, fundamentos e alcance. Compartilhar fonte, aparecer depois no diário ou possuir hashes encadeados não estabelece relação intelectual.

O diário possui ordem global de gravação para integridade. Essa ordem não é uma cronologia causal. O instante do acontecimento é declarado e pode ser desconhecido ou anterior ao registro; o instante do registro é atribuído pelo servidor. Datas declaradas não são convertidas em horários fictícios.

## Implementação incremental

1. Diário append-only com esquema versionado, eventos canônicos, SHA-256, cabeçalho e UUID de idempotência, na mesma transação SQLite.
2. Reprodução verificável com baselines explícitas, referências recuperáveis e projeções separadas de formulações e relações; sem migração retrospectiva de eventos.
3. Integração das novas capturas e revisões documentais com o diário, APIs de consulta e registro explícito de acontecimentos.
4. Consulta de trajetória no leitor de um insight e testes de recuperação, concorrência, alterações, truncamento e checkpoint.

## Estrutura e imutabilidade

`intellectual_events` é o diário, indexado por sequência técnica, insight principal e insight relacionado explícito. `event_log_head` guarda a identidade do diário e o último par sequência/hash. Não há tabela paralela de documentos, relações ou usuários. Triggers SQLite rejeitam UPDATE e DELETE de eventos e DELETE do cabeçalho. Não há API de edição ou exclusão de eventos.

O envelope canônico inclui: esquema, identidade/posição do evento, insight(s), natureza, modo, acontecimento declarado, momento de registro, origem, responsável declarado ou null, conteúdo, referências com snapshots e fingerprints, vínculos anteriores fundamentados, lacunas, limitações, baselines e hash técnico anterior. O hash é SHA-256 do envelope inteiro em UTF-8, excluindo apenas seu próprio campo `event_hash`. A serialização usa Python JSON com chaves ordenadas, separadores compactos, caracteres Unicode preservados e valores não finitos rejeitados. Esse contrato local versionado não é uma implementação de RFC 8785.

As leituras do cabeçalho, eventos e referências também usam uma fotografia transacional consistente, evitando falsos conflitos durante gravações concorrentes.

A inclusão do evento e a atualização do domínio/cabeçalho/pedido idempotente ocorrem na mesma transação `BEGIN IMMEDIATE`. Escritas concorrentes são serializadas pelo SQLite. UUID repetido com o mesmo payload retorna o evento já gravado; outro payload com o mesmo UUID gera conflito. O diário é verificado antes de acrescentar eventos. Corrupção bloqueia novas gravações dependentes, em vez de prolongar uma cadeia inválida.

## Baselines e reprodução

Nenhum evento é gerado ao atualizar ou reiniciar o sistema para os insights existentes. Sua trajetória permanece vazia, mesmo que `revisions` ou vínculos legados já existam. Não apagamos esses dados, mas também não os promovemos automaticamente a acontecimentos intelectuais.

Novas capturas geram `INSIGHT_REGISTERED`, modo OBSERVED, que observa somente a gravação pelo serviço. Sua baseline `CREATION_OBSERVED` preserva o estado inicial e as referências. Não observa a origem intelectual, a validade ou a autoria do insight.

Quando um insight anterior recebe seu primeiro evento explícito, o envelope preserva uma baseline `EXISTING_RECORD_AT_FIRST_EVENT`: estado que estava disponível **naquele registro**, não uma história reconstruída. A baseline não é um acontecimento retrospectivo nem recebe uma data histórica inventada.

A reprodução começa nessa base e aplica apenas revisões explícitas `FORMULATION_REVISED` aos campos title, claim e limitations. O ID intelectual é mantido; as linhas originais e as formulações anteriores permanecem intactas. A projeção é derivada e não sobrescreve `insights`. `trajectory.current_state` mostra a formulação corrente segundo os eventos; as APIs e a busca legadas continuam consultando o registro inicial. Indexar projeções correntes fica para outra etapa.

O fluxo documental anterior de “revisar criando outro registro” continua disponível para compatibilidade. Ele cria um registro autônomo e um evento `REVISION_REFERENCE_RECORDED` que documenta o vínculo explicitamente solicitado, sem substituir a formulação do anterior. Para reformular o mesmo insight, usa-se `FORMULATION_REVISED`. Os dois efeitos não são confundidos.

`Events.replay_bundle` reproduz projeções a partir de exportação verificada, inclusive sem conexão ao banco. Nesse modo, a disponibilidade dos arquivos externos não é revalidada. A recuperação pelo banco também compara referências e fingerprints com as fontes, versões, recebimentos, âncoras e registros recuperáveis. O estado atual e as atribuições de relações são projeções distintas.

## Acontecimentos e atribuições

Modos: OBSERVED (observado), REPORTED (relatado), PROPOSED (interpretação/proposta). O modo qualifica o acontecimento declarado, não certifica seu conteúdo. Origem e responsável desconhecidos permanecem null e as lacunas são acrescentadas automaticamente; nenhuma identidade é deduzida do token de acesso. Identificadores de pessoas são declarados, não autenticados civilmente.

Tipos públicos: OCCURRENCE_RECORDED, EVIDENCE_REFERENCED, CRITIQUE_RECORDED, INTERPRETATION_PROPOSED, FORMULATION_REVISED, PROVENANCE_SUPPLEMENTED, RELATION_RECOGNIZED e RELATION_CONTESTED. INTERPRETATION_PROPOSED exige PROPOSED. Uma revisão observada identifica o ato de formular e exige sujeito declarado; não promove a formulação a fato empírico. `PROVENANCE_SUPPLEMENTED` exige sujeito (`responsible`), data (`occurred_at`), fundamento (`content.summary`), referência de origem (`content.origin_reference`) e limitações, rejeitando alterações de formulação (`changes`); URLs mencionadas em acontecimentos genéricos nunca são interpretadas como referências de origem.

A projeção `trajectory.provenance` preserva o contexto inicial intacto e lista todas as complementações reconhecidas. Quando não existe URL no contexto inicial e há uma única URL válida complementada, `origin_status` é `SINGLE` e disponibiliza a retomada; quando existem URLs divergentes, `origin_status` é `DIVERGENT`, preservando todas sem precedência automática nem substituição silenciosa.

Cada trajetória também expõe `trajectory_point` por registro (`record_event_count`, `last_record_event_id`, `last_record_event_hash`, `formulation_revision_count`), sem depender de acontecimentos em registros não relacionados. No retorno de uma continuidade via `POST /api/events`, pode-se informar `expected_trajectory_point` para verificação transacional: se houver alterações posteriores no mesmo registro, o servidor responde `409` (`POSTERIOR_CHANGES`, listando `subsequent_events`) até exame humano com `acknowledge_divergence: true`; divergências incompatíveis com o histórico local respondem `409` (`TRAJECTORY_CONFLICT`).

Cada referência informa kind, id e role. Tipos: insight, source, document_version, receipt, anchor, relation ou event. A referência é resolvida e seu snapshot/fingerprint é preservado no evento. Texto ausente não é fabricado. Sem suporte indicado, o evento registra a lacuna `event_evidence`. Um recebimento documental em conflito pode ser referenciado como objeto sob exame; isso não o transforma em versão aceita.

`prior_events` é opcional e vazio por padrão. Quando informado, cada vínculo exige event_id existente, relationship (RESPONDS_TO, MOTIVATED_BY, CORRECTS ou CONTESTS), fundamento e evidências. O hash técnico anterior nunca é convertido automaticamente em vínculo intelectual. O sistema verifica a existência e a integridade das referências; não consegue provar a influência causal que uma pessoa declara.

Novas propostas pela API de relações exigem responsável identificado por id/name e origem declarada. As propostas anteriores continuam candidatas sem atribuição retroativa. Reconhecimento e contestação exigem sujeito, data do acontecimento, evidências, relação existente, fundamento/summary e alcance/scope. Ambos permanecem documentados e contestáveis. Reconhecer não altera `relations.status` para uma verdade aceita; contestar não apaga o reconhecimento. O mesmo evento fica consultável pelos dois insights da relação.

## APIs e exemplo

- `POST /api/events`: acrescentar acontecimento com confirmação explícita.
- `GET /api/insights/{id}/trajectory`: reprodução e referências conferidas.
- `GET /api/insights/{id}/context`: contexto e trajetória, preservando a formulação original.
- `GET /api/events/export`: exportação verificada do diário.
- `GET /api/events/checkpoint`: identidade e ponta atual da cadeia.

Leitura exige autoridade de leitura. Gravação exige token de escrita ou sessão local com cookie, Host/Origin locais correspondentes, JSON e `confirmed: true`. Não há nova integração remota nesta etapa.

Exemplo de evento explícito (substituir os IDs por referências existentes):

```json
{
  "request_id": "0bb339a6-b395-4a0e-b4f9-1d13a2653d46",
  "insight_id": "ID_DO_INSIGHT",
  "event_type": "CRITIQUE_RECORDED",
  "mode": "REPORTED",
  "occurred_at": null,
  "origin": "Crítica fornecida pelo pesquisador",
  "responsible": {"id": "sujeito:declarado", "name": "Nome declarado"},
  "content": {"summary": "Argumento crítico e seu fundamento declarado."},
  "evidence": [{"kind": "receipt", "id": "ID_DO_RECEBIMENTO", "role": "critical_argument"}],
  "prior_events": [],
  "missing": ["Data da discussão não fornecida"],
  "limitations": "Relato documental; influência intelectual não estabelecida.",
  "confirmed": true
}
```

## Checkpoints e limites criptográficos

A verificação detecta payloads alterados, sequência divergente, referências adulteradas, eventos removidos e truncamento em relação ao cabeçalho. Triggers não protegem contra um administrador que remova as proteções ou reescreva o arquivo inteiro. Se toda a cadeia e o cabeçalho forem recalculados, a consistência interna pode continuar válida.

Um checkpoint anterior, obtido e guardado com confiança **fora do controle exclusivo da base**, permite comparar o prefixo preservado e detectar essa reescrita. Um arquivo no mesmo computador é uma cópia operacional, não uma garantia de independência administrativa. Checkpoints desta etapa não são assinados; não há blockchain, consenso distribuído nem autoridade de timestamp.

```bash
python3 scripts/event-journal.py export /CAMINHO_PRIVADO/diario.json
python3 scripts/event-journal.py verify /CAMINHO_PRIVADO/diario.json --checkpoint /CHECKPOINT_CONFIAVEL.json
```

A exportação cria arquivos com permissão 0600 e não sobrescreve destinos. Exporta o checkpoint da mesma fotografia do diário; ele pode verificar extensões posteriores. Exportações contêm informações privadas e não devem ser publicadas no Git. Uma cadeia vazia não prova o conteúdo de eventos futuros.

## Interface e validação

O leitor do card informa quando não existem acontecimentos, sem apresentar linha do tempo artificial. Quando existem, oferece consulta dos eventos em ordem de gravação, distinguindo tempos, modos, sujeitos, lacunas, evidências e vínculos declarados. Reconhecimentos e contestações são apresentados como atribuições, separados da formulação. O registro de novos acontecimentos nesta etapa é feito pela API; um editor dedicado de eventos não foi acrescentado.

Testes cobrem legado sem eventos fictícios, captura transacional, reenvio idempotente, concorrência, falha e rollback, datas desconhecidas e diferentes do registro, revisão com identidade preservada, recuperação após reinício, reprodução offline, documentos e âncoras reutilizados, relações propostas/reconhecidas/contestadas, alteração de evidências, payloads, truncamento e reescrita integral detectável por checkpoint independente. Não há descoberta, avaliação ou integração automática de insights.


A verificação desta etapa percorre o diário completo e reproduz projeções em memória. Não há cache materializado ou checkpoint assinado. Paginação da trajetória, otimização de reprodução e edição assistida de acontecimentos são evoluções posteriores, preservando o mesmo contrato.
