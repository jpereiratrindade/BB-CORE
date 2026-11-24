# Relatório Técnico e Conceitual — `BB-CORE-EXP-003` v0.2.0

**Data de execução:** 24/11/2026 (`2026-11-24T21:01:05Z` UTC)  
**Natureza:** Investigação experimental da capacidade de descoberta semântica e abstração intelectual (isolada do núcleo canônico)  
**Script executor:** [`lab/exp003/run_exp003.py`](run_exp003.py)  
**Dados brutos integrais:** [`lab/exp003/results.json`](results.json)

---

## 1. O que foi efetivamente descoberto sobre o acervo real

Submetidos os 6 registros reais (`002`–`007`) às estratégias A (leitura integral), B (vizinhança semântica), C (transversal distante), D (incremental com estado determinístico) e à confrontação crítica independente (E), **apenas uma proposição transversal sobreviveu integralmente ao exame crítico como candidata sustentada (`SUSTAINED_CANDIDATE`)**:

### Descoberta sustentada (`D-01` — Estratégia A)
- **Título:** *Integração entre a preservação de contextos e continuidade intelectual* (`CONCEPTUAL_DISCOVERY`)
- **Formulação:** A integração entre a independência da organização dos objetos preservados (`002`), a distinção entre existência e conteúdo recuperável de um acontecimento (`005`) e a retomada do contexto de origem (`007`) permite sustentar a continuidade intelectual **tanto pelo conteúdo quanto pelo contexto de atividade que o gerou**.
- **Registros e trechos literais verificados (`3/3` `exact_match: true`):**
  - `002` (*A organização da memória não determina a organização da atividade intelectual*)
  - `005` (*A recuperação de um acontecimento exige distinguir sua existência de seu conteúdo intelectual*)
  - `007` (*Continuidade intelectual pela retomada do contexto de origem*)
- **Veredito da confrontação crítica (E):** `SUSTAINED_CANDIDATE` (`already_explicit_in_single_record: false`, `merely_summary_or_classification: false`, `depends_on_integration: true`, `adds_comprehension_or_investigation: true`).

### Descoberta transversal candidata (`D-01` — Estratégia C, registros distantes)
- **Título:** *Complementaridade entre reconhecimento de identidade e continuidade intelectual*
- **Registros:** `003` (*Reconhecimento de identidade...*) e `007` (*Continuidade intelectual...*), com `3/4` trechos literais exatos (1 trecho omitiu `"limitações,"`).
- **Relevância:** explicita uma tensão produtiva entre **retomar o contexto original (`007`)** e **não presumir que o reconhecimento de identidade equivale à confirmação integral do conteúdo (`003`)** — tensão que fundamenta diretamente o cuidado com referências externas não transcritas.

### Proposições rejeitadas pela confrontação crítica (`WEAK_OR_REDUNDANT`)
- Todas as 5 proposições geradas na **Estratégia D (incremental)** (`INC-01` a `INC-05`) foram classificadas pelo revisor crítico (E) como **`WEAK_OR_REDUNDANT`**: embora bem redigidas e com estado preservado sem *state drift*, constituíam reformulações diretas de um único registro (`depends_on_integration: false`).
- Na **Estratégia B (vizinhança semântica)**, a abstração proposta apoiou-se apenas em `002`, não realizando síntese multi-registro apesar de receber `002`, `005` e `007`.

---

## 2. Representações semânticas investigadas (`qwen3-embedding:4b`)

| Representação | Tempo (6 registros) | Par mais próximo (cosseno) | Par mais distante (cosseno) |
|---|---:|---|---|
| **Registro integral** | `4,69 s` | `002 ↔ 007` (`0.7643`) | `006 ↔ 007` (`0.4394`) |
| **`claim` (formulação)** | `0,47 s` | `002 ↔ 007` (`0.6457`) | — |
| **`why_matters`** | `0,30 s` | — | — |
| **`limitations`** | `0,32 s` | — | — |

**Observações:**
1. O espaço vetorial identificou corretamente a afinidade conceitual entre `002` e `007` (`0.7643`), `003` e `004` (`0.7344`) e `005` e `007` (`0.7317`), e isolou `006` (*Suficiência funcional...*, decisão metodológica de escopo) como o registro mais distante (`0.4394`–`0.5394`).
2. Contudo, a proximidade vetorial **não garantiu** síntese na Estratégia B (que colapsou em `002`), enquanto a distância vetorial na Estratégia C permitiu articular `003 ↔ 007`. Isso confirma que embeddings são úteis como **mecanismo auxiliar de seleção de contexto**, nunca como substituto da integração analítica nem como critério único de agrupamento.

---

## 3. Comparação entre estratégias e custos computacionais

| Estratégia | Tempo (s) | Resultado principal | Diagnóstico metodológico |
|---|---:|---|---|
| **Embeddings (`qwen3-embedding:4b`)** | `5,77 s` | Matriz de similaridade integral e por campo | Custo muito baixo; ordenação coerente, mas insuficiente sozinha para descoberta. |
| **A — Leitura integral (`qwen2.5:14b`)** | `25,68 s` | 1 descoberta sustentada (`D-01`: `002+005+007`) | Melhor relação custo/qualidade para acervos que cabem na janela de contexto. |
| **B — Vizinhança semântica** | `11,78 s` | 1 abstração restrita a `002` | Risco de redundância em vizinhanças muito próximas. |
| **C — Transversal distante** | `20,24 s` | 1 complementaridade (`003+007`) | Útil para evitar bolhas de similaridade semântica. |
| **D — Incremental (estado externo)** | `90,26 s` | 5 descobertas individuais (`INC-01..05`) + 2 `ADD_GROUND` | Eliminou o *state drift* do `EXP-001`, mas tendeu a reformular cada registro isoladamente. |
| **E — Confrontação crítica** | — (incluída no fluxo) | 1 `SUSTAINED_CANDIDATE`, 5 `WEAK_OR_REDUNDANT` | **Indispensável:** filtrou automaticamente 100% das pseudo-descobertas redundantes de D. |

---

## 4. Arquitetura para escalabilidade e operação contínua (proposta)

Com base nos resultados de `EXP-001`, `EXP-002` e `EXP-003`:
1. **Indexação semântica incremental (barata):** ao confirmar um registro ou revisão (`FORMULATION_REVISED`), gerar embeddings (`qwen3-embedding:4b`) fora da transação SQLite canônica (~0,8 s por registro).
2. **Recuperação híbrida de contexto (evitando `O(n²)`):** selecionar `k` vizinhos semânticos próximos (Estratégia B) **+** `m` registros distantes/transversais (Estratégia C), evitando tanto a leitura integral quanto a comparação exaustiva de pares do `EXP-002`.
3. **Síntese + Confrontação obrigatória:** toda descoberta candidata proposta pela LLM deve passar por uma etapa independente de confrontação (Estratégia E) e verificação determinística de trechos antes de ser apresentada ao pesquisador.
4. **Representação exploratória centrada em descobertas:** em vez de forçar todas as conexões num grafo par-a-par denso (`EXP-002`), exibir **Descobertas Candidatas Sustentadas** como nós de síntese navegáveis em dois sentidos:
   - *Descoberta → registros e trechos que a fundamentam*;
   - *Registro → descobertas sustentadas que dele dependem*, mantendo a rede de registros, a referência lexical e o calendário como perspectivas complementares.
