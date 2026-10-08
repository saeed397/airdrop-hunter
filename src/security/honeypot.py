"""Honeypot.is API - free EVM honeypot detection.
Endpoint: https://api.honeypot.is/v2/IsHoneypot?address={addr}
"""
from typing import Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.logger import log
from src.utils.helpers import is_evm_address


class HoneypotChecker:
    """Simple wrapper around honeypot.is public API."""

    BASE_URL = "https://api.honeypot.is/v2/IsHoneypot"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "AirdropHunterBot/1.0"},
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=6))
    async def check(self, address: str, chain: str = "ethereum") -> Dict[str, Any]:
        """
        Returns dict with is_honeypot flag and simulation results.
        """
        if not is_evm_address(address):
            return {"error": "invalid_address", "is_honeypot": None}

        # honeypot.is supports chainId query param on some versions
        params = {"address": address}
        # Map common names (optional)
        chain_map = {
            "ethereum": 1,
            "eth": 1,
            "bsc": 56,
            "polygon": 137,
            "arbitrum": 42161,
            "base": 8453,
        }
        if chain and chain.lower() in chain_map:
            params["chainID"] = chain_map[chain.lower()]

        try:
            resp = await self.client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            return {
                "is_honeypot": data.get("honeypotResult", {}).get("isHoneypot"),
                "simulation_success": data.get("simulationSuccess"),
                "risk": data.get("summary", {}).get("risk"),
                "raw": data,
            }
        except Exception as e:
            log.warning(f"[Honeypot.is] check failed for {address}: {e}")
            return {"error": str(e), "is_honeypot": None}

    async def close(self):
        await self.client.aclose()
