"""Base scraper plugin interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from src.utils.helpers import utc_now, generate_airdrop_id, clean_text


@dataclass
class RawAirdrop:
    """Normalized raw airdrop data returned by every scraper."""
    name: str
    source: str
    description: Optional[str] = None
    project_url: Optional[str] = None
    airdrop_url: Optional[str] = None
    chain: Optional[str] = None
    contract_address: Optional[str] = None
    source_links: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=utc_now)

    def to_id(self) -> str:
        """Generate stable unique ID for deduplication."""
        return generate_airdrop_id(
            name=self.name,
            source=self.source,
            url=self.project_url or self.airdrop_url or "",
        )


class BaseScraper(ABC):
    """
    Abstract base class for all airdrop data sources.
    Design as plugins: add a new scraper by subclassing and registering it.
    """

    name: str = "base"
    enabled: bool = True

    @abstractmethod
    async def fetch(self) -> List[RawAirdrop]:
        """
        Fetch airdrops from the source.
        Must return a list of RawAirdrop objects.
        Should never raise; log errors and return empty list on failure.
        """
        pass

    def normalize_name(self, name: str) -> str:
        """Clean and normalize airdrop/project name."""
        return clean_text(name)
