# Plano de evolução, por gates (sem escopo implícito)

Enquanto a integração pública estiver pendente, exercitar os processos locais com o [registro MÉTIS e o processo local](LOCAL-PROCESS.md), já preservado no acervo operacional.

## Gate 0 — validado pelos testes unitários locais
Captura explícita; integridade; idempotência; recuperação; busca textual; relação candidata; separação entre token de leitura/escrita.

## Ingestão documental local
Camada anterior à captura: bytes originais, versões declaradas, recebimentos, conflitos preservados e registros humanos com âncoras verificáveis. Ver [contrato e limites](DOCUMENT-INGESTION.md). Independente da integração pública.

## Gate 1 — integração real ChatGPT (P0)
Confirmar transporte e catálogo MCP com conta real e mecanismo de autenticação oferecido pelo cliente. Implementar OAuth 2.1 / PKCE conforme requisitos da plataforma ou gateway validado; observar rejeições e gravar logs sanitizados. Executar captura apenas após consentimento explícito, recuperar em segunda conversa. **Não alegar conclusão antes desse teste.**

## Gate 2 — cadeia de proveniência (P0)
Importação de conversas autenticáveis com IDs e timestamps quando disponíveis; fontes externas referenciadas, permissões granulares; páginas de origem e lacunas; modelo `insight_sources` ampliado para várias âncoras; avaliações humanas de pertinência, alcance e atenção.

## Gate 3 — conhecimento intersistemas (P1)
Autorização por sujeito, sistema, coleção, papel e ação; políticas de exportação por fonte; APIs com filtragem obrigatória, trilhas de acesso e revogação; evitar que conteúdo privado apareça em respostas do MCP ou índices para sistemas não autorizados.

## Gate 4 — continuidade (P1)
Detecção opcional de insights relacionados; recuperação semântica como candidata; contrapontos e critérios de novidade; benchmark com avaliações humanas. Sem governança automática de verdade, influência ou ações externas.

## Não fazer no MVP-0
Agentes permanentes, crawling de conversas, vigilância, importação implícita de mensagens privadas, criação de grafos causais por similaridade, vetores sem teste de necessidade, hospedagem pública direta, endpoints de execução nos sistemas consumidores.
