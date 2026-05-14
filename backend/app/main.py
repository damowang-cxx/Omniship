import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.air_waybills import router as air_waybills_router
from app.routers.users import router as users_router
from app.routers.waybill_uploads import router as waybill_uploads_router
from app.services.air_waybill_scheduler import AirWaybillAutoRefreshScheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AirWaybillAutoRefreshScheduler(settings)
    app.state.air_waybill_scheduler = scheduler
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(
    title="Omniship Air Waybills PoC",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(air_waybills_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(waybill_uploads_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
