"""Scraper plugin registry.
Add new sources by importing the class and appending to SCRAPERS list.
"""
from src.scrapers.defillama import DefiLlamaScraper
from src.scrapers.coingecko import CoinGeckoScraper
from src.scrapers.airdrops_io import AirdropsIOScraper
from src.scrapers.rss_feeds import RSSFeedScraper

# All enabled scrapers (order does not matter)
SCRAPERS = [
    DefiLlamaScraper,
    CoinGeckoScraper,
    AirdropsIOScraper,
    RSSFeedScraper,
]


async def run_all_scrapers():
    """Run every registered scraper and return combined RawAirdrop list."""
    from src.utils.logger import log
    all_results = []
    for scraper_cls in SCRAPERS:
        scraper = scraper_cls()
        if not getattr(scraper, "enabled", True):
            continue
        try:
            items = await scraper.fetch()
            all_results.extend(items)
            log.info(f"Scraper [{scraper.name}] returned {len(items)} items")
        except Exception as e:
            log.error(f"Scraper [{scraper.name}] crashed: {e}")
        finally:
            if hasattr(scraper, "close"):
                await scraper.close()
    return all_results
