"""Airdrops.io HTML scraper (respectful, no Selenium).
Uses requests + BeautifulSoup. Prefer RSS if available.
"""
from typing import List
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from src.scrapers.base import BaseScraper, RawAirdrop
from src.utils.logger import log


class AirdropsIOScraper(BaseScraper):
    """
    Scrapes https://airdrops.io/ for listed airdrops.
    Respects robots.txt spirit: limited frequency, proper User-Agent.
    """

    name = "airdrops_io"
    BASE_URL = "https://airdrops.io"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "AirdropHunterBot/1.0 (research; contact: none)",
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def _get_html(self, url: str) -> str:
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.text

    async def fetch(self) -> List[RawAirdrop]:
        results: List[RawAirdrop] = []
        try:
            html = await self._get_html(f"{self.BASE_URL}/")
            soup = BeautifulSoup(html, "lxml")

            # Airdrops.io uses cards / list items; structure may change.
            # We look for common patterns: article, .airdrop-item, h2/h3 links.
            cards = soup.select("article, .airdrop, .card, .project, li.airdrop-item")
            if not cards:
                # Fallback: any link that looks like an airdrop page
                cards = soup.select("a[href*='/airdrop/'], a[href*='/project/']")

            seen_names = set()
            for card in cards[:40]:
                # Extract name
                title_el = card.select_one("h2, h3, h4, .title, a")
                if not title_el:
                    continue
                name = self.normalize_name(title_el.get_text())
                if not name or name in seen_names or len(name) < 2:
                    continue
                seen_names.add(name)

                # URL
                link_el = card if card.name == "a" else card.select_one("a")
                href = link_el.get("href") if link_el else None
                if href and href.startswith("/"):
                    href = self.BASE_URL + href
                airdrop_url = href

                # Description snippet
                desc_el = card.select_one("p, .description, .excerpt")
                description = self.normalize_name(desc_el.get_text()) if desc_el else None

                results.append(
                    RawAirdrop(
                        name=name,
                        source=self.name,
                        description=description,
                        airdrop_url=airdrop_url,
                        project_url=airdrop_url,
                        source_links=[airdrop_url] if airdrop_url else [self.BASE_URL],
                        extra={"type": "listed_airdrop"},
                    )
                )

            log.info(f"[Airdrops.io] Fetched {len(results)} candidates")
        except Exception as e:
            log.error(f"[Airdrops.io] Fetch failed: {e}")
        return results

    async def close(self):
        await self.client.aclose()
