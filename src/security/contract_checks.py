"""READ-ONLY contract inspection using web3.py.
Never signs transactions. Only eth_call / get_code / get_storage.
"""
from typing import Dict, Any, Optional
from web3 import Web3
from src.utils.logger import log
from src.utils.helpers import is_evm_address


# Public free RPC endpoints (no key required for light usage)
# Prefer your own or Alchemy/Infura free tier if available
PUBLIC_RPCS = {
    "ethereum": "https://eth.llamarpc.com",
    "eth": "https://eth.llamarpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "base": "https://mainnet.base.org",
    "optimism": "https://mainnet.optimism.io",
    "polygon": "https://polygon-rpc.com",
}


class ContractChecker:
    """
    Basic on-chain checks:
    - Has code? (is contract)
    - Is verified? (via explorer API later)
    - Simple ownership / mint indicators via common function selectors
    """

    def __init__(self, etherscan_api_key: Optional[str] = None):
        self.etherscan_api_key = etherscan_api_key
        self._w3_cache: Dict[str, Web3] = {}

    def _get_w3(self, chain: str = "ethereum") -> Optional[Web3]:
        chain = (chain or "ethereum").lower()
        if chain in self._w3_cache:
            return self._w3_cache[chain]
        rpc = PUBLIC_RPCS.get(chain)
        if not rpc:
            log.warning(f"[Contract] No public RPC for chain={chain}")
            return None
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
        if w3.is_connected():
            self._w3_cache[chain] = w3
            return w3
        log.warning(f"[Contract] Cannot connect to RPC for {chain}")
        return None

    async def check_basic(self, address: str, chain: str = "ethereum") -> Dict[str, Any]:
        """
        Synchronous web3 calls wrapped for async context.
        Returns basic contract flags.
        """
        if not is_evm_address(address):
            return {"error": "invalid_address", "is_contract": False}

        result = {
            "is_contract": False,
            "code_size": 0,
            "has_owner_function": None,
            "has_mint_function": None,
        }

        try:
            w3 = self._get_w3(chain)
            if not w3:
                return {**result, "error": "no_rpc"}

            checksum = Web3.to_checksum_address(address)
            code = w3.eth.get_code(checksum)
            code_hex = code.hex() if code else ""
            result["is_contract"] = len(code_hex) > 2
            result["code_size"] = len(code_hex) // 2

            # Very light heuristic: look for common function selectors in bytecode
            # owner() = 0x8da5cb5b
            # mint(address,uint256) = 0x40c10f19
            if result["is_contract"]:
                result["has_owner_function"] = "8da5cb5b" in code_hex
                result["has_mint_function"] = "40c10f19" in code_hex

        except Exception as e:
            log.warning(f"[Contract] basic check failed for {address}: {e}")
            result["error"] = str(e)

        return result
