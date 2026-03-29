import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.fixture(autouse=True)
def setup_test_dirs(tmp_path):
    os.environ["SHIELD_DATA_DIR"] = str(tmp_path)
    os.environ["SHIELD_DB_URL"] = f"sqlite+aiosqlite:///{tmp_path}/db/test.db"
    os.environ["SHIELD_ENVIRONMENT"] = "development"
    os.makedirs(f"{tmp_path}/uploads", exist_ok=True)
    os.makedirs(f"{tmp_path}/outputs", exist_ok=True)
    os.makedirs(f"{tmp_path}/db", exist_ok=True)
    # Clear settings cache for fresh config per test
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
