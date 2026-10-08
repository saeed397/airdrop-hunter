"""
Airdrop Hunter - Main entry point (Step 1 core).
Runs one full scan cycle: scrape → security checks → score → store in DB.
Later steps will add scheduler, Telegram and Streamlit.
"""
import asyncio
from typing import List, Dict, Any
from datetime import datetime

from src.config import settings
from src.utils.logger import log
from src.utils.helpers import utc_now
from src.db.database import init_db, get_db
from src.db.models import Airdrop, ScanLog
from src.scrapers import run_all_scrapers
from src.scrapers.base import RawAirdrop
from src.security import GoPlusChecker, HoneypotChecker, ContractChecker, DomainChecker
from src.scoring import ScoringEngine


async def enrich_and_score(raw: RawAirdrop) -> Dict[str, Any]:
    """
    Run security checks (if we have a contract address) and produce a score.
    All checks are best-effort; missing data simply lowers the category score.
    """
    goplus = GoPlusChecker(api_key=settings.GOPLUS_API_KEY)
    honeypot = HoneypotChecker()
    contract = ContractChecker(etherscan_api_key=settings.ETHERSCAN_API_KEY)
    domain = DomainChecker()
    engine = ScoringEngine()

    goplus_data: Dict = {}
    honeypot_data: Dict = {}
    contract_data: Dict = {}
    domain_data: Dict = {}

    try:
        # Domain check (always useful)
        url = raw.project_url or raw.airdrop_url
        if url:
            domain_data = domain.check_domain(url)

        # Contract-level checks only if we have an address
        if raw.contract_address:
            chain = raw.chain or "ethereum"
            goplus_raw = await goplus.check_token(raw.contract_address, chain)
            goplus_data = goplus.analyze_result(goplus_raw)
            honeypot_data = await honeypot.check(raw.contract_address, chain)
            contract_data = await contract.check_basic(raw.contract_address, chain)
    except Exception as e:
        log.warning(f"Enrichment error for {raw.name}: {e}")
    finally:
        await goplus.close()
        await honeypot.close()

    score_result = engine.score(
        name=raw.name,
        contract_data=contract_data,
        goplus_data=goplus_data,
        honeypot_data=honeypot_data,
        domain_data=domain_data,
        extra=raw.extra,
        sources=[raw.source],
        description=raw.description,
    )

    return {
        "score_result": score_result,
        "goplus": goplus_data,
        "honeypot": honeypot_data,
        "contract": contract_data,
        "domain": domain_data,
    }


async def process_raw_airdrops(raw_list: List[RawAirdrop]) -> tuple[int, int]:
    """
    Deduplicate, enrich, score and upsert into the database.
    Returns (new_count, updated_count).
    """
    new_count = 0
    updated_count = 0
    now = utc_now()

    with get_db() as db:
        for raw in raw_list:
            try:
                airdrop_id = raw.to_id()
                existing = db.get(Airdrop, airdrop_id)

                enriched = await enrich_and_score(raw)
                sr = enriched["score_result"]

                if existing:
                    # Update score & metadata
                    existing.legitimacy_score = sr.total
                    existing.score_breakdown = sr.breakdown
                    existing.reasons = sr.reasons
                    existing.red_flags = sr.red_flags
                    existing.risk_label = sr.risk_label
                    existing.participation_level = sr.participation_level
                    existing.participation_tags = sr.participation_tags
                    existing.last_updated = now
                    existing.last_scanned = now
                    # Merge sources
                    old_sources = set(existing.sources or [])
                    old_sources.add(raw.source)
                    existing.sources = list(old_sources)
                    if sr.is_scam:
                        existing.status = "scam"
                    updated_count += 1
                else:
                    airdrop = Airdrop(
                        id=airdrop_id,
                        name=raw.name,
                        description=raw.description,
                        project_url=raw.project_url,
                        airdrop_url=raw.airdrop_url,
                        chain=raw.chain,
                        contract_address=raw.contract_address,
                        legitimacy_score=sr.total,
                        score_breakdown=sr.breakdown,
                        reasons=sr.reasons,
                        red_flags=sr.red_flags,
                        risk_label=sr.risk_label,
                        participation_level=sr.participation_level,
                        participation_tags=sr.participation_tags,
                        sources=[raw.source],
                        source_links=raw.source_links,
                        status="scam" if sr.is_scam else "new",
                        first_seen=now,
                        last_updated=now,
                        last_scanned=now,
                        extra_data={
                            "raw_extra": raw.extra,
                            "goplus": enriched["goplus"],
                            "honeypot": enriched["honeypot"],
                            "contract": enriched["contract"],
                            "domain": enriched["domain"],
                        },
                    )
                    db.add(airdrop)
                    new_count += 1

                log.info(
                    f"{'NEW' if not existing else 'UPD'} | {raw.name[:40]:<40} | "
                    f"Score {sr.total:5.1f} | {sr.risk_label} | {sr.participation_level}"
                )
            except Exception as e:
                log.error(f"Failed to process {raw.name}: {e}")

    return new_count, updated_count


async def run_scan() -> None:
    """One complete scan cycle."""
    log.info("=" * 60)
    log.info("Starting Airdrop Hunter scan")
    log.info("=" * 60)

    started = utc_now()
    scan_log = None

    with get_db() as db:
        scan_log = ScanLog(started_at=started, status="running")
        db.add(scan_log)
        db.flush()
        scan_id = scan_log.id

    errors = []
    try:
        raw_list = await run_all_scrapers()
        log.info(f"Total raw candidates collected: {len(raw_list)}")

        new_c, upd_c = await process_raw_airdrops(raw_list)

        with get_db() as db:
            log_entry = db.get(ScanLog, scan_id)
            if log_entry:
                log_entry.finished_at = utc_now()
                log_entry.airdrops_found = len(raw_list)
                log_entry.airdrops_new = new_c
                log_entry.airdrops_updated = upd_c
                log_entry.status = "success"
                log_entry.errors = errors or None

        log.info(f"Scan finished. New={new_c} Updated={upd_c}")
    except Exception as e:
        log.exception(f"Scan failed: {e}")
        errors.append(str(e))
        with get_db() as db:
            log_entry = db.get(ScanLog, scan_id)
            if log_entry:
                log_entry.finished_at = utc_now()
                log_entry.status = "failed"
                log_entry.errors = errors


def main():
    """Entry point for manual run / testing."""
    log.info("Initializing database...")
    init_db()
    asyncio.run(run_scan())
    log.info("Done. Check the database for results.")


if __name__ == "__main__":
    main()
