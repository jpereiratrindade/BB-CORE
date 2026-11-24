# Plano de evolução do BB-CORE (v0.5.0 — 2026-11-24)

> **Estado do documento:** Revisão **v0.5.0** — Consolidação do contrato de ingestão Markdown parametrizado ([`BB-CORE-ESP-ING-001` v0.2.0](BB-CORE-ESP-ING-001.md)) para exame humano antes da implementação em código.
>
> **Histórico preservado:** As revisões `v0.1.0` a `v0.4.0` permanecem no histórico Git e têm seus fundamentos e compromissos suspensos preservados abaixo.

---

## Critério fundamental de triagem

> **Esta funcionalidade contribui diretamente para preservar, contextualizar ou recuperar um achado intelectual?**
>
> Se a resposta não for suficientemente clara, sua implementação pode esperar.

---

## 1. Delimitação e decisões consolidadas

1. **Finalidade:** preservar, contextualizar, permitir exame e recuperar achados intelectuais produzidos no ChatGPT ou em outros ambientes externos de elaboração.
2. **Parser YAML (`PyYAML`):** utilizar `PyYAML` como dependência instrumental (`pyproject.toml`), com `SafeLoader` customizado que rejeita chaves duplicadas, tipos inválidos, campos desconhecidos, versões incompatíveis (`schema != "BB-CORE-ING-0.2.0"`) e excedentes de limite. **Não** desenvolver parser YAML próprio.
3. **Formulação e autoria:** priorizar preservação literal da formulação presente no Markdown (`DOCUMENT_EXCERPT`). Distinguir estritamente `formulation_origin` (`DOCUMENT_EXCERPT`, `EXTERNAL_AI_ASSISTED`, `HUMAN_FORMULATION`), autoria declarada (`attribution`) e confirmação humana (`confirmed_by_declared`). **Nunca** classificar conteúdo produzido por IA como `HUMAN_FORMULATION`.
4. **Cardinalidade:** suportar 0, 1 ou vários registros por documento, cada qual com identidade própria e confirmação individual e facultativa, sem inferir relações entre eles.
5. **Mesa de Elaboração experimental:** retirar da navegação principal da interface (`hidden` no menu), preservando integralmente o código (`bbcore/elaborations.py`, `web/mesa.js`) e os dados eventualmente existentes na tabela `elaborations`, suspendendo sua expansão.
6. **Proveniência:** distinguir explicitamente o Markdown parametrizado (artefato de transporte) da fonte original (ex.: conversa no ChatGPT), registrando lacunas (`provenance_gaps` / `missing`). A integridade SHA-256 do Markdown não comprova fidelidade à conversa de origem.
7. **Fora do escopo:** MCP, integrações remotas, agentes autônomos, gatilhos automáticos, descoberta ou inferência automática, busca vetorial/semântica e expansão da Mesa de Elaboração.

---

## 2. Reavaliação de impacto no banco de dados: cinco identidades e reimportação

A análise anterior de que *nenhuma adaptação de banco seria necessária* foi **reavaliada e corrigida** à luz dos requisitos de identidade e reimportação:

- **Problema identificado:** `insights` e `record_elaborations` não indexam a **identidade declarada do registro transportado** (`external_record_id` / `(document.external_id, id_local)`). Sem esse registro no SQLite, reimportar o mesmo documento com um novo `request_id` (nova operação computacional) permitiria criar **duplicações silenciosas** no acervo ou impediria detectar divergência de formulação em nova versão documental.
- **Adaptação aditiva necessária:**
  1. **Tabela aditiva `imported_record_identities`** (sem alterar tabelas existentes): mapeia `declared_record_key` → `insight_id`, `document_external_id`, `declared_version`, `claim_sha256`, `confirmed_at`.
  2. **Ampliação controlada de `formulation_origin`:** aceitar `EXTERNAL_AI_ASSISTED` além de `DOCUMENT_EXCERPT` e `HUMAN_FORMULATION` em `Documents.create_record`.
- **Comportamento garantido:**
  - *Reimportação com mesma formulação:* cria novo recebimento documental (`RECEIVED_AGAIN`), marca o registro candidato como `ALREADY_CONFIRMED` apontando para o `insight_id` existente e **impede duplicação silenciosa**.
  - *Nova versão ou reimportação com formulação divergente:* marca `FORMULATION_DIVERGENCE`, **nunca** sobrescreve nem revisa automaticamente o insight anterior.

---

## 3. Interação humana: `Receber → Examinar → Confirmar → Recuperar`

1. **Receber:** enviar arquivo `.md` ou colar texto Markdown parametrizado (`POST /api/documents`), preservando os bytes literais.
2. **Examinar:** o sistema interpreta deterministicamente o cabeçalho e o corpo, exibindo:
   - texto original integral;
   - parâmetros interpretados (identidade documental, fonte de origem e lacunas de proveniência, registros candidatos `0..N`, âncoras em bytes UTF-8, origem da formulação e limitações);
   - situação diante do acervo (`NEW_CANDIDATE`, `ALREADY_CONFIRMED`, `FORMULATION_DIVERGENCE` ou `VERSION_CONFLICT`).
3. **Confirmar:** o pesquisador não precisa redigir novamente o que já veio parametrizado; escolhe individualmente quais registros confirmar (`confirmed: true`) e, se desejar, ajusta campos com atribuição explícita.
4. **Recuperar:** consultar os registros confirmados no Acervo de achados com seu contexto, formulação original/corrente, fontes ancoradas, limitações, proveniência e trajetória (`BB-EVENT-1`).

---

## 4. Plano incremental de implementação

1. **Dependência e adaptador YAML (`pyproject.toml`, `bbcore/parametrized.py`):** adicionar `PyYAML` e implementar interpretador determinístico `BB-CORE-ING-0.2.0` com `SafeLoader` estrito (sem chaves duplicadas, validação de tipos/campos/limites e cálculo de âncoras UTF-8).
2. **Identidades declaradas e `formulation_origin` (`bbcore/documents.py`):** adicionar tabela `imported_record_identities`, suporte a `EXTERNAL_AI_ASSISTED` e método de inspeção/confirmação que distingue as 5 identidades.
3. **Rotas locais (`bbcore/server.py`):** rota de inspeção pré-confirmação (ex.: `GET /api/documents/{version_id}/parametrized` ou `POST /api/documents/inspect`) mantendo `/mcp` inalterado.
4. **Interface simplificada (`web/`):** retirar a Mesa de Elaboração da navegação principal e integrar o fluxo `Receber → Examinar → Confirmar → Recuperar` diretamente em `#recebimento` e `#documentos`.
5. **Validação com experiência real e testes:**
   - **Verificação prévia do acervo operacional (`~/.local/share/bb-core/bb.sqlite`):** o registro `a5ae664bd9f248b1b28b12d571f26364` (*"Distinção entre elaboração intelectual e preservação do conhecimento"*, documento `BB-CORE-INSIGHT-001` v0.1.0) **já existe** no banco operacional local — o fluxo deve reconhecer essa existência prévia sem duplicar silenciosamente.
   - Exercitar em ambiente de teste e validação controlada: (a) ingestão de [`docs/reference/BB-CORE-INSIGHT-001.parametrized.md`](reference/BB-CORE-INSIGHT-001.parametrized.md), (b) reimportação do mesmo documento, (c) documento com múltiplos registros e confirmação seletiva, (d) recebimento de versão divergente (`VERSION_CONFLICT` e `FORMULATION_DIVERGENCE`), e (e) recuperação completa do contexto, limitações e proveniência.

---

## 5. Compromissos e Gates anteriores preservados (suspensos nesta etapa)

- **Gate 0 — validado pelos testes unitários locais (42 testes).**
- **Ingestão documental local e `BB-EVENT-1` — implementados.**
- **Gates 1, 2, 3 e 4 (MCP real ChatGPT, cadeia de proveniência remota, autorização intersistemas, continuidade assistida) — suspensos nesta fase, preservados sem descarte.**
- **Não fazer no MVP-0:** agentes permanentes, crawling, vigilância, importação implícita de conversas privadas, grafos causais automáticos, vetores sem teste de necessidade, hospedagem pública direta.
