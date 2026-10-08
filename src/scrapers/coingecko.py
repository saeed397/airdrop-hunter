"""CoinGecko public API scraper - free tier, no key for basic endpoints.
Used for project/token metadata and market data.
"""
from typing import List, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.scrapers.base import BaseScraper, RawAirdrop
from src.utils.logger import log
from src.utils.helpers import safe_float


class CoinGeckoScraper(BaseScraper):
    """
    Public endpoints (no key required for basic usage):
    - /search/trending
    - /coins/list
    Rate limit: ~10-30 calls/min on free tier. Be respectful.
    """

    name = "coingecko"
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "AirdropHunterBot/1.0 (read-only research)"},
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, path: str, params: dict = None) -> Any:
        url = f"{self.BASE_URL}{path}"
        resp = await self.client.get(url, params=params or {})
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> List[RawAirdrop]:
        """Fetch trending coins as potential airdrop-related projects."""
        results: List[RawAirdrop] = []
        try:
            data = await self._get("/search/trending")
            coins = data.get("coins", []) if isinstance(data, dict) else []
            for item in coins:
                coin = item.get("item", {})
                name = coin.get("name") or ""
                if not name:
                    continue
                name = self.normalize_name(name)
                results.append(
                    RawAirdrop(
                        name=name,
                        source=self.name,
                        description=f"Trending on CoinGecko | Rank: {coin.get('market_cap_rank', 'N/A')}",
                        project_url=f"https://www.coingecko.com/en/coins/{coin.get('id', '')}",
                        source_links=[f"https://www.coingecko.com/en/coins/{coin.get('id', '')}"],
                        extra={
                            "coingecko_id": coin.get("id"),
                            "symbol": coin.get("symbol"),
                            "market_cap_rank": coin.get("market_cap_rank"),
                            "score": coin.get("score"),
                            "type": "trending",
                        },
                    )
                )
            log.info(f"[CoinGecko] Fetched {len(results)} trending candidates")
        except Exception as e:
            log.error(f"[CoinGecko] Fetch failed: {e}")
        return results

    async def close(self):
        await self.client.aclose()
