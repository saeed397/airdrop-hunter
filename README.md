# Airdrop Hunter & Scoring System (Step 1 – Python Core)

Read-only system that discovers airdrops, checks security, scores legitimacy (0-100) and stores results in Postgres.

**This is STEP 1 only.** Steps 2-5 (Render hosting, Telegram, Streamlit, Safety) come after your confirmation.

---

## Project Structure

```
airdrop_hunter/
├── main.py                 # Entry point – run one full scan
├── requirements.txt        # Pinned dependencies
├── .env.example            # Copy to .env and fill values
├── README.md
├── src/
│   ├── config.py           # Pydantic settings from env
│   ├── scrapers/           # Plugin-based data sources
│   │   ├── base.py
│   │   ├── defillama.py
│   │   ├── coingecko.py
│   │   ├── airdrops_io.py
│   │   └── rss_feeds.py
│   ├── security/           # Read-only security checks
│   │   ├── goplus.py
│   │   ├── honeypot.py
│   │   ├── contract_checks.py
│   │   └── domain_checks.py
│   ├── scoring/
│   │   └── engine.py       # Weighted legitimacy score 0-100
│   ├── db/
│   │   ├── models.py
│   │   └── database.py
│   └── utils/
│       ├── logger.py
│       └── helpers.py
└── tests/
    └── test_scoring.py
```

---

## Quick Start (local)

```bash
# 1. Clone / enter folder
cd airdrop_hunter

# 2. Create virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env → set DATABASE_URL (Neon or Supabase free Postgres)

# 5. Run unit tests (no DB needed)
pytest tests/ -v

# 6. Run one scan
python main.py
```

---

## Scoring Model (transparent)

| Category              | Weight | What it looks at                                      |
|-----------------------|--------|-------------------------------------------------------|
| Contract Security     | 30%    | GoPlus, Honeypot.is, verified source, mint, proxy     |
| Project Credibility   | 25%    | DefiLlama raises, investors, domain age, SSL          |
| Reward Potential      | 20%    | TVL, funding size, tokenless / points                 |
| Participation Cost    | 15%    | Deposit / stake / gas mentions (lower cost = higher)  |
| Social Proof          | 10%    | Number of independent sources                         |

**Hard Red Flags → score = 0 + label "SCAM/AVOID"**
- Mentions seed phrase / private key / pay-to-unlock
- Domain age < 30 days
- Honeypot detected
- Owner can take back ownership / change balances
- Unverified contract asking for approve

Risk labels:
- Excellent ≥ 80
- Good 60–79
- Risky 40–59
- Avoid < 40

---

## Important Constraints (already enforced in code)

- **NO Binance** anything
- **NO private keys / signing** – web3.py is READ-ONLY
- **NO auto-claim / auto-approve**
- All secrets via `.env`
- Scrapers are plugins – easy to add/remove sources

---

## Next Steps (after your "continue")

2. 24/7 hosting on Render (Dockerfile / render.yaml + health endpoint)
3. Telegram alerts with inline buttons
4. Streamlit dashboard
5. Safety checklist + more tests

---

## Notes for free-tier usage

- Prefer Neon or Supabase free Postgres (ephemeral disk on Render cannot keep SQLite)
- Respect rate limits of free APIs
- Domain WHOIS can be slow / rate-limited – it is best-effort
