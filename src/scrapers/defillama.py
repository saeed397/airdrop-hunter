"""DefiLlama API scraper - free, no key required.
Focuses on protocols, raises, and TVL data that help score credibility.
"""
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.scrapers.base import BaseScraper, RawAirdrop
from src.utils.logger import log
from src.utils.helpers import safe_float


class DefiLlamaScraper(BaseScraper):
    """
    Uses public DefiLlama endpoints:
    - https://api.llama.fi/protocols
    - https://api.llama.fi/raises
    No API key needed. Rate-limit friendly.
    """

    name = "defillama"
    BASE_URL = "https://api.llama.fi"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "AirdropHunterBot/1.0 (read-only research)"},
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get(self, path: str) -> Any:
        url = f"{self.BASE_URL}{path}"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def fetch(self) -> List[RawAirdrop]:
        """Fetch recent raises + high-TVL protocols as potential airdrop candidates."""
        results: List[RawAirdrop] = []
        try:
            # 1. Recent fundraising / raises (strong credibility signal)
            raises = await self._get("/raises")
            raises_list = raises.get("raises", []) if isinstance(raises, dict) else raises
            for item in raises_list[:50]:  # limit to recent 50
                name = item.get("name") or item.get("project") or ""
                if not name:
                    continue
                name = self.normalize_name(name)
                results.append(
                    RawAirdrop(
                        name=name,
                        source=self.name,
                        description=f"Raised ${safe_float(item.get('amount')):.0f}M | Sector: {item.get('category', 'N/A')}",
                        project_url=item.get("url") or item.get("website"),
                        chain=item.get("chains", [None])[0] if item.get("chains") else None,
                        source_links=[f"https://defillama.com/raises"],
                        extra={
                            "raise_amount_usd": safe_float(item.get("amount")) * 1_000_000,
                            "investors": item.get("leadInvestors") or item.get("otherInvestors") or [],
                            "category": item.get("category"),
                            "date": item.get("date"),
                            "type": "raise",
                        },
                    )
                )

            # 2. Protocols with TVL (tokenless or points programs often appear here)
            protocols = await self._get("/protocols")
            if isinstance(protocols, list):
                # Prefer protocols that may still be tokenless or have points
                for p in protocols[:80]:
                    name = p.get("name") or ""
                    if not name:
                        continue
                    name = self.normalize_name(name)
                    tvl = safe_float(p.get("tvl"))
                    if tvl < 1_000_000:  # skip dust
                        continue
                    results.append(
                        RawAirdrop(
                            name=name,
                            source=self.name,
                            description=f"TVL: ${tvl:,.0f} | Category: {p.get('category', 'N/A')}",
                            project_url=p.get("url"),
                            chain=(p.get("chains") or [None])[0],
                            source_links=[f"https://defillama.com/protocol/{p.get('slug', '')}"],
                            extra={
                                "tvl": tvl,
                                "category": p.get("category"),
                                "symbol": p.get("symbol"),
                                "slug": p.get("slug"),
                                "type": "protocol",
                            },
                        )
                    )

            log.info(f"[DefiLlama] Fetched {len(results)} candidates")
        except Exception as e:
            log.error(f"[DefiLlama] Fetch failed: {e}")
        return results

    async def close(self):
        await self.client.aclose()
