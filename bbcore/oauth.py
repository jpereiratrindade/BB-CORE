"""Verificação de access tokens OAuth RS256/ES256 emitidos por IdP externo.

Não emite tokens. Não aceita JWT sem assinatura nem confia em cabeçalhos de identidade do proxy.
"""
import os
import threading

class OAuthVerifier:
    def __init__(self, issuer, audience, jwks_url):
        if not (issuer.startswith("https://") and jwks_url.startswith("https://") and audience.startswith("https://")):
            raise ValueError("Issuer, JWKS e audience devem usar HTTPS")
        try:
            import jwt
        except ImportError as e:
            raise RuntimeError("Instale PyJWT[crypto] no venv do BB-CORE") from e
        self.jwt = jwt
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.jwks = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)
        self.lock = threading.Lock()

    def scopes(self, token):
        try:
            with self.lock:
                key = self.jwks.get_signing_key_from_jwt(token).key
            claims = self.jwt.decode(
                token, key, algorithms=["RS256","ES256"],
                issuer=self.issuer, audience=self.audience,
                options={"require":["exp","iss","aud","sub"]},
                leeway=30,
            )
            raw = claims.get("scope", "")
            if isinstance(raw, str):
                return set(raw.split())
            # Alguns IdPs usam scp como lista, mas não aceitamos outros formatos arbitrários.
            raw = claims.get("scp", [])
            return set(raw) if isinstance(raw, list) and all(isinstance(x,str) for x in raw) else set()
        except Exception:
            return set()
