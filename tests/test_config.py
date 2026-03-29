import os
import pytest
from app.core.config import get_settings, Settings


def test_default_values(setup_test_dirs):
    settings = get_settings()
    assert settings.environment == "development"
    assert settings.secret_key == "dev-secret-change-me"
    assert settings.max_upload_mb == 50
    assert settings.max_downloads == 50
    assert settings.document_ttl_days == 14
    assert settings.nuke_ttl_hours == 72
    assert settings.token_ttl_minutes == 30
    assert settings.cf_access_team_domain == ""
    assert settings.cf_access_aud == ""


def test_env_override(tmp_path):
    os.environ["SHIELD_ENVIRONMENT"] = "staging"
    os.environ["SHIELD_SECRET_KEY"] = "my-custom-secret"
    os.environ["SHIELD_MAX_UPLOAD_MB"] = "100"
    os.environ["SHIELD_MAX_DOWNLOADS"] = "10"
    os.environ["SHIELD_DOCUMENT_TTL_DAYS"] = "7"
    os.environ["SHIELD_NUKE_TTL_HOURS"] = "24"
    os.environ["SHIELD_TOKEN_TTL_MINUTES"] = "60"
    os.environ["SHIELD_CF_TEAM_DOMAIN"] = "myteam.cloudflareaccess.com"
    os.environ["SHIELD_CF_ACCESS_AUD"] = "abc123"
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.environment == "staging"
    assert settings.secret_key == "my-custom-secret"
    assert settings.max_upload_mb == 100
    assert settings.max_downloads == 10
    assert settings.document_ttl_days == 7
    assert settings.nuke_ttl_hours == 24
    assert settings.token_ttl_minutes == 60
    assert settings.cf_access_team_domain == "myteam.cloudflareaccess.com"
    assert settings.cf_access_aud == "abc123"

    # Cleanup
    for key in [
        "SHIELD_SECRET_KEY", "SHIELD_MAX_UPLOAD_MB", "SHIELD_MAX_DOWNLOADS",
        "SHIELD_DOCUMENT_TTL_DAYS", "SHIELD_NUKE_TTL_HOURS", "SHIELD_TOKEN_TTL_MINUTES",
        "SHIELD_CF_TEAM_DOMAIN", "SHIELD_CF_ACCESS_AUD",
    ]:
        os.environ.pop(key, None)
    get_settings.cache_clear()


def test_production_requires_secret_key(tmp_path):
    os.environ["SHIELD_ENVIRONMENT"] = "production"
    os.environ["SHIELD_SECRET_KEY"] = "dev-secret-change-me"
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="SHIELD_SECRET_KEY must be set in production"):
        Settings()

    os.environ["SHIELD_ENVIRONMENT"] = "development"
    get_settings.cache_clear()


def test_production_with_valid_secret(tmp_path):
    os.environ["SHIELD_ENVIRONMENT"] = "production"
    os.environ["SHIELD_SECRET_KEY"] = "secure-production-secret-key"
    get_settings.cache_clear()

    settings = Settings()
    assert settings.environment == "production"
    assert settings.secret_key == "secure-production-secret-key"

    os.environ["SHIELD_ENVIRONMENT"] = "development"
    os.environ.pop("SHIELD_SECRET_KEY", None)
    get_settings.cache_clear()


def test_db_url_uses_data_dir(tmp_path):
    os.environ["SHIELD_DATA_DIR"] = str(tmp_path)
    os.environ.pop("SHIELD_DB_URL", None)
    get_settings.cache_clear()

    settings = Settings()
    assert str(tmp_path) in settings.db_url
    assert "shield.db" in settings.db_url

    get_settings.cache_clear()
