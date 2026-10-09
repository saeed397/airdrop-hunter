"""
Step 2 – Web server + 24/7 scheduler.

- FastAPI exposes GET /health so UptimeRobot can ping every 10 min
  and keep the free Render Web Service awake.
- APScheduler runs the airdrop scan every SCAN_INTERVAL_MINUTES.
- All heavy work stays in the same process (free-tier friendly).
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.utils.logger import log, setup_logger
from src.db.database import init_db
from main import run_scan

# Re-configure logger with settings level
setup_logger(settings.LOG_LEVEL)

scheduler = AsyncIOScheduler()

# Track last scan status for /health
_last_scan: dict = {
    "started_at": None,
    "finished_at": None,
    "status": "never_run",
    "error": None,
}


async def _scheduled_scan():
    """Wrapper so APScheduler can call the async scan safely."""
    global _last_scan
    _last_scan["started_at"] = datetime.now(timezone.utc).isoformat()
    _last_scan["status"] = "running"
    _last_scan["error"] = None
    log.info("[Scheduler] Starting scheduled scan...")
    try:
        await run_scan()
        _last_scan["status"] = "success"
        log.info("[Scheduler] Scan finished successfully")
    except Exception as e:
        _last_scan["status"] = "failed"
        _last_scan["error"] = str(e)
        log.exception(f"[Scheduler] Scan failed: {e}")
    finally:
        _last_scan["finished_at"] = datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB + start scheduler. Shutdown: stop scheduler."""
    log.info("=== Airdrop Hunter server starting ===")
    log.info(f"Environment: {settings.ENVIRONMENT}")
    log.info(f"Scan interval: {settings.SCAN_INTERVAL_MINUTES} minutes")

    try:
        init_db()
        log.info("Database ready")
    except Exception as e:
        log.error(f"DB init failed (will retry on first scan): {e}")

    # Recurring scans
    scheduler.add_job(
        _scheduled_scan,
        trigger=IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
        id="airdrop_scan",
        name="Airdrop discovery scan",
        replace_existing=True,
        max_instances=1,  # never overlap scans
    )

    # First scan ~45 seconds after boot
    scheduler.add_job(
        _scheduled_scan,
        trigger="date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=45),
        id="first_scan",
        name="First scan after boot",
        replace_existing=True,
    )

    scheduler.start()
    log.info("APScheduler started")

    yield  # app runs here

    log.info("Shutting down scheduler...")
    scheduler.shutdown(wait=False)
    log.info("=== Airdrop Hunter server stopped ===")


app = FastAPI(
    title="Airdrop Hunter",
    description="Read-only airdrop discovery & scoring (health + scheduler)",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """
    Lightweight health check for UptimeRobot / Render.
    Must stay fast and never depend on external APIs.
    """
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "airdrop-hunter",
            "environment": settings.ENVIRONMENT,
            "scan_interval_minutes": settings.SCAN_INTERVAL_MINUTES,
            "scheduler_running": scheduler.running,
            "last_scan": _last_scan,
            "jobs": jobs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.get("/")
async def root():
    """Simple root so opening the service URL is not a 404."""
    return {
        "message": "Airdrop Hunter is running",
        "health": "/health",
        "docs": "/docs",
    }


@app.post("/scan/now")
async def trigger_scan_now():
    """
    Manual trigger (optional). Useful for testing on Render.
    Does not require auth on free tier – protect later if the URL is public.
    """
    if _last_scan.get("status") == "running":
        return JSONResponse(
            status_code=409,
            content={"detail": "A scan is already running"},
        )
    asyncio.create_task(_scheduled_scan())
    return {"detail": "Scan started in background"}
