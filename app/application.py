from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .analytics import router as analytics_router
from .api.routers import ROUTERS, ROUTER_MODULES
from .config import settings
from .core.legacy import (
    MEDIA_ROOT,
    database_not_configured_handler,
    http_exception_handler,
    log_requests,
    shutdown,
    startup,
    unhandled_exception_handler,
)
from .database import DatabaseNotConfiguredError
from .wearables import router as wearables_router


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.include_router(wearables_router)
    app.include_router(analytics_router)
    app.mount("/media", StaticFiles(directory=MEDIA_ROOT), name="media")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(log_requests)
    app.add_exception_handler(DatabaseNotConfiguredError, database_not_configured_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.on_event("startup")(startup)
    app.on_event("shutdown")(shutdown)

    for router in ROUTERS:
        app.include_router(router)

    return app
