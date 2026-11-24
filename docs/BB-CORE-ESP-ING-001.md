# BB-CORE-ESP-ING-001 — Contrato de Ingestão Markdown Parametrizado

**Versão do contrato:** `0.2.0` (consolida e substitui a proposta `0.1.0`)  
**Data:** `2026-11-24`  
**Estatuto:** Especificação consolidada para exame humano antes da implementação em código  
**Independência:** Este contrato é independente da interface gráfica e da ferramenta externa que produz o documento (ChatGPT, editor local, script ou outro sistema).

---

## 1. Propósito e delimitação de responsabilidade

Este contrato define o formato **Markdown Parametrizado** para transportar achados e registros intelectuais produzidos em ambientes externos até o **BB-CORE**.

- **Ambiente externo:** conduz investigação, discussão, formulação, explicitação de fundamentos/limitações e gera o documento Markdown parametrizado.
- **BB-CORE:** recebe os bytes originais, preserva-os integralmente, valida estrutura e parâmetros, interpreta deterministicamente o conteúdo, apresenta tudo para exame humano, confirma apenas o que o operador autorizar e sustenta a recuperação e continuidade (`BB-EVENT-1`).

O BB-CORE **não** infere conhecimento, relações, autoria civil, fidelidade a conversas externas, validade científica nem acontecimentos intelectuais a partir da simples recepção de um documento.

---

## 2. Estrutura documental e parser (`PyYAML`)

### 2.1 Codificação e limites físicos
- **Formato:** arquivo `.md` (ou texto Markdown colado), **UTF-8** válido, sem byte nulo (`\x00`), não vazio após remoção de BOM/espaços.
- **Limite físico do documento:** até **256.000 bytes** (`MAX_DOCUMENT_BYTES`).
- **Normalização proibida:** os bytes recebidos são preservados literalmente (incluindo BOM e CRLF/LF) para `sha256` e ancoragem em offsets de bytes UTF-8.

### 2.2 Anatomia e parser obrigatório (`PyYAML`)
O documento é composto por:
1. **Cabeçalho YAML Front Matter** delimitado por `---` na primeira linha e `---` no fechamento.
2. **Corpo Markdown** com seções estruturadas (`## ...` / `### ...`) e texto livre complementar.

**Requisitos estritos do parser:**
- Utilizar **`PyYAML`** como dependência instrumental com carregamento seguro (`SafeLoader` customizado) — **não** implementar parser YAML próprio.
- **Chaves duplicadas:** rejeitar explicitamente qualquer mapeamento com chave duplicada em qualquer nível do Front Matter.
- **Tipos inválidos:** rejeitar tipos YAML não previstos (ex.: tags customizadas, objetos arbitrários, booleanos onde se espera string, `NaN`/`Infinity`).
- **Campos desconhecidos:** rejeitar ou sinalizar explicitamente; nenhum campo desconhecido no esquema pode ser aceito silenciosamente como válido.
- **Versões incompatíveis:** `schema` diferente de `"BB-CORE-ING-0.2.0"` deve ser rejeitado com erro explícito de versão.
- **Limites de processamento:** limitar o tamanho do Front Matter (ex.: ≤ 64.000 bytes), profundidade máxima de aninhamento (ex.: ≤ 8 níveis) e quantidade de nós/itens (`records` ≤ 32 itens) antes/durante a interpretação.

### 2.3 Metadados do cabeçalho (Front Matter)

| Campo | Obrigatório | Tipo | Descrição |
| ----- | ----------- | ---- | --------- |
| `schema` | Sim | string | Deve ser exatamente `"BB-CORE-ING-0.2.0"`. |
| `document.external_id` | Não | string (≤ 240 B) | Identificador externo declarado do documento (nunca inferido do nome do arquivo). |
| `document.version` | Não | string (≤ 120 B) | Versão declarada do documento. |
| `document.declared_date` | Não | string (`YYYY-MM-DD`) ou `null` | Data declarada da produção do documento (distinta de `received_at`, atribuída pelo servidor). |
| `document.source_context` | Não | objeto | Distingue o artefato Markdown da fonte original (ver Seção 6). |
| `document.provenance` | Não* | string (≤ 4000 B) | Procedência declarada do documento (*pode ser complementada no ato do recebimento local). |
| `records` | Sim | lista (0 a 32 itens) | Lista declarada de registros intelectuais transportados. `[]` é válido. |

---

## 3. Conteúdo intelectual, formulação e autoria

### 3.1 Separação estrita entre formulação, autoria e confirmação
O contrato **não** confunde três dimensões distintas:
1. **Origem da formulação (`formulation_origin`):**
   - `DOCUMENT_EXCERPT`: preservação literal do trecho presente no corpo do Markdown parametrizado (prioritária neste contrato).
   - `HUMAN_FORMULATION`: formulação posteriormente elaborada/editada pelo humano no exame local.
   - `EXTERNAL_AI_ASSISTED`: formulação atribuída a assistência por IA em ambiente externo (**nunca** deve ser classificada automaticamente como `HUMAN_FORMULATION`).
2. **Autoria declarada (`attribution`):** quem formulou/propôs o conteúdo no ambiente de origem (ex.: pesquisador, diálogo com ChatGPT, autor externo), **não** autenticada civilmente.
3. **Confirmação humana (`confirmed_by_declared` + `confirmed: true`):** ato explícito do operador local autorizando a preservação no acervo do BB-CORE; não transforma texto de IA em autoria humana nem valida cientificamente o conteúdo.

### 3.2 Campos por item em `records`
A ausência legítima de informação é representada por `null`, `[]` ou omissão explícita sem inferência silenciosa:

| Campo | Obrigatório para confirmar | Descrição |
| ----- | -------------------------- | --------- |
| `id_local` | Sim (único no documento) | Identificador local do item no documento (ex.: `achado-01`). |
| `external_record_id` | Recomendado | Identificador intelectual declarado do registro (ex.: `BB-CORE-INSIGHT-001`), usado na detecção de reimportação e divergência. Se omitido e `document.external_id` existir, compõe-se a chave declarada `(document.external_id, id_local)`. |
| `kind` | Sim | `CONCEPTUAL_FINDING`, `METHODOLOGICAL_DECISION`, `OPEN_QUESTION` ou `EMPIRICAL_REPORT`. |
| `work_state` | Sim | Compatível com `kind` (`PROPOSED`, `ADOPTED`, `OPEN`, `REPORTED`). |
| `title` | Sim (≤ 240 B) | Título declarativo do registro. |
| `formulation_origin` | Sim | `DOCUMENT_EXCERPT` (padrão quando usa `claim_section`), `EXTERNAL_AI_ASSISTED` ou `HUMAN_FORMULATION`. |
| `claim_section` | Sim* | Nome exato do cabeçalho `## ...` no corpo Markdown contendo a formulação literal a ancorar em bytes UTF-8 (*ou `claim` literal único no documento). |
| `why_matters_section` / `why_matters` | Sim (≤ 4000 B) | Relevância declarada da preservação. |
| `limitations_section` / `limitations` | Sim (≤ 10000 B) | Limites epistemológicos, metodológicos e lacunas explícitas. |
| `genesis_section` / `genesis` | Não | Como o registro emergiu; desconhecidos explícitos. |
| `context` | Não | Escopo, referências externas e `missing` (lacunas de contexto/proveniência). |
| `attribution` | Não | `{ declared_author, declared_role, external_tool, verified: false }`. |
| `evidence` | Não | Evidências literais disponíveis e referências recuperáveis (IDs do BB-CORE ou trechos). |
| `open_questions` | Não | Lista de questões decorrentes (não cria registros automáticos fora de `records`). |
| `declared_relations` | Não | Relações explicitamente declaradas com IDs já existentes (`left_id`/`right_id`, `rationale`, `counterpoint`). |
| `supersedes_id` | Não | ID interno de registro anterior no BB-CORE quando se tratar de desdobramento explícito. |

---

## 4. Cardinalidade e não-inferência

- Um documento Markdown pode transportar **0, 1 ou vários** registros intelectuais autônomos (`records: []`, `[r1]` ou `[r1, r2, ...]`).
- Cada registro possui identidade própria e **confirmação individual e facultativa** (o operador pode confirmar `r1` e não confirmar `r2`).
- Compartilhar o mesmo documento **não** cria relação intelectual, causalidade ou influência entre `r1` e `r2`.

---

## 5. Cinco identidades distintas, reimportação e divergências

### 5.1 As cinco identidades
| Camada | Identidade | Onde vive / Exemplo | Papel |
| ------ | ---------- | ------------------- | ----- |
| 1. **Documento** | `document_id` + `external_id` + `declared_version` | `documents` / `document_versions` | Identifica o artefato documental e suas versões declaradas. |
| 2. **Conteúdo (bytes)** | `sha256` | `document_contents` | Identifica exatamente os bytes preservados. |
| 3. **Registro declarado** | `external_record_id` (ou `(document.external_id, id_local)`) | Registro de identidade declarada (adaptação SQLite necessária) | Identifica o objeto intelectual transportado entre documentos/versões. |
| 4. **Insight interno** | `insights.id` (UUID hex) | `insights` | Identidade canônica imutável dentro do BB-CORE. |
| 5. **Operação computacional** | `request_id` (UUID) | `requests` | Idempotência de requisição HTTP/API; **não** representa identidade intelectual. |

### 5.2 Regras de comportamento diante de reimportação e divergência
1. **Mesmo `request_id` + mesmo payload (retry HTTP):** idempotência computacional devolve o resultado anterior sem reprocessar.
2. **Mesmo `request_id` + payload diferente:** `409 Conflict` (violação de idempotência).
3. **Reimportação do mesmo documento (`sha256` igual, novo `request_id`):**
   - A camada documental registra novo recebimento (`outcome: RECEIVED_AGAIN`), preservando a nova procedência/ator.
   - Para cada registro em `records` cuja identidade declarada já foi confirmada anteriormente com o mesmo `claim_sha256`: o sistema informa **`ALREADY_CONFIRMED`** apontando para o `insight_id` existente e **impede duplicação silenciosa**.
4. **Mesmo `external_id` + mesma `declared_version` + `sha256` diferente:**
   - Gera `VERSION_CONFLICT` na camada documental, preservando o conteúdo divergente sem sobrescrever o original e bloqueando confirmação até exame explícito.
5. **Nova versão documental (`declared_version` diferente) com registro declarado já existente:**
   - Se a formulação (`claim_sha256`) for **idêntica** à já confirmada: reconhece como já preservada (`ALREADY_CONFIRMED`), podendo opcionalmente registrar novo vínculo de evidência se autorizado, sem duplicar o insight.
   - Se a formulação (`claim_sha256`) for **divergente**: sinaliza **`FORMULATION_DIVERGENCE`** entre a nova versão e o `insight_id` existente. **Nunca** revisa, sobrescreve ou substitui automaticamente o registro anterior; o operador decide se mantém, revisa explicitamente (`FORMULATION_REVISED`) ou cria novo registro desdobrado (`supersedes_id`).

> **Reavaliação de impacto no banco:** para sustentar as regras 3 e 5 sem duplicação silenciosa, **será necessária uma adaptação aditiva no SQLite** (tabela de mapeamento de identidades declaradas de registros importados → `insight_id` e `claim_sha256`), sem alterar o schema das tabelas existentes.

---

## 6. Proveniência: Markdown parametrizado vs. fonte original

O documento Markdown parametrizado é um **artefato de transporte/síntese**, não necessariamente a transcrição integral da fonte onde o achado emergiu (ex.: conversa no ChatGPT).

- `document.source_context` (e `context.missing`) deve distinguir:
  - `origin_kind` (ex.: `CHATGPT_CONVERSATION`, `RESEARCH_NOTE`, `EXTERNAL_DOCUMENT`)
  - `origin_reference` (identificador, título ou data da conversa/fonte original, se disponível)
  - `transcript_included` (`true` | `false` | `"PARTIAL"`)
  - `provenance_gaps` (lista explícita do que falta, ex.: ausência da transcrição completa da conversa).
- **Garantia explícita:** a integridade SHA-256 do arquivo Markdown **não** comprova que ele representa fielmente a conversa ou fonte externa que declara ter originado o achado.

---

## 7. Validação, estados e confirmação humana

Estados distintos do ciclo:
1. **`RECEIVED`**: bytes preservados em `document_contents` / `document_receipts`.
2. **`STRUCTURALLY_VALID`**: PyYAML seguro passou, `schema` compatível, sem chaves duplicadas, tipos e limites válidos.
3. **`INTERPRETED`**: registros candidatos extraídos deterministicamente com âncoras em bytes UTF-8 calculadas e confrontados com identidades já confirmadas (`NEW_CANDIDATE` | `ALREADY_CONFIRMED` | `FORMULATION_DIVERGENCE`). Nada gravado em `insights`.
4. **`CONFIRMED`**: gravação individual autorizada pelo operador (`confirmed: true`) para cada registro selecionado.

Nenhum conteúdo recebido é tratado como instrução executável. A interface apresenta o documento original, os parâmetros interpretados, as lacunas de proveniência, o status frente ao acervo existente e a ação explícita de confirmar (ou não) cada registro.
