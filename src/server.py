"""
Web server + scheduler – resilient for Render free tier.

- GET /health always answers fast (UptimeRobot keeps service awake)
- Scans never overlap; one failed scan does not kill the process
- Scan has a time limit so a hung job cannot freeze the server
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
from src.telegram_alerts import start_telegram_bot, stop_telegram_bot

setup_logger(settings.LOG_LEVEL)

scheduler = AsyncIOScheduler(
    job_defaults={
        "coalesce": True,          # skip missed runs, run once
        "max_instances": 1,        # never two scans at once
        "misfire_grace_time": 300, # 5 min late is still ok
    }
)

_last_scan: dict = {
    "started_at": None,
    "finished_at": None,
    "status": "never_run",
    "error": None,
}

# Hard limit so a stuck scan cannot freeze the whole service (minutes)
_SCAN_TIMEOUT_SEC = max(10, min(settings.SCAN_INTERVAL_MINUTES - 2, 25)) * 60


async def _scheduled_scan():
    """Run one scan; catch all errors; never crash the web process."""
    global _last_scan
    if _last_scan.get("status") == "running":
        log.warning("[Scheduler] Scan already running – skip")
        return

    _last_scan["started_at"] = datetime.now(timezone.utc).isoformat()
    _last_scan["status"] = "running"
    _last_scan["error"] = None
    log.info("[Scheduler] Starting scheduled scan...")
    try:
        await asyncio.wait_for(run_scan(), timeout=_SCAN_TIMEOUT_SEC)
        _last_scan["status"] = "success"
        log.info("[Scheduler] Scan finished successfully")
    except asyncio.TimeoutError:
        _last_scan["status"] = "failed"
        _last_scan["error"] = f"timeout after {_SCAN_TIMEOUT_SEC}s"
        log.error(f"[Scheduler] Scan timed out after {_SCAN_TIMEOUT_SEC}s")
    except Exception as e:
        _last_scan["status"] = "failed"
        _last_scan["error"] = str(e)[:500]
        log.exception(f"[Scheduler] Scan failed: {e}")
    finally:
        _last_scan["finished_at"] = datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Airdrop Hunter server starting ===")
    log.info(f"Environment: {settings.ENVIRONMENT}")
    log.info(f"Scan interval: {settings.SCAN_INTERVAL_MINUTES} minutes")

    try:
        init_db()
        log.info("Database ready")
    except Exception as e:
        log.error(f"DB init failed (will retry on first scan): {e}")

    try:
        scheduler.add_job(
            _scheduled_scan,
            trigger=IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
            id="airdrop_scan",
            name="Airdrop discovery scan",
            replace_existing=True,
        )
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
    except Exception as e:
        log.error(f"Scheduler failed to start: {e}")

    try:
        await start_telegram_bot()
    except Exception as e:
        log.error(f"Telegram bot failed to start (service continues): {e}")

    yield

    log.info("Shutting down...")
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    try:
        await stop_telegram_bot()
    except Exception:
        pass
    log.info("=== Airdrop Hunter server stopped ===")


app = FastAPI(
    title="Airdrop Hunter",
    description="Read-only airdrop discovery & scoring",
    version="0.2.1",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Always return 200 quickly – used by UptimeRobot to prevent sleep."""
    try:
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
                "scheduler_running": bool(scheduler.running),
                "last_scan": _last_scan,
                "jobs": jobs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as e:
        # Still 200 so UptimeRobot does not mark DOWN on a minor health bug
        return JSONResponse(
            status_code=200,
            content={"status": "degraded", "error": str(e)[:200]},
        )


@app.get("/")
async def root():
    return {"message": "Airdrop Hunter is running", "health": "/health"}


@app.post("/scan/now")
async def trigger_scan_now():
    if _last_scan.get("status") == "running":
        return JSONResponse(status_code=409, content={"detail": "Scan already running"})
    asyncio.create_task(_scheduled_scan())
    return {"detail": "Scan started in background"}
