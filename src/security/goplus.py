"""GoPlus Security API - free token/contract security checks.
Docs: https://docs.gopluslabs.io/
No key required for basic token security endpoint.
"""
from typing import Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from src.utils.logger import log
from src.utils.helpers import is_evm_address


class GoPlusChecker:
    """
    Check token/contract security via GoPlus.
    Endpoint example:
    https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={addr}
    """

    BASE_URL = "https://api.gopluslabs.io/api/v1"
    # Common chain IDs
    CHAIN_IDS = {
        "ethereum": "1",
        "eth": "1",
        "bsc": "56",
        "polygon": "137",
        "arbitrum": "42161",
        "optimism": "10",
        "base": "8453",
        "avalanche": "43114",
        "fantom": "250",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "AirdropHunterBot/1.0"},
        )

    def _resolve_chain_id(self, chain: Optional[str]) -> Optional[str]:
        if not chain:
            return "1"  # default ethereum
        return self.CHAIN_IDS.get(chain.lower().strip(), None)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=6))
    async def check_token(self, address: str, chain: str = "ethereum") -> Dict[str, Any]:
        """
        Returns a dict with security flags.
        Empty dict on failure (caller treats as "unknown").
        """
        if not is_evm_address(address):
            return {"error": "invalid_address"}

        chain_id = self._resolve_chain_id(chain)
        if not chain_id:
            return {"error": "unsupported_chain"}

        url = f"{self.BASE_URL}/token_security/{chain_id}"
        params = {"contract_addresses": address.lower()}
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {}).get(address.lower(), {})
            return result or {"error": "no_data"}
        except Exception as e:
            log.warning(f"[GoPlus] check failed for {address}: {e}")
            return {"error": str(e)}

    def analyze_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert raw GoPlus response into simple flags used by scoring engine.
        """
        if not result or "error" in result:
            return {
                "is_honeypot": None,
                "is_open_source": None,
                "is_proxy": None,
                "can_take_back_ownership": None,
                "owner_change_balance": None,
                "is_mintable": None,
                "is_blacklisted": None,
                "buy_tax": None,
                "sell_tax": None,
                "raw_error": result.get("error") if result else "empty",
            }

        def _bool(val):
            if val is None:
                return None
            return str(val).lower() in ("1", "true", "yes")

        return {
            "is_honeypot": _bool(result.get("is_honeypot")),
            "is_open_source": _bool(result.get("is_open_source")),
            "is_proxy": _bool(result.get("is_proxy")),
            "can_take_back_ownership": _bool(result.get("can_take_back_ownership")),
            "owner_change_balance": _bool(result.get("owner_change_balance")),
            "is_mintable": _bool(result.get("is_mintable")),
            "is_blacklisted": _bool(result.get("is_blacklisted")),
            "buy_tax": result.get("buy_tax"),
            "sell_tax": result.get("sell_tax"),
            "holder_count": result.get("holder_count"),
            "raw": result,
        }

    async def close(self):
        await self.client.aclose()
