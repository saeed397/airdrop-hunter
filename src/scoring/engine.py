"""
Legitimacy Scoring Engine (0-100).
Weighted, explainable, with hard red-flag rules that force score=0.
Also classifies participation difficulty for Streamlit strategy filters.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from src.utils.helpers import safe_float


# ---------------------------------------------------------------------------
# Participation strategy levels (used by Streamlit checkboxes)
# From strictest → easiest
# ---------------------------------------------------------------------------
PARTICIPATION_LEVELS = {
    "zero_tx": {
        "label_fa": "سخت‌گیرانه‌ترین (بدون هیچ تراکنش)",
        "label_en": "Zero-TX / Social + Testnet only",
        "order": 1,
        "description": "فقط فالو، دیسکورد، ثبت‌نام یا تست‌نت — هیچ تراکنش اصلی",
    },
    "low_tx": {
        "label_fa": "کم‌تراکنش (حداکثر یک تراکنش ارزان)",
        "label_en": "Low-TX (one cheap approve/tx max)",
        "order": 2,
        "description": "حداکثر یک approve یا تراکنش خیلی ارزان روی mainnet",
    },
    "medium_tx": {
        "label_fa": "عادی (سواپ/بریج کوچک قابل قبول)",
        "label_en": "Medium-TX (small swap/bridge ok)",
        "order": 3,
        "description": "سواپ، بریج یا استیک کوچک قابل قبول است",
    },
    "high_tx": {
        "label_fa": "ساده‌ترین فیلتر (همه روش‌ها)",
        "label_en": "All methods (no restriction)",
        "order": 4,
        "description": "بدون محدودیت — شامل دیپازیت و نقدینگی هم می‌شود",
    },
}


@dataclass
class ScoreResult:
    total: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    red_flags: List[str] = field(default_factory=list)
    risk_label: str = "Unknown"
    is_scam: bool = False
    # New: participation difficulty for Streamlit strategy filter
    participation_level: str = "medium_tx"  # zero_tx | low_tx | medium_tx | high_tx
    participation_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": round(self.total, 1),
            "breakdown": {k: round(v, 1) for k, v in self.breakdown.items()},
            "reasons": self.reasons,
            "red_flags": self.red_flags,
            "risk_label": self.risk_label,
            "is_scam": self.is_scam,
            "participation_level": self.participation_level,
            "participation_tags": self.participation_tags,
        }


class ScoringEngine:
    """
    Weights (must sum to 100):
      - Contract Security   30%
      - Project Credibility 25%
      - Reward Potential    20%
      - Participation Cost  15%
      - Social Proof        10%
    """

    WEIGHTS = {
        "contract_security": 30.0,
        "project_credibility": 25.0,
        "reward_potential": 20.0,
        "participation_cost": 15.0,
        "social_proof": 10.0,
    }

    def score(
        self,
        *,
        name: str,
        contract_data: Optional[Dict] = None,
        goplus_data: Optional[Dict] = None,
        honeypot_data: Optional[Dict] = None,
        domain_data: Optional[Dict] = None,
        extra: Optional[Dict] = None,
        sources: Optional[List[str]] = None,
        description: Optional[str] = None,
    ) -> ScoreResult:
        """
        Main entry point. All inputs are optional; missing data lowers the category score.
        """
        contract_data = contract_data or {}
        goplus_data = goplus_data or {}
        honeypot_data = honeypot_data or {}
        domain_data = domain_data or {}
        extra = extra or {}
        sources = sources or []
        description = (description or "").lower()
        name_l = (name or "").lower()
        text = name_l + " " + description

        result = ScoreResult()

        # ---------- 1. HARD RED FLAGS (score = 0) ----------
        red_flags = self._detect_red_flags(
            name=name,
            description=description,
            goplus=goplus_data,
            honeypot=honeypot_data,
            domain=domain_data,
            contract=contract_data,
        )
        if red_flags:
            result.red_flags = red_flags
            result.total = 0.0
            result.is_scam = True
            result.risk_label = "SCAM/AVOID"
            result.reasons = ["Hard red flag(s) detected → automatic score 0"] + red_flags
            result.breakdown = {k: 0.0 for k in self.WEIGHTS}
            result.participation_level = "high_tx"
            result.participation_tags = ["scam"]
            return result

        # ---------- 2. Classify participation difficulty ----------
        level, tags = self._classify_participation(text, extra)
        result.participation_level = level
        result.participation_tags = tags

        # ---------- 3. Category scores (0-100 each) ----------
        sec_score, sec_reasons = self._score_contract_security(
            goplus_data, honeypot_data, contract_data
        )
        cred_score, cred_reasons = self._score_credibility(extra, domain_data, sources)
        reward_score, reward_reasons = self._score_reward_potential(extra)
        cost_score, cost_reasons = self._score_participation_cost(extra, description, level)
        social_score, social_reasons = self._score_social_proof(sources, extra)

        result.breakdown = {
            "contract_security": sec_score,
            "project_credibility": cred_score,
            "reward_potential": reward_score,
            "participation_cost": cost_score,
            "social_proof": social_score,
        }

        total = 0.0
        for cat, weight in self.WEIGHTS.items():
            total += result.breakdown[cat] * (weight / 100.0)
        result.total = min(100.0, max(0.0, total))

        result.reasons = (
            sec_reasons + cred_reasons + reward_reasons + cost_reasons + social_reasons
        )
        result.reasons.append(
            f"Participation level: {PARTICIPATION_LEVELS[level]['label_en']}"
        )
        result.risk_label = self._label(result.total)
        return result

    # ------------------------------------------------------------------
    # Participation classification (for Streamlit strategy checkboxes)
    # ------------------------------------------------------------------
    def _classify_participation(
        self, text: str, extra: Dict
    ) -> tuple[str, List[str]]:
        """
        Returns (level, tags).
        Levels from strictest to easiest:
          zero_tx → low_tx → medium_tx → high_tx
        """
        tags: List[str] = []

        # Keywords that indicate NO mainnet transaction needed
        social_kw = (
            "twitter", "discord", "follow", "retweet", "join", "telegram",
            "social", "quest", "galxe", "zealy", "layer3", "register", "signup",
            "sign up", "waitlist", "whitelist form",
        )
        testnet_kw = ("testnet", "test net", "goerli", "sepolia", "holesky", "faucet", "free gas")
        points_kw = ("points", "xp", "loyalty", "season", "campaign", "tokenless")

        # Keywords that require on-chain activity
        low_tx_kw = ("approve", "claim", "connect wallet", "sign message")
        medium_tx_kw = ("swap", "bridge", "trade", "transaction", "mainnet", "gas")
        high_tx_kw = (
            "deposit", "stake", "lock", "liquidity", "provide lp", "lend",
            "borrow", "collateral", "minimum deposit", "lock tokens",
        )

        has_social = any(k in text for k in social_kw)
        has_testnet = any(k in text for k in testnet_kw)
        has_points = any(k in text for k in points_kw)
        has_low = any(k in text for k in low_tx_kw)
        has_medium = any(k in text for k in medium_tx_kw)
        has_high = any(k in text for k in high_tx_kw)

        if has_social:
            tags.append("social")
        if has_testnet:
            tags.append("testnet")
        if has_points:
            tags.append("points")
        if has_low:
            tags.append("approve_or_claim")
        if has_medium:
            tags.append("swap_or_bridge")
        if has_high:
            tags.append("deposit_or_stake")

        # Extra signals from DefiLlama / protocol data
        if extra.get("type") in ("raise", "protocol") and not extra.get("symbol"):
            tags.append("tokenless")
            has_points = True

        # Decision tree (strictest first)
        if has_high:
            return "high_tx", tags or ["deposit_or_stake"]
        if has_medium:
            return "medium_tx", tags or ["swap_or_bridge"]
        if has_low and not (has_social or has_testnet or has_points):
            return "low_tx", tags or ["approve_or_claim"]
        if has_testnet or (has_social and not has_medium and not has_high):
            return "zero_tx", tags or ["social"]
        if has_points and not has_medium and not has_high:
            return "zero_tx", tags or ["points"]
        if has_low:
            return "low_tx", tags or ["approve_or_claim"]

        # Default when we have little info: assume medium (safer for filtering)
        return "medium_tx", tags or ["unknown"]

    # ------------------------------------------------------------------
    # Red-flag detection
    # ------------------------------------------------------------------
    def _detect_red_flags(
        self,
        name: str,
        description: str,
        goplus: Dict,
        honeypot: Dict,
        domain: Dict,
        contract: Dict,
    ) -> List[str]:
        flags = []

        bad_phrases = [
            "seed phrase", "private key", "secret key", "mnemonic",
            "enter your seed", "connect wallet and approve", "send eth to unlock",
            "pay to claim", "unlock fee", "gas fee upfront",
        ]
        text = (name + " " + description).lower()
        for phrase in bad_phrases:
            if phrase in text:
                flags.append(f"Suspicious text: mentions '{phrase}'")

        age = domain.get("domain_age_days")
        if age is not None and age < 30:
            flags.append(f"Domain age only {age} days (< 30 day red flag)")

        if goplus.get("is_honeypot") is True:
            flags.append("GoPlus: token is honeypot")
        if honeypot.get("is_honeypot") is True:
            flags.append("Honeypot.is: detected as honeypot")

        if goplus.get("is_blacklisted") is True:
            flags.append("GoPlus: address blacklisted")
        if goplus.get("can_take_back_ownership") is True:
            flags.append("GoPlus: owner can take back ownership")
        if goplus.get("owner_change_balance") is True:
            flags.append("GoPlus: owner can change balances")

        if (
            contract.get("is_contract")
            and goplus.get("is_open_source") is False
            and "approve" in description
        ):
            flags.append("Unverified contract + approve request")

        return flags

    # ------------------------------------------------------------------
    # Category scorers
    # ------------------------------------------------------------------
    def _score_contract_security(
        self, goplus: Dict, honeypot: Dict, contract: Dict
    ) -> tuple[float, List[str]]:
        score = 50.0
        reasons = []

        if goplus.get("is_open_source") is True:
            score += 20
            reasons.append("Contract is open-source / verified (+20)")
        elif goplus.get("is_open_source") is False:
            score -= 25
            reasons.append("Contract NOT open-source (-25)")

        if goplus.get("is_honeypot") is False or honeypot.get("is_honeypot") is False:
            score += 15
            reasons.append("Not a honeypot (+15)")
        elif goplus.get("is_honeypot") is True or honeypot.get("is_honeypot") is True:
            score = 0
            reasons.append("Honeypot detected (score forced low)")

        if goplus.get("is_mintable") is False:
            score += 10
            reasons.append("No unlimited mint (+10)")
        elif goplus.get("is_mintable") is True:
            score -= 15
            reasons.append("Mintable token (-15)")

        if goplus.get("is_proxy") is True:
            score -= 5
            reasons.append("Proxy contract (extra caution) (-5)")

        if contract.get("is_contract") is True:
            score += 5
            reasons.append("Valid contract code found (+5)")

        return max(0.0, min(100.0, score)), reasons

    def _score_credibility(
        self, extra: Dict, domain: Dict, sources: List[str]
    ) -> tuple[float, List[str]]:
        score = 40.0
        reasons = []

        raise_amt = safe_float(extra.get("raise_amount_usd"))
        if raise_amt >= 5_000_000:
            score += 25
            reasons.append(f"Raised ${raise_amt/1e6:.1f}M (+25)")
        elif raise_amt >= 1_000_000:
            score += 15
            reasons.append(f"Raised ${raise_amt/1e6:.1f}M (+15)")
        elif raise_amt > 0:
            score += 5
            reasons.append("Has some funding (+5)")

        investors = extra.get("investors") or []
        if investors:
            score += 10
            reasons.append(f"Known investors listed ({len(investors)}) (+10)")

        age = domain.get("domain_age_days")
        if age is not None:
            if age >= 365:
                score += 15
                reasons.append(f"Domain age {age} days (≥1y) (+15)")
            elif age >= 90:
                score += 8
                reasons.append(f"Domain age {age} days (+8)")
            elif age >= 30:
                score += 3
                reasons.append(f"Domain age {age} days (+3)")

        if domain.get("has_ssl") is True:
            score += 5
            reasons.append("Valid SSL certificate (+5)")

        return max(0.0, min(100.0, score)), reasons

    def _score_reward_potential(self, extra: Dict) -> tuple[float, List[str]]:
        score = 40.0
        reasons = []

        tvl = safe_float(extra.get("tvl"))
        if tvl >= 100_000_000:
            score += 30
            reasons.append(f"TVL ${tvl/1e6:.0f}M (+30)")
        elif tvl >= 10_000_000:
            score += 20
            reasons.append(f"TVL ${tvl/1e6:.0f}M (+20)")
        elif tvl >= 1_000_000:
            score += 10
            reasons.append(f"TVL ${tvl/1e6:.0f}M (+10)")

        if extra.get("type") in ("raise", "protocol") and not extra.get("symbol"):
            score += 15
            reasons.append("Appears tokenless / pre-TGE (+15)")
        elif extra.get("type") == "trending":
            score += 10
            reasons.append("Trending on CoinGecko (+10)")

        return max(0.0, min(100.0, score)), reasons

    def _score_participation_cost(
        self, extra: Dict, description: str, level: str
    ) -> tuple[float, List[str]]:
        """
        Lower required cost → higher score.
        Now also influenced by classified participation_level.
        """
        # Base score by level (zero_tx is best for cost category)
        base = {
            "zero_tx": 90.0,
            "low_tx": 70.0,
            "medium_tx": 45.0,
            "high_tx": 20.0,
        }.get(level, 50.0)

        reasons = [f"Participation level '{level}' → base cost score {base}"]

        text = description.lower()
        if "testnet" in text or "free" in text:
            base = min(100.0, base + 10)
            reasons.append("Testnet / free mention (+10)")

        return max(0.0, min(100.0, base)), reasons

    def _score_social_proof(
        self, sources: List[str], extra: Dict
    ) -> tuple[float, List[str]]:
        score = 30.0
        reasons = []

        unique_sources = set(s.lower() for s in sources)
        n = len(unique_sources)
        if n >= 3:
            score += 40
            reasons.append(f"Listed in {n} independent sources (+40)")
        elif n == 2:
            score += 25
            reasons.append("Listed in 2 sources (+25)")
        elif n == 1:
            score += 10
            reasons.append("Single source (+10)")

        if extra.get("type") == "raise":
            score += 15
            reasons.append("Appears in DefiLlama raises (+15)")

        return max(0.0, min(100.0, score)), reasons

    def _label(self, score: float) -> str:
        if score >= 80:
            return "Excellent"
        if score >= 60:
            return "Good"
        if score >= 40:
            return "Risky"
        return "Avoid"
