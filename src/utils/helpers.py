"""Shared helper functions."""
from datetime import datetime, timezone
from typing import Optional, Any
from urllib.parse import urlparse
import hashlib
import re
import tldextract


def utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def normalize_url(url: str) -> str:
    """Normalize URL for comparison (lowercase, strip trailing slash)."""
    if not url:
        return ""
    url = url.strip().lower()
    if url.endswith("/"):
        url = url[:-1]
    return url


def extract_domain(url: str) -> Optional[str]:
    """Extract registered domain from URL using tldextract."""
    if not url:
        return None
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        ext = tldextract.extract(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
        return None
    except Exception:
        return None


def generate_airdrop_id(name: str, source: str, url: str = "") -> str:
    """
    Generate a stable unique ID for deduplication.
    Uses name + source + domain hash so the same airdrop from different
    scrapes is recognized as one entity.
    """
    domain = extract_domain(url) or ""
    raw = f"{name.strip().lower()}|{source.strip().lower()}|{domain}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def clean_text(text: Optional[str]) -> str:
    """Remove extra whitespace and normalize text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def is_evm_address(addr: str) -> bool:
    """Check if string looks like an EVM address."""
    if not addr:
        return False
    return bool(re.match(r"^0x[a-fA-F0-9]{40}$", addr.strip()))
