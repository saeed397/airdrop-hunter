"""Generic RSS / Atom feed scraper for airdrop news sites.
Uses feedparser (lightweight, no Selenium).
"""
from typing import List
import feedparser
import httpx
from src.scrapers.base import BaseScraper, RawAirdrop
from src.utils.logger import log


# Curated list of public RSS feeds related to airdrops / crypto opportunities
# (no Binance-owned sources)
DEFAULT_FEEDS = [
    "https://airdropalert.com/feed/",
    "https://www.coinmarketcap.com/headlines/news/feed/",  # general crypto news
    # Add more public RSS feeds here as plugins
]


class RSSFeedScraper(BaseScraper):
    """
    Parses multiple RSS feeds and extracts potential airdrop mentions.
    """

    name = "rss_feeds"

    def __init__(self, feed_urls: List[str] = None):
        self.feed_urls = feed_urls or DEFAULT_FEEDS
        self.client = httpx.AsyncClient(
            timeout=25.0,
            headers={"User-Agent": "AirdropHunterBot/1.0 (research)"},
            follow_redirects=True,
        )

    async def _fetch_feed(self, url: str) -> feedparser.FeedParserDict:
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            return feedparser.parse(resp.text)
        except Exception as e:
            log.warning(f"[RSS] Failed to fetch {url}: {e}")
            return feedparser.FeedParserDict()

    async def fetch(self) -> List[RawAirdrop]:
        results: List[RawAirdrop] = []
        keywords = ("airdrop", "claim", "points", "reward", "token generation", "tge", "snapshot")

        for feed_url in self.feed_urls:
            try:
                feed = await self._fetch_feed(feed_url)
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "") or entry.get("description", "")
                    text = (title + " " + summary).lower()

                    # Simple keyword filter to keep only relevant items
                    if not any(k in text for k in keywords):
                        continue

                    name = self.normalize_name(title)[:120]
                    if not name:
                        continue

                    link = entry.get("link")
                    results.append(
                        RawAirdrop(
                            name=name,
                            source=self.name,
                            description=self.normalize_name(summary)[:300] if summary else None,
                            airdrop_url=link,
                            project_url=link,
                            source_links=[link] if link else [feed_url],
                            extra={
                                "published": entry.get("published"),
                                "feed": feed_url,
                                "type": "rss",
                            },
                        )
                    )
            except Exception as e:
                log.error(f"[RSS] Error processing {feed_url}: {e}")

        log.info(f"[RSS] Fetched {len(results)} candidates from feeds")
        return results

    async def close(self):
        await self.client.aclose()
