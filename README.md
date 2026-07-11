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
- **Part B (Streamlit):** live health-factor monitoring for active Aave V3
  borrowers, computed from raw on-chain balances + live market prices.

## How It Works

1. A custom subgraph (deployed from Aave's own open-source subgraph code)
   indexes Aave V3's contract events on Ethereum mainnet.
2. For each of the top 5 most-borrowed markets, the pipeline finds the
   largest active borrowers (`userReserves` sorted by debt, within a
   single asset at a time — see Known Limitations for why this matters).
3. For each wallet, all of their collateral and debt positions are pulled
   and converted from raw on-chain integers into real-world units.
4. Live USD prices are fetched from CoinGecko (the subgraph's own price
   field turned out to be unreliable for many assets — see below).
5. Health factor is computed per wallet using Aave's own formula:
   `(collateral × liquidation threshold) / debt`.
6. Streamlit displays risk tiers, distributions, and cascade scenarios.

## Data Quality & Known Limitations

This section is here deliberately — understanding where data breaks down
is part of the analysis, not something to hide.

- **Pendle PT-token collateral is excluded.** Wallets using Pendle
  Principal Tokens (e.g. `PT-sUSDe-27NOV2025`) as collateral are excluded
  from risk calculations, because each PT token trades at a maturity-
  specific discount that requires Pendle's own pricing API — out of
  scope for this project. These wallets are flagged and dropped rather
  than shown with incorrect (zero) collateral values.
- **A small number of newer/exotic assets have no price source.**
  A handful of tokens (e.g. `mUSD`, `USDG`, `eBTC`) aren't covered by
  the CoinGecko mapping used here and are excluded from collateral/debt
  totals for any wallet holding them.
- **The subgraph's native `priceInEth` field is not reliable.** Despite
  the name, it stores a USD price scaled by 1e8 for major assets, but
  returns `0` for several newer assets (e.g. GHO, USDe, RLUSD) — likely
  because their oracle isn't a standard Chainlink feed. Live CoinGecko
  prices are used instead for accuracy and full coverage.
- **Ranking by "top borrowers" is done per-asset, not globally.** Raw
  on-chain debt amounts aren't comparable across assets with different
  decimal precision (e.g. USDC uses 6 decimals, WETH uses 18) — so
  candidate wallets are identified by sorting within one reserve at a
  time, where the comparison is valid.

## Tech Stack

- SQL (Dune Analytics / Trino)
- Python 3.11
- Streamlit
- The Graph (self-deployed Aave V3 subgraph, Graph Studio)
- CoinGecko API (live pricing)
- Plotly

## Author

Built by Bao Ying — [github.com/betagamma-by](https://github.com/betagamma-by)