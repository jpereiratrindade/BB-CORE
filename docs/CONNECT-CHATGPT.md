# BB-CORE v0.2 — domínio + HTTPS + OAuth externo

## Decisão de segurança

O BB-CORE NÃO implementa um provedor OAuth artesanal. Ele verifica tokens JWT assinados (RS256/ES256) de um IdP existente, usando JWKS remoto, issuer, audience e scopes. **A integração real depende de um IdP compatível com o fluxo OAuth 2.1 do ChatGPT (authorization code + PKCE S256, registro de cliente CIMD/DCR ou cliente predefinido, refresh tokens).** Não use token estático local como autenticação remota do ChatGPT.

## Parâmetros necessários

| Parâmetro | Exemplo | Obrigatório |
|---|---|---|
| Domínio FQDN | bb.seudominio.com | sim |
| DNS | A/AAAA para proxy HTTPS | sim |
| Proxy | Nginx/HAProxy com TLS válido | sim |
| Conexão proxy → BB | 127.0.0.1:8789 se no mesmo host | sim |
| BB_PUBLIC_URL | https://bb.seudominio.com | sim |
| BB_OAUTH_ISSUER | https://id.seudominio.com/realms/bb | sim |
| BB_OAUTH_JWKS_URL | https://id.seudominio.com/.../certs | sim |
| Audience do access token | https://bb.seudominio.com | sim |
| Scopes OAuth | bb.read, bb.write, offline_access | sim |
| IdP | OAuth 2.1 + PKCE S256 + CIMD/DCR/predefined | sim |
| Certificado | CA pública e renovação | sim |
| Firewall | apenas 443 no proxy, nunca 8789 público | sim |

**IMPORTANTE:** o access token deve ser um JWT assinado com `iss`, `aud`, `sub`, `exp`, e `scope` (`bb.read` ou `bb.write`); tokens opacos não são suportados neste adaptador. O servidor NÃO confia em X-Forwarded-User. O IdP deve emitir audience exata `BB_PUBLIC_URL`. Se o IdP não suportar isso, NÃO ative o endpoint público.

## Instalação sem sobrescrever o banco

1. Copie o patch para o repositório já instalado, preservando os arquivos existentes.
2. Rode `python3 -m unittest discover -s tests -v`.
3. Configure IdP, DNS, TLS e proxy (exemplo em `deploy/nginx-bbcore.conf.example`).
4. No host Fedora (não no Toolbox):

```bash
cd /run/media/jpereiratrindade/labeco10T/dev/cpp/bb-core
export BB_PUBLIC_URL='https://bb.seudominio.com'
export BB_OAUTH_ISSUER='https://id.seudominio.com/realms/bb'
export BB_OAUTH_JWKS_URL='https://id.seudominio.com/realms/bb/protocol/openid-connect/certs'
bash scripts/configure-oauth.sh
```

O script cria `.venv` no projeto, instala PyJWT[crypto] e adiciona drop-in systemd. Não altera `secret.env`, banco ou tokens. Precisa de acesso ao índice de pacotes Python. Em Silverblue, o venv requer suporte `venv` e `pip` no Python do host.

## Verificações

```bash
systemctl --user status bb-core
curl -i https://bb.seudominio.com/.well-known/oauth-protected-resource
curl -i https://bb.seudominio.com/mcp
curl -i https://bb.seudominio.com/health  # deve retornar 404
```

`/mcp` sem token deve responder `401` com `WWW-Authenticate` indicando o recurso. Não envie os tokens locais ao ChatGPT nem exponha a interface web.

No ChatGPT, se sua conta/workspace permitir: Plugins → Adicionar servidor MCP personalizado → URL `https://bb.seudominio.com/mcp` → OAuth → revisar ferramentas. Para escrita, a autorização OAuth deve conceder `bb.write`; somente leitura usa `bb.read`. Exija aprovação humana para capturas e relações.

## Limites explícitos

- A captura NÃO acessa o histórico completo do ChatGPT automaticamente.
- O IdP é uma dependência de infraestrutura ainda a configurar.
- O fluxo OAuth não foi testado com uma conta real do ChatGPT neste pacote.
- O backend continua single-user; não habilite múltiplos usuários sem isolamento por sujeito.
- Uma instância de Nginx em outro host não consegue usar `127.0.0.1` da workstation; será necessário túnel privado ou transporte protegido até o Fedora. NÃO vincule o backend a 0.0.0.0.
- Proteja o endpoint com rate limiting, monitoração e backup; revise logs para não registrar conteúdo sensível.
