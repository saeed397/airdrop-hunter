"""Unit tests for the scoring engine, red-flag rules and participation levels."""
import pytest
from src.scoring.engine import ScoringEngine, ScoreResult, PARTICIPATION_LEVELS


@pytest.fixture
def engine():
    return ScoringEngine()


def test_hard_red_flag_seed_phrase(engine):
    result = engine.score(
        name="Free Token",
        description="Enter your seed phrase to claim the airdrop",
    )
    assert result.total == 0.0
    assert result.is_scam is True
    assert result.risk_label == "SCAM/AVOID"
    assert any("seed" in r.lower() for r in result.red_flags)


def test_hard_red_flag_young_domain(engine):
    result = engine.score(
        name="New Project",
        domain_data={"domain_age_days": 5},
    )
    assert result.total == 0.0
    assert result.is_scam is True
    assert any("domain age" in r.lower() for r in result.red_flags)


def test_hard_red_flag_honeypot(engine):
    result = engine.score(
        name="Suspicious Token",
        goplus_data={"is_honeypot": True},
    )
    assert result.total == 0.0
    assert result.is_scam is True


def test_good_score_with_funding(engine):
    result = engine.score(
        name="Solid Protocol",
        extra={
            "raise_amount_usd": 10_000_000,
            "investors": ["a16z", "Paradigm"],
            "tvl": 50_000_000,
            "type": "raise",
        },
        domain_data={"domain_age_days": 400, "has_ssl": True},
        sources=["defillama", "coingecko"],
        goplus_data={"is_open_source": True, "is_honeypot": False, "is_mintable": False},
        honeypot_data={"is_honeypot": False},
        contract_data={"is_contract": True},
    )
    assert result.total >= 60
    assert result.is_scam is False
    assert result.risk_label in ("Good", "Excellent")
    assert "contract_security" in result.breakdown
    assert len(result.reasons) > 0
    assert result.participation_level in PARTICIPATION_LEVELS


def test_score_range_always_0_100(engine):
    result = engine.score(name="Minimal")
    assert 0.0 <= result.total <= 100.0


def test_weights_sum_to_100(engine):
    assert abs(sum(engine.WEIGHTS.values()) - 100.0) < 0.01


def test_risk_labels(engine):
    assert engine._label(85) == "Excellent"
    assert engine._label(70) == "Good"
    assert engine._label(50) == "Risky"
    assert engine._label(20) == "Avoid"


# ---------- Participation level tests ----------

def test_zero_tx_social_only(engine):
    result = engine.score(
        name="Social Quest",
        description="Follow on Twitter and join Discord to earn points. No deposit needed.",
    )
    assert result.participation_level == "zero_tx"
    assert "social" in result.participation_tags or "points" in result.participation_tags


def test_zero_tx_testnet(engine):
    result = engine.score(
        name="Testnet Campaign",
        description="Complete tasks on the Sepolia testnet. Free faucet available.",
    )
    assert result.participation_level == "zero_tx"
    assert "testnet" in result.participation_tags


def test_high_tx_deposit(engine):
    result = engine.score(
        name="Liquidity Mining",
        description="Deposit and stake LP tokens to earn the airdrop.",
    )
    assert result.participation_level == "high_tx"
    assert "deposit_or_stake" in result.participation_tags


def test_medium_tx_swap(engine):
    result = engine.score(
        name="Swap Campaign",
        description="Make a small swap on mainnet and bridge assets to qualify.",
    )
    assert result.participation_level == "medium_tx"


def test_participation_in_to_dict(engine):
    result = engine.score(name="Any", description="follow twitter")
    d = result.to_dict()
    assert "participation_level" in d
    assert "participation_tags" in d
