import os
from functools import lru_cache


class Settings:
    def __init__(self):
        self.environment = os.getenv("SHIELD_ENVIRONMENT", "development")
        self.secret_key = os.getenv("SHIELD_SECRET_KEY", "dev-secret-change-me")
        self.data_dir = os.getenv("SHIELD_DATA_DIR", "/data")
        self.db_url = os.getenv("SHIELD_DB_URL", f"sqlite+aiosqlite:///{self.data_dir}/db/shield.db")
        self.max_upload_mb = int(os.getenv("SHIELD_MAX_UPLOAD_MB", "50"))
        self.max_downloads = int(os.getenv("SHIELD_MAX_DOWNLOADS", "50"))
        self.document_ttl_days = int(os.getenv("SHIELD_DOCUMENT_TTL_DAYS", "14"))
        self.nuke_ttl_hours = int(os.getenv("SHIELD_NUKE_TTL_HOURS", "72"))
        self.token_ttl_minutes = int(os.getenv("SHIELD_TOKEN_TTL_MINUTES", "30"))
        self.cf_access_team_domain = os.getenv("SHIELD_CF_TEAM_DOMAIN", "")
        self.cf_access_aud = os.getenv("SHIELD_CF_ACCESS_AUD", "")
        if self.environment == "production" and self.secret_key == "dev-secret-change-me":
            raise ValueError("SHIELD_SECRET_KEY must be set in production")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
