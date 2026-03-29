import jwt
import httpx

_jwks_cache: dict = {}


def _get_cf_public_keys(team_domain: str) -> list:
    """Fetch CF Access public keys from JWKS endpoint. Cached in memory."""
    if team_domain in _jwks_cache:
        return _jwks_cache[team_domain]

    url = f"https://{team_domain}/cdn-cgi/access/certs"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    public_keys = []
    for key_data in data.get("public_certs", []):
        public_keys.append(key_data["cert"])
    # Also try keys array (alternative format)
    for key_data in data.get("keys", []):
        public_keys.append(jwt.algorithms.RSAAlgorithm.from_jwk(key_data))

    _jwks_cache[team_domain] = public_keys
    return public_keys


def validate_cf_access_token(
    token, dev_mode=False, audience="", key="", team_domain=""
):
    if token is None:
        if dev_mode:
            return {"email": "dev@localhost", "sub": "dev-user"}
        raise ValueError("CF Access token missing")
    try:
        if dev_mode:
            options = {
                "verify_signature": False,
                "verify_aud": False,
                "verify_iss": False,
            }
            return jwt.decode(token, options=options, algorithms=["RS256", "HS256"])

        # Production: validate against CF Access public keys
        if team_domain:
            public_keys = _get_cf_public_keys(team_domain)
            for pub_key in public_keys:
                try:
                    return jwt.decode(
                        token,
                        key=pub_key,
                        algorithms=["RS256"],
                        audience=audience if audience else None,
                    )
                except (jwt.InvalidSignatureError, jwt.InvalidKeyError):
                    continue
            raise ValueError("CF Access token signature could not be verified")

        # Fallback: no team_domain configured
        return jwt.decode(
            token,
            key=key,
            algorithms=["RS256", "HS256"],
            options={"verify_signature": False},
            audience=audience if audience else None,
        )

    except jwt.ExpiredSignatureError:
        raise ValueError("CF Access token expired or invalid")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"CF Access token invalid: {e}")
