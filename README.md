# Aave V3 Liquidation Risk Monitor

Live on-chain risk monitoring for Aave V3 on Ethereum Mainnet — tracks
which borrowers are closest to liquidation, which collateral assets are
most exposed, and what happens under hypothetical price-drop scenarios.

## 📊 Live Dashboard (Part A — Dune Analytics)
[View on Dune Analytics](https://dune.com/betagamma/aave-v3-liquidation-risk-monitor)

Historical liquidation activity, borrower trends, and stress scenarios
built entirely in SQL against decoded on-chain event logs.

## 🖥️ Live App (Part B — Python + Streamlit)
[View Live App](https://aave-risk-monitor-9syd5qjjfcasllzflvjwh5.streamlit.app/)

Live position monitoring: pulls active borrower data from a **self-deployed
Aave V3 subgraph** on The Graph Studio, computes health factor per wallet
from raw collateral/debt balances, and displays risk tiers, collateral
concentration, and cascade scenarios in an interactive dashboard.

## What This Project Does

- **Part A (Dune):** historical liquidation volume, collateral exposure,
  borrower growth trends, and cascade stress scenarios — all via SQL.
- **Part B (Streamlit):** Health Factor monitoring for a sampled
  population of Aave V3 Ethereum Mainnet borrowers, calculated using
  borrower collateral and debt data, Aave Oracle asset prices,
  and applicable liquidation thresholds.

  The dashboard supports live data retrieval and validated
  historical snapshot fallback.

## How It Works

1. The Aave V3 Ethereum Mainnet subgraph on The Graph Studio
   provides borrower and reserve data.

2. The pipeline ranks reserves by USD debt and samples borrowers
   from the top 8 reserves, targeting up to 60 borrowers per reserve.
   Wallets appearing in multiple reserves are deduplicated.

3. For each sampled wallet, the pipeline retrieves collateral and
   debt positions, accounting for reserve indexes and supported
   on-chain debt adjustments.

4. Asset prices are obtained from the Aave Oracle.

5. Health Factor is calculated using collateral values, each
   asset's applicable liquidation threshold, and total debt.
   Financial calculations use Python Decimal arithmetic.

6. Streamlit displays risk classifications, debt exposure,
   collateral concentrations, and simplified stress scenarios.

7. GitHub Actions creates daily snapshots. When live fetching
   fails, Streamlit can recover from a validated historical
   snapshot and displays a historical-data warning.

## Data Quality & Known Limitations

This section is here deliberately — understanding where data breaks down
is part of the analysis, not something to hide.

- **Sampled coverage, not protocol-wide coverage.**
  The dashboard monitors selected borrowers from the largest
  debt markets. It must not be interpreted as covering every
  Aave V3 borrower.

- **Missing prices cause wallet exclusion.**
  If an asset required to value a wallet's collateral or debt
  lacks a valid price, that wallet is excluded from risk
  calculations rather than assigned an incorrect zero value.
  This can affect Pendle PT-token positions and other assets
  without supported oracle prices.

- **Asset pricing.**
  USD collateral and debt valuations use prices obtained
  from the Aave V3 Oracle on Ethereum Mainnet.

  Wallets requiring unavailable or invalid prices are
  excluded from risk calculations.

- **Snapshots are not perfectly block-consistent.**
  Subgraph and Ethereum RPC reads may occur at different
  blocks. Saved snapshots include relevant capture metadata,
  but should not be treated as an atomic on-chain state.

- **Historical fallback is not live monitoring.**
  When live fetching fails, the dashboard can display a
  previously validated snapshot. Historical data must not
  be interpreted as current liquidation eligibility.

- **Stress tests are simplified estimates.**
  The current scenarios assume uniform collateral price
  declines with unchanged debt values and liquidation
  thresholds. Results indicate hypothetical liquidation
  eligibility, not actual liquidations or financial losses.

- **Borrower selection is performed per reserve, not globally.**
  The pipeline selects borrowers from individual Aave V3
  reserves, rather than ranking all borrowers by their
  total USD debt across the entire protocol.

  This means the monitored population is a sample of
  borrowers from selected markets, not a complete
  protocol-wide ranking.

## Note on Live Data Availability

This project's live subgraph runs on The Graph Studio's free testing tier,
which is subject to periodic archival after inactivity (per The Graph's
Fair Use Policy). If the live app shows a connection warning, the subgraph
has likely been archived.

To redeploy it, clone Aave's official subgraph source
([github.com/aave/protocol-subgraphs](https://github.com/aave/protocol-subgraphs))
and run:

\`\`\`bash
VERSION=v3 BLOCKCHAIN=v3 NETWORK=mainnet npm run prepare:subgraph
SLUG=aave-v-3-risk-monitor npm run subgraph:deploy
\`\`\`

## Tech Stack

- SQL (Dune Analytics / Trino)
- Python 3.11
- Streamlit
- The Graph (self-deployed Aave V3 subgraph, Graph Studio)
- Aave Oracle (on-chain asset pricing)
- Ethereum RPC (on-chain reserve and debt data)
- GitHub Actions (daily snapshots and automated testing)
- Parquet (validated historical snapshots)
- Plotly

## Author

Built by Bao Ying — [github.com/betagamma-by](https://github.com/betagamma-by)