import streamlit as st
import pandas as pd
import plotly.express as px
import os
import data_fetcher as d
from scenario_presets import PRESETS
from web3 import Web3
from data_fetcher import fetch_high_risk_positions
from datetime import datetime, timezone
from recovery import load_with_fallback
from f11_fallback import load_github_snapshot
from stress_engine import simulate_price_shock

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
    positions, stats, prepared, prices = fetch_high_risk_positions(
        top_reserves=top_reserves,
        borrowers_per_reserve=borrowers_per_reserve,
        return_stats=True,
        return_inputs=True,
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

    return positions, stats, fetched_at, freshness, (prepared, prices)

@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def load_positions_with_fallback(top_reserves, borrowers_per_reserve):
    return load_with_fallback(
        load_positions,
        load_github_snapshot,
        top_reserves,
        borrowers_per_reserve,
    )

with st.spinner("Loading Aave positions..."):
    try:
        (
            positions_df,
            coverage_stats,
            fetched_at,
            freshness,
            data_source,
            scenario_inputs,
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

st.info(
    "Coverage: This dashboard monitors a sampled subset of Aave V3 "
    "Ethereum borrowers, not all active borrowers. "
    "Positions excluded because of missing prices or the minimum "
    "debt threshold are not represented in the risk statistics."
)

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

liquidatable = positions_df[
    positions_df["health_factor"] < 1.0
]

near_liquidation = positions_df[
    (positions_df["health_factor"] >= 1.0)
    & (positions_df["health_factor"] < 1.05)
]

critical = positions_df[
    positions_df["risk_tier"] == "CRITICAL (HF < 1.05)"
]

high = positions_df[
    positions_df["risk_tier"] == "HIGH (HF 1.05–1.2)"
]
total_debt_monitored = positions_df["debt_usd"].sum()

col1.metric("Positions Monitored", len(positions_df))
col2.metric(
    "Critical Risk (HF < 1.05)",
    len(critical)
)
col2.markdown(
    f"""
    <div style="
        background-color: rgba(255, 75, 75, 0.12);
        color: #FF4B4B;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        margin-top: 4px;
    ">
        ${critical['debt_usd'].sum():,.0f} Combined Outstanding Debt
    </div>
    """,
    unsafe_allow_html=True
)
col3.metric("High Risk (HF 1.05–1.2)", len(high))
col4.metric("Total Debt Monitored", f"${total_debt_monitored:,.0f}")
if len(liquidatable) + len(near_liquidation) != len(critical):
    st.error("Liquidation risk classification mismatch detected.")
st.caption(
    f"Critical positions: {len(liquidatable):,} currently "
    f"liquidatable (HF < 1.0) + "
    f"{len(near_liquidation):,} near liquidation "
    f"(1.0 ≤ HF < 1.05) = {len(critical):,} total."
)
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
st.subheader("Simplified Collateral Price Stress Test")

st.caption(
    "Hypothetical scenarios assuming all collateral assets decline "
    "by the same percentage, debt values remain unchanged, and "
    "liquidation thresholds remain constant. "
    "Results represent potential liquidation eligibility, "
    "not predicted liquidations or realized losses."
)

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

scenarios["Positions with Simulated HF < 1.0"] = liquidated_counts

scenarios["Collateral Held by These Positions (USD)"] = [
    f"${v:,.0f}" for v in collateral_at_risk
]

st.dataframe(scenarios, width="stretch", hide_index=True)


st.subheader("F13 — Asset-Specific Price Shock")

if scenario_inputs is None:
    st.info(
        "Asset-specific simulation is unavailable while using "
        "historical snapshot recovery."
    )
else:
    prepared, prices = scenario_inputs

    assets = (
        prepared[["underlying", "symbol"]]
        .drop_duplicates(subset=["underlying"])
        .copy()
    )

    assets["underlying"] = assets["underlying"].str.lower()
    assets = assets[assets["underlying"].isin(prices)]
    assets = assets.sort_values(["symbol", "underlying"])

    if assets.empty:
        st.info("No priced assets available for simulation.")
    else:
        options = {
            f"{r.symbol} ({r.underlying[:10]}...)": r.underlying
            for r in assets.itertuples()
        }

        asset_label = st.selectbox(
            "Asset to stress",
            options=list(options),
        )

        drop_pct = st.slider(
            "Price decrease (%)",
            min_value=0,
            max_value=80,
            value=20,
            step=5,
        )

        try:
            result = simulate_price_shock(
                prepared,
                prices,
                {options[asset_label]: -drop_pct / 100},
            )

            selected_asset = options[asset_label]

            asset_positions = prepared[
                prepared["underlying"].str.lower() == selected_asset
            ].copy()

            asset_positions["holds_selected_collateral"] = (
                asset_positions["collateral_enabled"]
                & (asset_positions["atoken_balance_raw"] > 0)
            )

            asset_positions["owes_selected_asset"] = (
                asset_positions["debt_raw"] > 0
            )

            exposure = asset_positions[
                [
                    "wallet",
                    "holds_selected_collateral",
                    "owes_selected_asset",
                ]
            ].rename(columns={"wallet": "wallet_full"})

            result = result.merge(
                exposure,
                on="wallet_full",
                how="left",
                validate="one_to_one",
            )

            result["holds_selected_collateral"] = (
                result["holds_selected_collateral"].fillna(False).astype(bool)
            )

            result["owes_selected_asset"] = (
                result["owes_selected_asset"].fillna(False).astype(bool)
            )

            newly = result[result["newly_liquidatable"]]
            already = result[result["already_liquidatable"]]

            c1, c2, c3 = st.columns(3)

            c1.metric("Newly Liquidatable", len(newly))
            c2.metric("Already Liquidatable", len(already))
            c3.metric(
                "Debt of Newly Liquidatable Wallets",
                f"${newly['stressed_debt_usd'].sum():,.0f}",
            )

            st.caption(
                "Hypothetical single-asset price shock. "
                "Debt shown is outstanding debt, not expected losses. "
                "No liquidation execution is simulated."
            )

            st.markdown("#### 20 Lowest Simulated Health Factors")

            st.caption(
                "Shows the 20 monitored wallets with the lowest Health Factors "
                "after the selected price shock. Wallets are ranked by simulated HF, "
                "regardless of whether they hold or borrow the selected asset. "
                "Some wallets may already be liquidatable or remain unaffected "
                "by this scenario."
            )

            st.caption(
                "HF Change = Stressed HF − Baseline HF. "
                "A negative value means the borrower's liquidation safety "
                "margin decreased; a positive value means it improved."
            )

            st.dataframe(
                result.sort_values("stressed_hf").head(20),
                width="stretch",
                hide_index=True,
            )

        except ValueError as exc:
            st.warning(
                "This scenario could not be compared consistently: "
                f"{exc}"
            )

        st.divider()
        st.subheader("Multi-Asset Stress Scenario")

        st.caption(
            "Simulate several asset price changes together. "
            "Scenario presets are illustrative assumptions, not forecasts."
        )

        scenario = st.selectbox(
            "Scenario",
            [
                "ETH Market Crash",
                "Stablecoin Depeg",
                "Staking Token Divergence",
                "Custom",
            ],
            key="multi_scenario",
        )

        # Build asset selection from actual monitored reserves.
        asset_options = {
            f"{r.symbol} ({r.underlying[:10]}...)": r.underlying
            for r in assets.itertuples()
        }

        if scenario == "Custom":
            selected_assets = st.multiselect(
                "Assets to change",
                options=list(asset_options),
                default=[],
            )

            changes = {}
            for label in selected_assets:
                pct = st.slider(
                    f"{label} price change (%)",
                    min_value=-80,
                    max_value=100,
                    value=-20,
                    step=5,
                    key=f"custom_{asset_options[label]}",
                )
                if pct != 0:
                    changes[asset_options[label]] = pct / 100

        else:
            changes = {}
            missing_assets = []

            for symbol, pct in PRESETS[scenario].items():
                matching = assets[assets["symbol"] == symbol]

                if matching.empty:
                    missing_assets.append(symbol)
                    continue

                for address in matching["underlying"]:
                    changes[address] = pct / 100

            if missing_assets:
                st.error(
                    "INCOMPLETE SCENARIO — Missing priced assets: "
                    + ", ".join(missing_assets)
                    + ". Results do not represent the full preset."
                )

        if changes:
            st.markdown("#### Assets With Simulated Price Changes")

            st.caption(
                "These are token contract addresses, NOT borrower wallet addresses. "
                "Each price change applies to that token across all monitored wallets. "
                "Percentages are hypothetical assumptions, not market forecasts."
            )

            asset_names = dict(zip(assets["underlying"], assets["symbol"]))

            st.dataframe(
                pd.DataFrame([
                    {
                        "Token": asset_names.get(address, "Unknown"),
                        "Token Contract Address": address,
                        "Current Oracle Price (USD)": prices[address],
                        "Simulated Price Change (%)": round(change * 100, 2),
                        "Simulated Price (USD)": prices[address] * (1 + change),
                    }
                    for address, change in changes.items()
                ]),
                width="stretch",
                hide_index=True,
            )

            try:
                multi_result = simulate_price_shock(
                    prepared,
                    prices,
                    changes,
                )

                newly_multi = multi_result[
                    multi_result["newly_liquidatable"]
                ]

                affected_multi = multi_result[
                    multi_result["affected_by_shock"]
                ]

                m1, m2, m3 = st.columns(3)

                m1.metric("Affected Wallets", len(affected_multi))
                m2.metric("Newly Liquidatable", len(newly_multi))
                m3.metric(
                    "Debt of Newly Liquidatable Wallets",
                    f"${newly_multi['stressed_debt_usd'].sum():,.0f}",
                )

                st.caption(
                    "Showing the 20 lowest simulated Health Factors "
                    "across sampled wallets. Unaffected wallets may appear. "
                    "Outstanding debt is not an estimate of liquidation losses."
                )

                st.dataframe(
                    multi_result.sort_values("stressed_hf").head(20),
                    width="stretch",
                    hide_index=True,
                )

            except ValueError as exc:
                st.warning(f"Scenario unavailable: {exc}")
        else:
            st.info("Select at least one available asset with a nonzero shock.")

# ── Section 4: Top At-Risk Positions ─────────────────────────
st.subheader("Top Monitored Positions by Debt")
top20 = positions_df.nlargest(20, "debt_usd")[
    [
        "wallet",
        "health_factor_display",
        "collateral_usd",
        "debt_usd",
        "primary_collateral",
        "risk_tier",
    ]
].rename(columns={
    "health_factor_display": "Health Factor"
})

st.dataframe(
    top20,
    width="stretch",
    hide_index=True,
    column_config={
        "Health Factor": st.column_config.NumberColumn(
            "Health Factor",
            format="%.6f"
        )
    }
)

st.divider()
st.caption(
    "Built by Bao Ying | "
    "Data: Aave V3 Ethereum Mainnet via The Graph Studio "
    "and Aave Oracle prices | "
    "github.com/betagamma-by | "
    "Coverage: sampled monitored borrowers; "
    "positions with required assets lacking valid prices are excluded. "
    "See README for methodology and limitations."
)