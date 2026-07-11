import streamlit as st
import pandas as pd
import plotly.express as px
from data_fetcher import fetch_high_risk_positions

st.set_page_config(
    page_title="Aave V3 Liquidation Risk Monitor",
    page_icon="⚠️",
    layout="wide"
)

st.title("⚠️ Aave V3 Liquidation Risk Monitor")
st.caption("Live on-chain data via a self-deployed Aave V3 subgraph | Ethereum Mainnet | Prices via CoinGecko")

# ── Fetch data ──────────────────────────────────────────────
with st.spinner("Fetching live on-chain data..."):
    try:
        positions_df = fetch_high_risk_positions(top_reserves=5, borrowers_per_reserve=15)
        data_ok = not positions_df.empty
    except Exception as e:
        st.error(f"Data fetch failed: {e}")
        data_ok = False

if not data_ok:
    st.warning("No positions returned. The subgraph may still be syncing, or no wallets matched the current filters.")
    st.stop()

# ── KPI Row ──────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

critical = positions_df[positions_df["health_factor"] < 1.05]
high = positions_df[(positions_df["health_factor"] >= 1.05) & (positions_df["health_factor"] < 1.2)]
total_debt_at_risk = positions_df["debt_usd"].sum()

col1.metric("Positions Monitored", len(positions_df))
col2.metric(
    "Critical Risk (HF < 1.05)",
    len(critical),
    delta=f"${critical['debt_usd'].sum():,.0f} debt at risk",
    delta_color="inverse"
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
    st.plotly_chart(fig_hist, use_container_width=True)

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
    st.plotly_chart(fig_pie, use_container_width=True)

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
st.plotly_chart(fig_collateral, use_container_width=True)

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

st.dataframe(scenarios, use_container_width=True, hide_index=True)

# ── Section 4: Top At-Risk Positions ─────────────────────────
st.subheader("Top Monitored Positions by Debt")
top20 = positions_df.nlargest(20, "debt_usd")[
    ["wallet", "health_factor", "collateral_usd", "debt_usd", "primary_collateral", "risk_tier"]
]
st.dataframe(top20, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Built by Bao Ying | Data: self-deployed Aave V3 subgraph (The Graph Studio) + CoinGecko live prices | "
    "github.com/betagamma-by | "
    "Note: positions collateralized by Pendle PT-tokens or a small number of unpriced assets are excluded — see README."
)