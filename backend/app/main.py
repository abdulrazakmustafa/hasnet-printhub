import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.payment_gateway import sync_pending_payments

logger = logging.getLogger("hph.payment_reconciler")


async def _run_payment_reconciler(stop_event: asyncio.Event) -> None:
    startup_delay = settings.payment_reconcile_startup_delay_seconds
    if startup_delay > 0:
        await asyncio.sleep(startup_delay)

    while not stop_event.is_set():
        db = SessionLocal()
        try:
            synced = sync_pending_payments(db, limit=settings.payment_reconcile_batch_limit)
            if synced > 0:
                logger.info("Payment reconciler synced %s pending payment(s).", synced)
        except Exception:
            db.rollback()
            logger.exception("Payment reconciler iteration failed.")
        finally:
            db.close()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.payment_reconcile_interval_seconds)
        except asyncio.TimeoutError:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_event: asyncio.Event | None = None
    task: asyncio.Task[None] | None = None

    if settings.payment_reconcile_enabled:
        stop_event = asyncio.Event()
        task = asyncio.create_task(_run_payment_reconciler(stop_event))
        logger.info(
            "Payment reconciler started (interval=%ss, limit=%s).",
            settings.payment_reconcile_interval_seconds,
            settings.payment_reconcile_batch_limit,
        )

    yield

    if stop_event is not None and task is not None:
        stop_event.set()
        await task
        logger.info("Payment reconciler stopped.")


app = FastAPI(title=settings.project_name, debug=settings.debug, lifespan=lifespan)
app.include_router(api_router, prefix=settings.api_v1_prefix)

_customer_app_dir = Path(__file__).resolve().parent / "static" / "customer_app"
if _customer_app_dir.exists():
    app.mount("/customer-app", StaticFiles(directory=str(_customer_app_dir), html=True), name="customer-app")

_admin_app_dir = Path(__file__).resolve().parent / "static" / "admin_app"
if _admin_app_dir.exists():
    app.mount("/admin-app", StaticFiles(directory=str(_admin_app_dir), html=True), name="admin-app")


@app.get("/healthz", tags=["Health"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
