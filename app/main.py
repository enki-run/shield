import asyncio
import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import close_db, get_session_factory, init_db
from app.core.logging import setup_logging
from app.services.cleanup_service import CleanupService

logger = structlog.get_logger()
_cleanup_task = None


async def _run_cleanup_loop():
    settings = get_settings()
    cleanup = CleanupService(nuke_ttl_hours=settings.nuke_ttl_hours)
    while True:
        try:
            await asyncio.sleep(900)
            factory = get_session_factory()
            if factory:
                async with factory() as db:
                    deleted = await cleanup.cleanup(db)
                    if deleted > 0:
                        logger.info("cleanup.completed", deleted=deleted)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("cleanup.error", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    settings = get_settings()
    setup_logging(settings.environment)
    os.makedirs(f"{settings.data_dir}/uploads", exist_ok=True)
    os.makedirs(f"{settings.data_dir}/outputs", exist_ok=True)
    os.makedirs(f"{settings.data_dir}/db", exist_ok=True)
    await init_db(settings.db_url)
    _cleanup_task = asyncio.create_task(_run_cleanup_loop())
    yield
    _cleanup_task.cancel()
    await close_db()


app = FastAPI(title="Shield", version="1.0.0", lifespan=lifespan)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


from app.api.documents import router as documents_router
from app.api.download import router as download_router

app.include_router(documents_router)
app.include_router(download_router)

# Static files (frontend build)
static_dir = os.path.join(os.path.dirname(__file__), "static")


@app.get("/")
async def root():
    return RedirectResponse(url="/app/")


if os.path.exists(static_dir):
    from fastapi.responses import FileResponse as _FileResponse

    MIME_TYPES = {
        ".js": "application/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".json": "application/json",
        ".woff2": "font/woff2",
        ".woff": "font/woff",
    }

    # Mount static assets directory directly for /app/assets/*
    app.mount("/app/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="static-assets")

    # Favicon and other root-level static files
    @app.get("/app/favicon.svg")
    async def favicon():
        return _FileResponse(os.path.join(static_dir, "favicon.svg"), media_type="image/svg+xml")

    @app.get("/app/icons.svg")
    async def icons():
        path = os.path.join(static_dir, "icons.svg")
        if os.path.exists(path):
            return _FileResponse(path, media_type="image/svg+xml")
        return _FileResponse(os.path.join(static_dir, "index.html"), media_type="text/html")

    # SPA catch-all — must be AFTER specific static routes
    @app.get("/app/{path:path}")
    async def spa_catchall(path: str):
        return _FileResponse(os.path.join(static_dir, "index.html"), media_type="text/html")

    @app.get("/app/")
    async def spa_root():
        return _FileResponse(os.path.join(static_dir, "index.html"), media_type="text/html")
