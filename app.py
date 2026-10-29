import streamlit as st
import pandas as pd
import plotly.express as px
import os
import data_fetcher as d
from web3 import Web3
from data_fetcher import fetch_high_risk_positions
from datetime import datetime, timezone
from f11_fallback import load_github_snapshot

st.set_page_config(
    page_title="Aave V3 Liquidation Risk Monitor",
    page_icon="⚠️",
    layout="wide"
)

st.title("⚠️ Aave V3 Liquidation Risk Monitor")
st.caption(
    "Ethereum Mainnet | Aave V3 positions via The Graph "
    "| Prices via Aave Oracle"
)

# ── Fetch data ──────────────────────────────────────────────
@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def load_positions(top_reserves, borrowers_per_reserve):
    positions, stats = fetch_high_risk_positions(
        top_reserves=top_reserves,
        borrowers_per_reserve=borrowers_per_reserve,
        return_stats=True
    )

    fetched_at = datetime.now(timezone.utc)

    # Observe data-source freshness after calculating positions.
    graph_meta = d._gql(
        "{ _meta { block { number } hasIndexingErrors } }"
    )["_meta"]

    w3 = Web3(Web3.HTTPProvider(
        os.environ["ETH_RPC_URL"],
        request_kwargs={"timeout": 20}
    ))

    chain_block = w3.eth.block_number
    graph_block = int(graph_meta["block"]["number"])

    freshness = {
        "chain_block": chain_block,
        "graph_block": graph_block,
        "lag_blocks": max(0, chain_block - graph_block),
        "indexing_errors": graph_meta["hasIndexingErrors"],
    }

    return positions, stats, fetched_at, freshness


@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def load_positions_with_fallback(top_reserves, borrowers_per_reserve):
    try:
        positions, stats, fetched_at, freshness = load_positions(
            top_reserves, borrowers_per_reserve
        )
        return positions, stats, fetched_at, freshness, "live"
    except Exception as live_error:
        try:
            positions, stats, captured_at, metadata = load_github_snapshot()
            stats = stats.copy()
            stats["price_source"] = metadata["price_source"]
            freshness = {
                "chain_block": metadata.get("chain_block"),
                "graph_block": metadata.get("graph_block"),
                "lag_blocks": metadata.get("lag_blocks"),
                "indexing_errors": metadata.get("indexing_errors"),
            }
            return positions, stats, captured_at, freshness, "snapshot"
        except Exception:
            raise RuntimeError(
                "Both live Aave data and GitHub snapshot recovery failed"
            ) from None


with st.spinner("Loading Aave positions..."):
    try:
        (
            positions_df,
            coverage_stats,
            fetched_at,
            freshness,
            data_source,
        ) = load_positions_with_fallback(8, 60)
    except Exception as e:
        st.error(
            "Unable to load Aave data from either the live sources "
            "or the GitHub recovery snapshot."
        )
        st.caption(f"Error type: {type(e).__name__}")
        st.stop()

if data_source == "snapshot":
    st.warning(
        "⚠️ HISTORICAL SNAPSHOT — Live Aave data is unavailable. "
        f"Showing the last valid snapshot captured at "
        f"{fetched_at:%Y-%m-%d %H:%M:%S} UTC. "
        "These positions and health factors may no longer reflect "
        "current liquidation risk."
    )

if positions_df.empty:
    st.warning(
        "No positions matched the current selection. "
        "This does not mean Aave has no active borrowers."
    )
    st.stop()

# ── Data quality and coverage ───────────────────────────────
st.divider()
if data_source == "live":
    st.write(f"Ethereum head block: {freshness['chain_block']:,}")
    st.write(f"Subgraph indexed block: {freshness['graph_block']:,}")
    st.write(f"Indexing lag: {freshness['lag_blocks']} blocks")

    if freshness["indexing_errors"]:
        st.error("Subgraph reports indexing errors.")
    elif freshness["lag_blocks"] > 20:
        st.warning("Subgraph may be significantly behind Ethereum.")
else:
    st.caption(
        "Blockchain freshness metrics are unavailable in "
        "historical recovery mode."
    )

st.caption(
    f"{'Data fetched' if data_source == 'live' else 'Snapshot captured'}: "
    f"{fetched_at:%Y-%m-%d %H:%M:%S} UTC "
    "| Cache TTL: 5 minutes"
)

if st.button("Refresh data"):
    load_positions.clear()
    load_positions_with_fallback.clear()
    st.rerun()

fetched = coverage_stats["wallets_fetched"]
analyzed = len(positions_df)

excluded_collateral = coverage_stats["excluded_unpriced_collateral"]
excluded_debt = coverage_stats["excluded_unpriced_debt"]
dropped_small = coverage_stats["dropped_debt_under_100"]

excluded = excluded_collateral + excluded_debt
total_omitted = excluded + dropped_small

with st.expander("Data Quality & Coverage", expanded=False):
    c1, c2, c3 = st.columns(3)
    c1.metric("Wallets fetched", fetched)
    c2.metric("Wallets analyzed", analyzed)
    c3.metric("Excluded / dropped", total_omitted)

    st.write(f"Missing collateral prices: {excluded_collateral}")
    st.write(f"Missing debt prices: {excluded_debt}")
    st.write(f"Debt below $100: {dropped_small}")
    st.write(f"Wallets in eMode: {coverage_stats['wallets_in_emode']}")
    st.write(f"Price source: {coverage_stats['price_source']}")

    st.caption(
        "Coverage represents selected borrowers, not every "
        "Aave borrower. Excluded wallets are not included in "
        "risk calculations."
    )

    if fetched != analyzed + total_omitted:
        st.error("Wallet accounting mismatch detected.")

    if excluded > 0:
        st.warning(
            f"{excluded} wallets excluded due to missing prices. "
            "Reported risk statistics exclude these positions."
        )

# ── KPI Row ──────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

critical = positions_df[positions_df["health_factor"] < 1.05]
high = positions_df[(positions_df["health_factor"] >= 1.05) & (positions_df["health_factor"] < 1.2)]
total_debt_at_risk = positions_df["debt_usd"].sum()

col1.metric("Positions Monitored", len(positions_df))
col2.metric(
    "Critical Risk (HF < 1.05)",
    len(critical),
    border=True
)
col2.caption(
    f"Combined Outstanding Debt: ${critical['debt_usd'].sum():,.0f}"
)
col3.metric("High Risk (HF 1.05–1.2)", len(high))
col4.metric("Total Debt Monitored", f"${total_debt_at_risk:,.0f}")

st.divider()

# ── Section 1: Risk Distribution ─────────────────────────────
st.subheader("Health Factor Distribution")
col_a, col_b = st.columns(2)

with col_a:
    fig_hist = px.histogram(
        positions_df,
        x="health_factor",
        nbins=20,
        color="risk_tier",
        title="Distribution of Health Factors (monitored positions)",
        labels={"health_factor": "Health Factor", "count": "# Positions"},
        color_discrete_map={
            "CRITICAL (HF < 1.05)": "#d62728",
            "HIGH (HF 1.05–1.2)": "#ff7f0e",
            "ELEVATED (HF 1.2–1.5)": "#ffdd57",
            "SAFE": "#2ca02c"
        }
    )
    st.plotly_chart(fig_hist, width="stretch")

with col_b:
    risk_counts = positions_df["risk_tier"].value_counts().reset_index()
    risk_counts.columns = ["risk_tier", "count"]
    fig_pie = px.pie(
        risk_counts,
        names="risk_tier",
        values="count",
        title="Risk Tier Breakdown",
        color="risk_tier",
        color_discrete_map={
            "CRITICAL (HF < 1.05)": "#d62728",
            "HIGH (HF 1.05–1.2)": "#ff7f0e",
            "ELEVATED (HF 1.2–1.5)": "#ffdd57",
            "SAFE": "#2ca02c"
        }
    )
    st.plotly_chart(fig_pie, width="stretch")

# ── Section 2: Collateral Concentration ──────────────────────
st.subheader("Collateral Concentration Among Monitored Positions")

collateral_summary = (
    positions_df.groupby("primary_collateral")
    .agg(position_count=("wallet", "count"), total_debt_usd=("debt_usd", "sum"))
    .reset_index()
    .sort_values("total_debt_usd", ascending=False)
)

fig_collateral = px.bar(
    collateral_summary,
    x="primary_collateral",
    y="total_debt_usd",
    color="position_count",
    title="Debt Exposure by Primary Collateral Asset",
    labels={
        "primary_collateral": "Collateral Asset",
        "total_debt_usd": "Total Debt (USD)",
        "position_count": "# Positions"
    },
    color_continuous_scale="Reds"
)
st.plotly_chart(fig_collateral, width="stretch")

# ── Section 3: Liquidation Cascade Simulation ─────────────────
st.subheader("Liquidation Cascade Scenarios")
st.caption("Estimated impact if collateral prices drop, based on currently monitored positions.")

total_collateral = positions_df["collateral_usd"].sum()

scenarios = pd.DataFrame({
    "Price Drop Scenario": ["-10%", "-20%", "-30%", "-40%", "-50%"],
})

liquidated_counts = []
collateral_at_risk = []

for drop_pct in [0.10, 0.20, 0.30, 0.40, 0.50]:
    threshold = 1.0 / (1 - drop_pct)
    at_risk_positions = positions_df[positions_df["health_factor"] < threshold]
    liquidated_counts.append(len(at_risk_positions))
    collateral_at_risk.append(at_risk_positions["collateral_usd"].sum())

scenarios["Positions Pushed Into Liquidation"] = liquidated_counts
scenarios["Est. Collateral at Risk (USD)"] = [f"${v:,.0f}" for v in collateral_at_risk]

st.dataframe(scenarios, width="stretch", hide_index=True)

# ── Section 4: Top At-Risk Positions ─────────────────────────
st.subheader("Top Monitored Positions by Debt")
top20 = positions_df.nlargest(20, "debt_usd")[
    ["wallet", "health_factor", "collateral_usd", "debt_usd", "primary_collateral", "risk_tier"]
]
st.dataframe(top20, width="stretch", hide_index=True)

st.divider()
st.caption(
    "Built by Bao Ying | Data: self-deployed Aave V3 subgraph (The Graph Studio) + CoinGecko live prices | "
    "github.com/betagamma-by | "
    "Note: positions collateralized by Pendle PT-tokens or a small number of unpriced assets are excluded — see README."
)