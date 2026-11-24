# Plano de evolução do BB-CORE (v0.3.0 — 2026-11-24)

> **Estado do documento:** Revisão v0.3.0 para exame humano, delimitando a próxima fase de desenvolvimento exclusivamente à **interação humana local** com o BB-CORE. Nenhum código ou banco operacional foi alterado por esta revisão.
>
> **Convenção de estatuto neste plano:**
> - `[FUNDAMENTO EXISTENTE]`: regra ou garantia já estabelecida nos contratos (`README.md`, `docs/DOCUMENT-INGESTION.md`, `docs/EVENTS.md`, `docs/PLAN.md` v0.1).
> - `[PROPOSTA]`: encaminhamento sugerido a partir das avaliações; **não** constitui decisão arquitetural consolidada até aprovação humana explícita.
> - `[QUESTÃO EM ABERTO]`: ponto que exige decisão humana antes da implementação.

Enquanto a integração pública estiver pendente, exercitar os processos locais com o [registro MÉTIS e o processo local](LOCAL-PROCESS.md) e com o percurso real das avaliações sucessivas do próprio BB-CORE.

---

## 1. Delimitação da próxima fase: Interação Humana Local `[PROPOSTA]`

A próxima fase concentra-se **exclusivamente na interação humana local** com o BB-CORE (interface web em loopback e núcleo local).

**Fora do escopo imediato desta fase** (compromissos preservados na Seção 7, sem eliminação):
- Evolução de ferramentas ou fluxos no servidor MCP (`POST /mcp`).
- Integrações remotas, túneis públicos, OAuth multi-sistema e Gateway HTTPS (Gate 1 / Gate 3).
- Gatilhos automáticos, descoberta proativa e mecanismos de participação autônoma (Gate 4).

O núcleo comum (`Archive`, `Documents`, `Events`) continua compartilhado, mas toda a concepção de experiência, fluxo e validação desta fase parte do **pesquisador operando localmente**.

---

## 2. Fundamentos conceituais e garantias preservadas `[FUNDAMENTO EXISTENTE]`

O BB-CORE é uma memória investigativa local em que fontes, documentos, registros intelectuais, acontecimentos e relações mantêm identidades e responsabilidades distintas.

Permanecem inegociáveis:

1. **Três dimensões independentes:** proveniência (documentos, versões, recebimentos, trechos em bytes UTF-8), trajetória (diário append-only `BB-EVENT-1`, podendo permanecer vazia) e relações (propostas candidatas e atribuições de reconhecimento/contestação).
2. **Proibição de reescrever o passado:** registros originais (`insights`), bytes documentais (`document_contents`) e eventos (`intellectual_events`) não são sobrescritos nem apagados. Não se fabricam trajetórias retrospectivas para o acervo anterior.
3. **Limites epistemológicos:** integridade local de bytes não comprova autoria civil, causalidade histórica nem validade científica. Confirmação humana de um registro ou evento não equivale a homologação científica.
4. **Projeções descartáveis e reconstruíveis `[PROPOSTA]`:** qualquer índice derivado (busca de formulações correntes/anteriores, filtros investigativos, contadores de pendências) deve ser 100% reconstruível a partir dos registros originais e do diário de eventos, sem jamais substituir a fonte canônica.
5. **Incompletude intelectual vs. pendência operacional `[FUNDAMENTO EXISTENTE]` / `[PROPOSTA]`:**
   - *Incompletude intelectual* (`OPEN_QUESTION`, `missing`, `occurred_at: null`, lacunas em `limitations`, ausência de trajetória posterior) é estado legítimo do conhecimento — **não** é defeito nem tarefa pendente.
   - *Pendência operacional* (`VERSION_CONFLICT` sem exame formal, paginação ausente, integração remota pendente) é limitação ou tarefa do sistema/operador.

---

## 3. Quatro capacidades humanas: da atividade ao contrato do núcleo `[PROPOSTA]`

A interface não deve ser desenhada como um espelho das rotas da API (`POST /api/events`, `POST /api/insights` etc.). Ela deve partir das **atividades intelectuais do pesquisador** e mapear nos contratos do núcleo o que os sustenta:

| Capacidade | O que o pesquisador faz | Como o núcleo sustenta (ou onde falta suporte) |
| ---------- | ----------------------- | ---------------------------------------------- |
| **Preservar** | Receber material bruto, registrar proveniência, detectar versões conflitantes sem apagar nada, fixar registros confirmados com trechos ancorados. | `[FUNDAMENTO EXISTENTE]` `Documents.ingest`, `Documents.create_record`, `Events.append` (`request_id` UUID + `confirmed: true` + SHA-256). Falta tratamento formal de `VERSION_CONFLICT` (pós-escopo imediato ou etapa dedicada). |
| **Examinar** | Ler documento integral e âncoras exatas, inspecionar trajetória cronológica de gravação, ver lacunas (`missing`), limitações e atribuições de relações sem confundir com verdade. | `[FUNDAMENTO EXISTENTE]` `GET /api/documents/{id}`, `GET /api/insights/{id}/context`, `GET /api/insights/{id}/trajectory`, `GET /health`. UI atual já lê cards e trajetória, mas precisa conectar melhor documento ↔ registros ↔ eventos. |
| **Elaborar** | Trabalhar uma ideia em progresso, salvar rascunho sem sujar o diário oficial, confirmar novo registro ancorado, reformular um insight mantendo identidade, registrar crítica, propor interpretação, vincular evidência ou contestar/reconhecer relação. | `[FUNDAMENTO EXISTENTE]` `Events.append` suporta 7 tipos públicos + `Documents.create_record` suporta `supersedes_id`. **Lacuna atual:** UI não expõe elaboração de acontecimentos nem distingue rascunho persistente de registro confirmado. |
| **Investigar** | Perguntar ao acervo: o que está em aberto, que decisões foram adotadas, o que foi reformulado, o que recebeu críticas, o que se apoia em certo documento, distinguindo formulação original de corrente. | `[PROPOSTA]` Exige **índice derivado reconstruível** de formulações (original vs. corrente), filtros por natureza/estado/trajetória/proveniência e paginação em `/api/insights` (hoje travado em 30 e FTS5 só vê formulação inicial). |

---

## 4. Ciclo de elaboração: em andamento, rascunho persistente e confirmado `[PROPOSTA]`

Para evitar que a rigidez do diário imutável (`BB-EVENT-1`) force o pesquisador a confirmar ideias prematuras — ou perca trabalho ao fechar uma aba —, a interação humana deve distinguir três estados claros:

| Estado | Natureza | Persistência e efeito no núcleo |
| ------ | -------- | ------------------------------- |
| **1. Elaboração em andamento** | Trabalho cognitivo ativo no leitor/editor (selecionando trechos, redigindo crítica, comparando formulação anterior e nova). | Estado em memória da interface; não grava em `insights` nem em `intellectual_events`; sem impacto em hashes ou busca. |
| **2. Rascunho persistente** | Trabalho interrompido que o pesquisador quer retomar depois (ex.: revisão parcial, crítica ainda sem evidência vinculada). | Persiste localmente **fora** de `insights` e **fora** da cadeia `BB-EVENT-1`. Não gera `INSIGHT_REGISTERED`, não entra na trajetória oficial e pode ser editado ou descartado livremente. |
| **3. Registro intelectual confirmado** | Ato deliberado de preservação (`confirmed: true`, `request_id` UUID). | Entra no núcleo canônico (`Documents.create_record` ou `Events.append`), torna-se imutável/append-only, entra na cadeia de hashes e passa a compor a memória investigativa. |

---

## 5. Cenário-guia de experiência real: avaliações do próprio BB-CORE `[PROPOSTA]`

Em vez de validar a interface apenas com dados sintéticos, usaremos o **próprio ciclo de avaliações sucessivas do BB-CORE** como percurso real de uso das quatro capacidades:

1. **Preservar:** ingerir os textos das avaliações técnicas/conceituais e contratos (`DOCUMENT-INGESTION.md`, `EVENTS.md`, relatórios de avaliação) como documentos imutáveis com proveniência declarada.
2. **Examinar:** abrir cada documento no leitor, verificar trechos ancorados em bytes UTF-8 e consultar os registros derivados sem perder o contexto original.
3. **Elaborar:**
   - Registrar um **achado conceitual** (ex.: *"Verificação integral O(N) em `_verified()`"*) e uma **decisão metodológica** (ex.: *"Separar índice derivado reconstruível da fonte canônica"*).
   - Usar **rascunho persistente** para redigir uma crítica ou revisão incompleta, fechar o diálogo/página e retomar depois.
   - Executar **reformulação mantendo identidade** (`FORMULATION_REVISED`) quando uma avaliação corrige ou refina a anterior (ex.: refinar *"diário à prova de mentira"* → *"integridade criptográfica depende de checkpoint externo e não comprova veracidade"*).
   - Registrar **crítica** (`CRITIQUE_RECORDED`) e **questão aberta** (`OPEN_QUESTION`) sobre pontos pendentes.
4. **Investigar:** buscar por termos que mudaram entre a formulação original e a corrente, filtrar apenas questões em aberto, decisões adotadas e registros com revisões ou críticas, verificando se a interface responde às perguntas investigativas reais.

---

## 6. Fases da interação humana local e detalhamento da Etapa 1 `[PROPOSTA]`

### Sequência desta fase local
1. **Etapa 1 — Elaboração e continuidade utilizáveis:** fluxo completo de **Elaborar** (em andamento → rascunho persistente → confirmado) para acontecimentos, revisões mantendo identidade (`FORMULATION_REVISED`), críticas, interpretações, evidências e atribuições de relação, integrado ao **Examinar** e **Preservar** existentes.
2. **Etapa 2 — Investigação coerente (Recuperação):** índice derivado reconstruível (original vs. corrente), indicação explícita de onde houve correspondência, filtros investigativos e paginação em `/api/insights`.
3. **Etapa 3 — Eficiência sem perda de integridade:** benchmarks (100, 1.000, 5.000 eventos) e eliminação de verificações redundantes na mesma fotografia transacional.
4. **Etapa 4 — Divergências documentadas:** exame e decisão formal sobre `VERSION_CONFLICT` (histórico vs. pendência corrente).

*(A Etapa 5 — Autorização granular e integração remota — permanece articulada ao Gate 3, fora desta fase local.)*

### Detalhamento da Etapa 1 (Contratos, critérios e limites)
- **Atividades cobertas na UI:**
  - *Reformular mantendo identidade* (`FORMULATION_REVISED`, modo `OBSERVED`).
  - *Registrar crítica* (`CRITIQUE_RECORDED`, `OBSERVED`/`REPORTED`).
  - *Propor interpretação* (`INTERPRETATION_PROPOSED`, `PROPOSED`).
  - *Vincular evidência* (`EVIDENCE_REFERENCED`).
  - *Registrar acontecimento* (`OCCURRENCE_RECORDED`).
  - *Reconhecer ou contestar relação* (`RELATION_RECOGNIZED` / `RELATION_CONTESTED`).
  - *Salvar, retomar e descartar rascunho persistente* antes da confirmação.
- **Contratos preservados `[FUNDAMENTO EXISTENTE]`:**
  - Toda confirmação escreve via `POST /api/events` (`Events.append`) com `request_id` UUID, `confirmed: true`, validação estrita por tipo e gravação atômica na cadeia `BB-EVENT-1`.
  - Leitura via `GET /api/insights/{id}/context` e `GET /api/insights/{id}/trajectory`, protegida por sessão local `bb_local`.
- **Critérios de aceitação verificáveis `[PROPOSTA]`:**
  1. Pesquisador executa todas as operações acima a partir do leitor sem editar JSON bruto.
  2. Diferença entre *reformular mantendo identidade* (`FORMULATION_REVISED`) e *criar novo registro relacionado* (`supersedes_id`) é explícita antes da confirmação.
  3. Rascunho persistente sobrevive a recarregamento da página/diálogo e **não** aparece em `intellectual_events`, `insights` nem na trajetória oficial antes de ser confirmado.
  4. Campos obrigatórios são guiados por atividade; lacunas (`missing`) são registradas explicitamente quando desconhecidas.
  5. Envio idempotente reutiliza `request_id` em falha de rede; após sucesso, trajetória atualiza imediatamente.
  6. Cenário-guia com as avaliações do BB-CORE executável de ponta a ponta; os 40 testes atuais seguem passando sem regressão.
- **Limites da Etapa 1:** não altera schema de `intellectual_events`, não cria edição/exclusão de eventos, não altera busca FTS5 (Etapa 2) e não modifica o MCP.

### Questões que exigem decisão humana antes de codar `[QUESTÃO EM ABERTO]`
1. **Onde mora o rascunho persistente?**
   - *Opção A (navegador local / `localStorage`):* zero impacto no SQLite, descarte trivial, mas fica preso àquele navegador/perfil.
   - *Opção B (tabela isolada no SQLite, ex.: `local_drafts`, fora de `BB-EVENT-1` e `insights`):* sobrevive a troca de navegador e backup único, mas exige endpoints simples de rascunho no servidor local.
2. **Responsável padrão na UI:** lembrar o último identificador/nome declarado na sessão local ou exigir preenchimento/marcação explícita de desconhecido a cada confirmação?
3. **Seleção de evidências no formulário:** seletor com documentos/recebimentos/insights já preservados no acervo local, entrada por ID colado, ou ambos?
4. **Nomenclatura do botão atual *"Preparar revisão deste registro"* (`supersedes_id`):** renomear/agrupar junto a *"Reformular mantendo identidade"* para explicitar a criação de nova identidade vs. preservação de identidade?

---

## 7. Compromissos e Gates anteriores preservados `[FUNDAMENTO EXISTENTE]`

Os marcos abaixo permanecem válidos e os pendentes continuam obrigatórios antes de declarar o sistema pronto para uso remoto, MCP ampliado ou intersistemas:

- **Gate 0 — validado pelos testes unitários locais:** Captura explícita; integridade; idempotência; recuperação; busca textual; relação candidata; separação entre token de leitura/escrita.
- **Ingestão documental local (implementado):** Bytes originais, versões declaradas, recebimentos, conflitos preservados e registros humanos com âncoras verificáveis. Ver [contrato e limites](DOCUMENT-INGESTION.md).
- **Continuidade orientada a eventos (implementado):** Diário append-only, encadeamento SHA-256, reprodução e checkpoints, conforme [BB-EVENT-1](EVENTS.md).
- **Gate 1 — integração real ChatGPT (P0 — pendente, fora do escopo imediato):** Confirmar transporte e catálogo MCP com conta real, OAuth 2.1 / PKCE, captura apenas após consentimento explícito e recuperação em segunda conversa.
- **Gate 2 — cadeia de proveniência (P0 — pendente, fora do escopo imediato):** Importação de conversas autenticáveis, permissões granulares, `insight_sources` ampliado.
- **Gate 3 — conhecimento intersistemas (P1 — pendente, fora do escopo imediato):** Autorização por sujeito, sistema, coleção, papel e ação; políticas de exportação e filtragem obrigatória no MCP.
- **Gate 4 — continuidade (P1 — pendente, fora do escopo imediato):** Detecção opcional de insights relacionados, recuperação semântica como candidata e benchmark humano.

### Não fazer no MVP-0 `[FUNDAMENTO EXISTENTE]`
Agentes permanentes, crawling de conversas, vigilância, importação implícita de mensagens privadas, criação de grafos causais por similaridade, vetores sem teste de necessidade, hospedagem pública direta, endpoints de execução nos sistemas consumidores.
