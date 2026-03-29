import time
import pytest
import jwt as pyjwt

from app.middleware.cf_access import validate_cf_access_token


def make_hs256_token(payload: dict, secret: str = "test-secret") -> str:
    return pyjwt.encode(payload, secret, algorithm="HS256")


SECRET = "test-secret"


def test_valid_token():
    """HS256 JWT mit email wird in dev_mode korrekt dekodiert."""
    payload = {"email": "user@example.com", "sub": "user-123", "exp": int(time.time()) + 3600}
    token = make_hs256_token(payload, secret=SECRET)
    claims = validate_cf_access_token(token, dev_mode=True, key=SECRET)
    assert claims["email"] == "user@example.com"
    assert claims["sub"] == "user-123"


def test_expired_token_dev_mode_still_works():
    """In dev_mode, expired tokens are accepted (signature+expiry skipped)."""
    payload = {"email": "user@example.com", "sub": "user-123", "exp": int(time.time()) - 10}
    token = make_hs256_token(payload, secret=SECRET)
    # Dev mode skips all validation — expired tokens still work
    claims = validate_cf_access_token(token, dev_mode=True)
    assert claims["email"] == "user@example.com"


def test_dev_mode_no_token():
    """None-Token in dev_mode gibt dev@localhost zurück."""
    result = validate_cf_access_token(None, dev_mode=True)
    assert result["email"] == "dev@localhost"
    assert result["sub"] == "dev-user"


def test_production_no_token():
    """None-Token in production wirft ValueError."""
    with pytest.raises(ValueError, match="CF Access token missing"):
        validate_cf_access_token(None, dev_mode=False)
