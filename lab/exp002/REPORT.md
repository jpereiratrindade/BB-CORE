# Relatório Técnico e Conceitual — `BB-CORE-EXP-002` v0.1.0

**Data de execução:** 24/11/2026 (`2026-11-24T20:43:32Z` UTC)  
**Natureza:** Análise experimental par-a-par de conexões intelectuais com LLM local (isolada do núcleo canônico)  
**Script executor:** [`lab/exp002/run_exp002.py`](run_exp002.py)  
**Dados brutos integrais:** [`lab/exp002/results.json`](results.json)

---

## 1. Universo e protocolo

- **Registros analisados:** os 6 registros reais do acervo (`002` a `007`), formando **15 pares distintos** (`C(6, 2) = 15`).
- **Confrontação de estabilidade:** cada par foi avaliado duas vezes — em ordem direta `(A, B)` e em ordem inversa `(B, A)` — totalizando **30 inferências** sem taxonomias, léxicos, tipologias obrigatórias ou pontuações numéricas.
- **Modelo e infraestrutura:** `qwen2.5:14b` (`temperature: 0.1`, `num_ctx: 16384`, JSON Schema nativo via Ollama, `100% GPU` em AMD Radeon RX 7900, `12 GB` VRAM).
- **Custos computacionais observados:** `180,98 s` (~3 min) no total das 30 chamadas; `25.000` tokens de prompt; `12.253` tokens gerados.

---

## 2. Resultados das 15 análises e confrontação de estabilidade

| Classificação de estabilidade | Quantidade de pares | Pares |
|---|---:|---|
| **`CONCORDANT_CONNECTED`** (proposta nas duas ordens) | 14 | 01, 02, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15 |
| **`DIVERGENT_ORDER_DEPENDENT`** (abstenção em uma ordem, conexão na outra) | 1 | **Par 03** (`002` ↔ `003`) |
| **`CONCORDANT_ABSTAINED`** (abstenção nas duas ordens) | 0 | — |

### Análise da divergência observada (Par 03: `002` ↔ `003`)
- **Ordem direta `(002 → 003)`:** `connection_proposed: false`. O modelo absteve-se explicitamente: *"Os registros tratam de aspectos distintos da organização e preservação dos objetos intelectuais, sem compartilhamento substantivo de ideias ou temas que justifiquem uma conexão relevante entre eles."*
- **Ordem inversa `(003 → 002)`:** `connection_proposed: true`. O modelo propôs conexão argumentando que ambos distinguem aspectos fundamentais da interação e preservação de objetos intelectuais.
- **Preservação na rede:** conforme a instrução, a divergência foi preservada integralmente (`DIVERGENT_ORDER_DEPENDENT`) e destacada visualmente com linha tracejada âmbar na interface.

---

## 3. Validação determinística de existência e trechos literais

- **Existência dos registros:** 100% dos IDs e versões (`1`) conferidos contra o acervo canônico do BB-CORE.
- **Correspondência literal dos trechos citados:** **`56 / 60` (`93,3%`)** dos trechos citados coincidiram exatamente com o texto original dos registros.
- **Os 4 trechos com divergência textual (`exact_match: false`):**
  - **Par 04 (`reverse_ba`, A e B):** o modelo abreviou passagens longas usando reticências (`...`).
  - **Par 10 (`reverse_ba`, A) e Par 14 (`forward_ab`, A):** o modelo omitiu a palavra `"limitações,"` ao transcrever uma enumeração de `003`.
  - Na interface (`web/analytics.js`), esses 4 trechos são marcados com `⚠` (borda âmbar) para exame humano, enquanto os 56 exatos recebem `✓`.

---

## 4. Avaliação crítica: limitações e viés conectivo observado

1. **Viés conectivo (*connectivity bias*) em corpus tematicamente próximo:**
   - Embora instruído a não confundir tema genérico com conexão intelectual, o modelo propôs conexão em **14 de 15 pares** (e em 1 direção do Par 03), com **0 abstenções concordantes**.
   - Em pares envolvendo `006` (*Suficiência funcional...*, Pares 04, 11, 13), várias justificativas recorreram a formulações amplas (*"Ambos os registros abordam aspectos fundamentais do desenvolvimento e uso do BB-CORE..."*), aproximando-se do compartilhamento temático genérico que o protocolo buscava evitar.
   - Consequência topológica: na rede resultante, todos os 6 registros formam um único componente conexo denso (14 arestas concordantes + 1 divergente, 0 nós isolados).
2. **Qualidade heterogênea das conexões:**
   - Conexões como `002 ↔ 007` (separação memória/atividade vs. retomada do contexto de origem) e `003 ↔ 004` (identidade vs. fidelidade da representação) têm fundamentação conceitual forte e específica; já conexões como `003 ↔ 006` são mais genéricas.
3. **Implicação para a próxima etapa:**
   - Para evitar redes excessivamente densas por viés conectivo, recomenda-se testar critérios mais estritos de abstenção (ex.: exigir explicitação de *como* um registro altera, fundamenta, limita ou tensiona o outro, rejeitando justificativas meramente temáticas do tipo *"ambos tratam do BB-CORE"*), além de comparar com `gemma3:12b` e incluir registros de domínios distintos (como o documento MÉTIS).

---

## 5. Integração com a `BB-CORE-UI-001` v0.2.0

Os resultados reais de [`lab/exp002/results.json`](results.json) foram integrados de forma somente-leitura em [`bbcore/analytics.py`](../../bbcore/analytics.py) e [`web/analytics.js`](../../web/analytics.js):
- Nós exibidos como **cards compactos** com título, tipo, prefixo de ID e contagem de conexões/estado isolado.
- Distinção visual entre conexões concordantes (linha contínua), conexões divergentes entre `(A,B)` e `(B,A)` (linha tracejada âmbar) e relações registradas (`relations`, linha azul-marinho), sem atribuir intensidades numéricas arbitrárias.
- Pan, zoom (`+`, `−`, `Ajustar`), modo expandido, exploração de vizinhança, inspeção completa de trechos (`✓`/`⚠`), justificativas e limitações, além do botão para abrir o card integral e sua trajetória `BB-EVENT-1`.
- Referência lexical `v0.1.0` e calendário GitHub com seleção cruzada preservados intactos.
