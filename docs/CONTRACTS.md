# Contratos e invariantes — BB-INSIGHT-1

## Fundamento da continuidade intelectual

Todo insight nasce como um registro intelectualmente autônomo, identificado e sustentado por fontes recuperáveis. Sua evolução é contingente e somente pode ser reconstruída a partir de acontecimentos efetivamente registrados. Suas relações com outros insights não são presumidas: podem ser propostas, examinadas, contestadas ou reconhecidas posteriormente, com proveniência e histórico preservados.

Proveniência, trajetória e relações são dimensões independentes. O contrato [BB-EVENT-1](EVENTS.md) define eventos append-only e sua reprodução, sem criar trajetórias retrospectivas fictícias.

## Identidade

- Cada insight tem ID aleatório, título, formulação candidata, gênese estruturada, contexto delimitado, limites, status e versão.
- Toda captura tem `request_id` UUID e assinatura do conteúdo para operação idempotente. Novo conteúdo com UUID anterior gera conflito.
- Cada fonte é ocorrência própria com texto literal e hash SHA-256. Bytes coincidentes NÃO constituem fontes independentes.
- Âncoras usam offsets em bytes UTF-8, verificadas contra corpo e `quote` ao consultar o contexto.
- Versões têm histórico em `revisions`; MVP-0 só cria v1. Revisões futuras não podem sobrescrever v1.
- Relações são candidatas, com justificativa e contraponto; não representam causalidade reconhecida.
- `genesis` contém informações atribuídas ao diálogo; desconhecidos permanecem `null`, nunca preenchidos por dedução temporal.

## Exemplo JSON de captura

```json
{
  "request_id": "9d0c89bb-6881-40f1-ae6e-ed2bf6f46f5e",
  "title": "Memória e contexto",
  "claim": "Uma síntese isolada não preserva a gênese de uma compreensão",
  "why_matters": "Permite reconstrução crítica posterior",
  "genesis": {"trigger": "Diálogo sobre BB", "previous_position": null,
              "turning_point": "Exigência de guardar bases"},
  "context": {"coverage": "PARTIAL_DIALOGUE",
              "missing": ["Exportação integral da conversa"]},
  "limitations": "Interpretação candidata. Sem cronologia autenticada.",
  "status": "INFERRED_CANDIDATE",
  "sharing": "PRIVATE",
  "sources": [{"text": "Precisamos guardar o contexto que tornou possível entender.",
               "quote": "guardar o contexto", "origin": "dialogo-citado",
               "author": "user (declarado)", "coverage": "LITERAL_EXCERPT",
               "role": "trigger"}]
}
```

## Fontes não confiáveis

Recuperação é operação de leitura de dados, não instrução operacional para o ChatGPT ou outros sistemas. Conteúdo de fontes nunca concede novas permissões ou autoria.

## Estados

`INFERRED_CANDIDATE` significa hipótese interpretativa; `REPORTED` é alegação atribuída; `DISPUTED` indica contestação; `WITHDRAWN` retira pertinência do enunciado. Nenhum status implica mérito científico certificado. O MVP não implementa transições desses estados.

## Segurança e escopo

Leitura e escrita exigem Bearer distintos e Origin explícita deve estar na allowlist. Tokens são autoridade integral sobre o acervo, portanto o rótulo `SCOPED` não disponibiliza ACL: compartilhamento intersistemas deve permanecer desabilitado. O arquivo SQLite deve ser protegido pelo SO e por backup privado.

## Documentos e elaboração humana

A camada documental independente e as regras de recebimento, conflitos, âncoras e confirmação estão em [DOCUMENT-INGESTION.md](DOCUMENT-INGESTION.md). Seus registros podem referenciar vários documentos. Recebimento não equivale a elaboração, decisão adotada não equivale a validação científica, e confirmação declarada não autentica autoria.

## Exportação e continuidade explícita (`BB-CORE-EXP-0.1.0` / `BB-CORE-CONT-0.1.0`)

O contrato de exportação `BB-CORE-EXP-0.1.0` (`GET /api/insights/{id}/export.md`) suporta dois modos explícitos, mantendo compatibilidade retroativa com exportações anteriores:

- **Exportação para consulta (`mode=export`, padrão):** emite `document_role: "EXPORTED_RECORD"` com identidade, formulação original vs. corrente, fontes ancoradas, limitações, proveniência e trajetória `BB-EVENT-1`.
- **Pacote de continuidade (`mode=continuity`, extensão `BB-CORE-CONT-0.1.0`):** mantém `export_schema: "BB-CORE-EXP-0.1.0"`, acrescenta `continuity_extension: "BB-CORE-CONT-0.1.0"`, `document_role: "CONTINUITY_PACKET"` e o bloco estruturado `continuity` no frontmatter (`operation`, `reference_system`, `insight_id`, `title`, `record_version`, `trajectory_point`, `retrieved_at`, `origin_reference`, `origin_status`, `purpose`, `context_gaps`), além da seção inicial **Declaração explícita de continuidade** e do pedido de reconhecimento inicial antes das fontes.

Nenhuma operação de consulta, exportação, cópia para área de transferência ou abertura de conversa no ambiente externo produz acontecimentos no diário `BB-EVENT-1`, cria novos registros ou altera a identidade/formulação preservada.
