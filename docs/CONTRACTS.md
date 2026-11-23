# Contratos e invariantes — BB-INSIGHT-1

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
