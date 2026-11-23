import streamlit as st
import pandas as pd
import plotly.express as px
import os
import data_fetcher as d
from scenario_presets import PRESETS, resolve_preset
from web3 import Web3
from data_fetcher import fetch_high_risk_positions
from datetime import datetime, timezone
from recovery import load_with_fallback
from f11_fallback import load_github_snapshot
from stress_engine import simulate_price_shock
from zoneinfo import ZoneInfo
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

def show_liquidation_wallet_selector(results, prepared, stressed_prices, key, snapshot_block, data_source, scenario_inputs_present, historical_debt_verified):

    from exposure_access import exposure_available

    if not exposure_available(
        data_source,
        scenario_inputs_present,
        snapshot_block,
        historical_debt_verified,
    ):
        st.warning(
            "Indicative liquidation exposure is unavailable in "
            "recovery mode or without verified live scenario inputs."
        )
        return

    eligible = results.loc[
        results["stressed_hf"] < 1
    ].drop_duplicates("wallet_full").sort_values("stressed_hf")

    with st.expander(
        f"Liquidation Exposure — {len(eligible)} eligible wallets"
    ):
        if eligible.empty:
            st.info("No monitored wallets have simulated HF below 1.")
            return

        wallet = st.selectbox(
            "Select borrower wallet",
            eligible["wallet_full"].tolist(),
            key=f"{key}_wallet",
        )
        # Reset the previous calculation when the wallet changes.
        wallet_state_key = f"{key}_previous_wallet"

        if st.session_state.get(wallet_state_key) != wallet:
            st.session_state.pop(
                f"{key}_current_verification", None
            )
            st.session_state.pop(
                f"{key}_hf_verification", None
            )
            st.session_state[wallet_state_key] = wallet
            st.rerun()


        position = eligible.loc[
            eligible["wallet_full"] == wallet
        ].iloc[0]

        st.code(wallet)

        # F17: compare monitor baseline against Aave at the same block.
        from decimal import Decimal
        from wallet_hf_comparison import compare_wallet_health_factors

        baseline_hf = position["baseline_hf"]
        stressed_hf = position["stressed_hf"]
        verification_key = f"{key}_hf_verification"

        # F17: invalidate verification when the snapshot changes.
        snapshot_state_key = f"{key}_hf_snapshot_block"

        if st.session_state.get(snapshot_state_key) != snapshot_block:
            st.session_state.pop(verification_key, None)
            st.session_state[snapshot_state_key] = snapshot_block

        st.markdown("#### Wallet Health Factor")

        c1, c2 = st.columns(2)
        c1.metric("Monitor Baseline HF", f"{float(baseline_hf):.6f}")
        c2.metric("Simulated HF (after shock)", f"{float(stressed_hf):.6f}")

        st.caption(
            f"Both values use snapshot block {snapshot_block:,}. "
            "Only the simulated HF includes the selected price shock."
        )

        if st.button(
            "Verify Historical & Current HF (on-chain)",
            key=f"{key}_verify_hf",
        ):
            from current_wallet_verification import fetch_current_wallet_account

            st.session_state.pop(verification_key, None)

            try:
                with st.spinner("Verifying against Aave Pool..."):
                    historical = fetch_current_wallet_account(
                        wallet,
                        block_identifier=int(snapshot_block),
                    )
                    current = fetch_current_wallet_account(wallet)

                if (
                    historical["wallet"] != wallet.lower()
                    or current["wallet"] != wallet.lower()
                    or historical["block_number"] != int(snapshot_block)
                ):
                    raise ValueError("Verification wallet/block mismatch")

                st.session_state[verification_key] = {
                    "historical": historical,
                    "current": current,
                }
            except Exception as exc:
                st.error(
                    "On-chain HF verification failed. "
                    "No verified comparison is available."
                )
                st.caption(f"Error type: {type(exc).__name__}")

        verification = st.session_state.get(verification_key)

        verified = (
            isinstance(verification, dict)
            and "historical" in verification
            and "current" in verification
            and verification["historical"]["wallet"] == wallet.lower()
            and verification["current"]["wallet"] == wallet.lower()
            and verification["historical"]["block_number"] == snapshot_block
        )

        if verified:
            historical = verification["historical"]
            current = verification["current"]

            c3, c4 = st.columns(2)

            historical_hf = historical["health_factor"]
            current_hf = current["health_factor"]

            c3.metric(
                "Aave Historical HF",
                f"{historical_hf:.6f}"
                if historical_hf is not None else "N/A — no debt",
            )
            c4.metric(
                "Aave Current HF",
                f"{current_hf:.6f}"
                if current_hf is not None else "N/A — no debt",
            )

            st.caption(
                f"Aave historical block: {historical['block_number']:,} | "
                f"Aave current verification block: {current['block_number']:,}. "
                "Both are unstressed on-chain readings."
            )

            comparison = compare_wallet_health_factors(
                baseline_hf,
                historical_hf,
                current_hf,
            )

            error = comparison["model_error_pct"]

            if error is None:
                st.info("HF model comparison unavailable for this wallet.")
            else:
                st.metric(
                    "Monitor vs Aave Historical Error",
                    f"{error:.9f}%",
                )
                if error >= Decimal("0.1"):
                    st.warning(
                        "Historical HF discrepancy exceeds the "
                        "0.1% diagnostic tolerance."
                    )

            if comparison["chain_delta"] is not None:
                st.caption(
                    "Historical-to-current on-chain HF change: "
                    f"{comparison['chain_delta']:+.6f}. "
                    "This is not the simulated shock effect."
                )

            if current_hf is None:
                st.info("No debt at the current verification block.")
            elif current_hf < 1:
                st.warning(
                    "Current on-chain HF is below 1 at the verification "
                    "block. This does not guarantee an executable liquidation."
                )

        else:
            st.caption(
                "Aave historical and current HF have not been verified "
                "for this wallet and snapshot block."
            )

        reserves = prepared.loc[
            prepared["wallet"].str.lower() == wallet.lower()
        ].copy()

        debt = reserves.loc[
            reserves["debt_raw"] > 0
        ]

        collateral = reserves.loc[
            (reserves["collateral_enabled"])
            & (reserves["atoken_balance_raw"] > 0)
        ]

        if debt.empty or collateral.empty:
            st.warning(
                "No eligible debt/collateral pair was found "
                "in the monitored position data."
            )
            return

        debt_asset = st.selectbox(
            "Debt asset to repay",
            debt["underlying"].tolist(),
            format_func=lambda address: debt.loc[
                debt["underlying"] == address, "symbol"
            ].iloc[0],
            key=f"{key}_debt",
        )

        collateral_asset = st.selectbox(
            "Collateral asset to seize",
            collateral["underlying"].tolist(),
            format_func=lambda address: collateral.loc[
                collateral["underlying"] == address, "symbol"
            ].iloc[0],
            key=f"{key}_collateral",
        )

        if st.button("Calculate indicative exposure", key=f"{key}_calculate"):
            try:
                ids = tuple(used_emode_ids(prepared))
                reserve_configs, emode_configs = load_liquidation_configs(ids, block_identifier=snapshot_block)

                exposure = estimate_wallet_liquidation(
                    prepared_raw=prepared,
                    stressed_prices=stressed_prices,
                    wallet=wallet,
                    stressed_hf=position["stressed_hf"],
                    debt_address=debt_asset,
                    collateral_address=collateral_asset,
                    reserve_configs=reserve_configs,
                    emode_configs=emode_configs,
                )

                a, b = st.columns(2)
                a.metric(
                    "Indicative debt repayable",
                    f"${float(exposure['repayable_debt_usd']):,.2f}",
                )
                b.metric(
                    "Indicative collateral seized",
                    f"${float(exposure['collateral_seized_usd']):,.2f}",
                )
                st.caption(
                    f"Modeled close factor: {exposure['close_factor']:.0%} | "
                    f"Liquidation bonus: {exposure['liquidation_bonus_pct']:.2%}"
                )

                st.markdown("#### Liquidation Fee Breakdown")

                c1, c2 = st.columns(2)

                c1.metric(
                    "Protocol Fee",
                    f"${float(exposure['protocol_fee_usd']):,.2f}",
                )

                c2.metric(
                    "Collateral to Liquidator",
                    f"${float(exposure['liquidator_collateral_usd']):,.2f}",
                )

                st.metric(
                    "Net Bonus Before Execution Costs",
                    f"${float(exposure['net_bonus_before_costs_usd']):,.2f}",
                )

                st.caption(
                    f"Protocol fee: {exposure['protocol_fee_bps'] / 100:.2f}% "
                    "of the gross liquidation bonus. "
                    "Net bonus excludes gas, slippage, flash-loan fees and other costs."
                )

                if exposure["passes_dust_check"]:
                    st.success(
                        "Preliminary dust check: Passed. "
                        "This does not guarantee an executable liquidation."
                    )
                else:
                    st.error(
                        "Preliminary dust check: Failed. "
                        "The proposed liquidation may leave prohibited "
                        "small debt or collateral balances."
                    )

                st.caption(
                    f"Remaining selected debt: "
                    f"${float(exposure['remaining_debt_asset_usd']):,.2f} | "
                    f"Remaining selected collateral: "
                    f"${float(exposure['remaining_collateral_asset_usd']):,.2f}"
                )

                st.warning(
                    "Indicative simulation only, not an executable liquidation quote. "
                    "Includes the modeled liquidation protocol fee. "
                    "Excludes slippage, gas, flash-loan fees, execution restrictions, "
                    "token-unit rounding and potential configuration changes."
                )
            except (ValueError, KeyError, RuntimeError) as exc:
                st.warning(f"Exposure unavailable: {exc}")

from wallet_liquidation import estimate_wallet_liquidation
from reserve_config_fetcher import fetch_reserve_configs
from emode_fetcher import fetch_emode_configs, used_emode_ids

@st.cache_data(ttl=300, show_spinner=False)
def load_liquidation_configs(emode_ids, block_identifier=None):
    from config_block_validation import validate_liquidation_config_blocks

    if block_identifier is None:
        raise ValueError(
            "Snapshot block required for liquidation configuration"
        )

    reserve_configs = fetch_reserve_configs(
        block_identifier=block_identifier
    )
    emode_configs = fetch_emode_configs(
        list(emode_ids),
        block_identifier=block_identifier,
    )

    validate_liquidation_config_blocks(
        snapshot_block=block_identifier,
        reserve_configs=reserve_configs,
        emode_configs=emode_configs,
    )

    return reserve_configs, emode_configs

def format_snapshot_time(timestamp):
    if timestamp is None:
        return "Unavailable"

    dt = datetime.fromtimestamp(
        int(timestamp),
        tz=timezone.utc,
    ).astimezone(ZoneInfo("Asia/Kuala_Lumpur"))

    return dt.strftime("%d %b %Y, %I:%M %p (GMT+8)")

st.set_page_config(
    page_title="Aave V3 Liquidation Risk Monitor",
    page_icon="⚠️",
    layout="wide"
)

st.caption(
    "Data reflects a historical Ethereum block, not continuously "
    "updated wallet balances. Liquidation estimates are hypothetical, "
    "not executable quotes."
)

st.title("⚠️ Aave V3 Liquidation Risk Monitor")
st.caption(
    "Ethereum Mainnet | Aave V3 positions via The Graph "
    "| Prices via Aave Oracle"
)

# ── Fetch data ──────────────────────────────────────────────
@st.cache_data(ttl=300, max_entries=2, show_spinner=False)
def load_positions(top_reserves, borrowers_per_reserve):
    from snapshot_context import select_snapshot_context
    from data_consistency import evaluate_data_freshness

    # Select a snapshot BEFORE loading borrower positions.
    graph_meta = d._gql(
        "{ _meta { block { number } hasIndexingErrors } }"
    )["_meta"]

    w3 = Web3(Web3.HTTPProvider(
        os.environ["ETH_RPC_URL"],
        request_kwargs={"timeout": 20},
    ))

    if w3.eth.chain_id != 1:
        raise RuntimeError("Expected Ethereum mainnet")

    context = select_snapshot_context(graph_meta, w3)

    positions, stats, prepared, prices = fetch_high_risk_positions(
        top_reserves=top_reserves,
        borrowers_per_reserve=borrowers_per_reserve,
        return_stats=True,
        return_inputs=True,
        block_identifier=context["snapshot_block"],
        block_timestamp=context["snapshot_timestamp"],
    )

    fetched_at = datetime.now(timezone.utc)

    freshness = evaluate_data_freshness(
        chain_block=context["chain_block"],
        graph_block=context["graph_block"],
        indexing_errors=bool(graph_meta.get("hasIndexingErrors", False)),
        max_lag_blocks=20,
    )

    freshness["snapshot_block"] = context["snapshot_block"]
    freshness["snapshot_timestamp"] = context["snapshot_timestamp"]
    freshness["positions_block_pinned"] = True
    freshness["historical_debt_verified"] = True

    # Overall consistency is not equivalent to current-wallet verification.
    freshness["block_consistent"] = False

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
        from data_integrity_errors import DataIntegrityError

        if isinstance(e, DataIntegrityError):
            st.error(
                "DATA INTEGRITY FAILURE — Historical on-chain "
                "verification failed. Recovery fallback is disabled "
                "to prevent presenting unverified positions."
            )
        else:
            st.error(
                "Unable to load Aave data from either the live sources "
                "or the GitHub recovery snapshot."
            )

        st.caption(f"Error type: {type(e).__name__}")
        st.stop()

st.subheader("Data Overview")

snapshot_block = freshness.get("snapshot_block")

verified = (
    data_source == "live"
    and freshness.get("historical_debt_verified") is True
)

c1, c2 = st.columns(2)

c1.metric(
    "Data source",
    "Live Ethereum snapshot" if data_source == "live"
    else "Saved recovery snapshot",
    help=(
        "The latest available Ethereum data retrieved by the monitor "
        "from The Graph and blockchain RPC. Data is captured at a "
        "specific block, not continuously streamed."
    ),
)

c2.metric(
    "Data as of",
    (
        f"Ethereum block #{snapshot_block:,}"
        if data_source == "live" and snapshot_block is not None
        else fetched_at.astimezone(
            ZoneInfo("Asia/Kuala_Lumpur")
        ).strftime("%d %b %Y, %I:%M %p (GMT+8)")
    ),
    help=(
        "Live data is aligned to a specific Ethereum block. "
        "Recovery data comes from a previously saved snapshot "
        "whose source reads were not necessarily block-aligned."
    ),
)

if data_source == "snapshot":
    st.warning(
        "⚠️ HISTORICAL SNAPSHOT — Live Aave data is unavailable. "
        f"Showing the last valid snapshot captured at "
        f"{fetched_at.astimezone(ZoneInfo('Asia/Kuala_Lumpur')):%d %b %Y, %I:%M %p} (GMT+8). "
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
    st.caption(
        "The Graph indexes Ethereum data independently. "
        "These metrics show how up to date its data is."
    )
    st.write(f"Ethereum head block: {freshness['chain_block']:,}")
    st.write(f"Subgraph indexed block: {freshness['graph_block']:,}")
    st.write(f"Indexing lag: {freshness['lag_blocks']} blocks")
    status = freshness["status"]
    st.write(
        "Position snapshot time:",
        format_snapshot_time(freshness.get("snapshot_timestamp")),
    )

    if freshness["lag_blocks"] < 0:
        st.error(
            "The subgraph reports a block ahead of this RPC provider. "
            "The sources may be out of sync."
        )


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

st.caption(
    "Coverage: This monitor analyzes a sampled subset of Aave V3 "
    "Ethereum borrowers, not the entire market. Wallets excluded "
    "because of missing prices or minimum debt requirements "
    "are not included in risk statistics."
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

st.divider()
st.subheader("Portfolio Risk Overview")

# ── Portfolio Risk Overview ──

hf = positions_df["health_factor"]

liquidatable = positions_df[hf < 1.0]
near_liquidation = positions_df[(hf >= 1.0) & (hf < 1.05)]
high = positions_df[(hf >= 1.05) & (hf < 1.20)]
elevated = positions_df[(hf >= 1.20) & (hf < 1.50)]
lower_risk = positions_df[hf >= 1.50]

total_debt_monitored = positions_df["debt_usd"].sum()
near_debt = near_liquidation["debt_usd"].sum()
liquidatable_debt = liquidatable["debt_usd"].sum()

debt_col1, debt_col2, debt_col3 = st.columns(3)

debt_col1.metric(
    "Positions Monitored",
    f"{len(positions_df):,}",
)

debt_col2.metric(
    "Total Debt Monitored",
    f"${total_debt_monitored:,.2f}",
)

debt_col3.metric(
    "Debt Near or Below Liquidation",
    f"${liquidatable_debt + near_debt:,.2f}",
    help="Combined outstanding debt of monitored wallets with "
         "HF below 1.05. This is not the amount immediately "
         "liquidatable or an estimate of realized losses.",
)

cols = st.columns(5)

cols[0].metric(
    "Liquidatable",
    f"{len(liquidatable):,}",
    help="Health Factor below 1.00. These positions meet "
         "Aave's HF liquidation eligibility condition.",
)

cols[1].metric(
    "Near Liquidation",
    f"{len(near_liquidation):,}",
    help="Health Factor from 1.00 to below 1.05. "
         "Monitor-defined risk category.",
)

cols[2].metric(
    "High Risk",
    f"{len(high):,}",
    help="Health Factor from 1.05 to below 1.20. "
         "Monitor-defined risk category.",
)

cols[3].metric(
    "Elevated Risk",
    f"{len(elevated):,}",
    help="Health Factor from 1.20 to below 1.50. "
         "Monitor-defined risk category.",
)

cols[4].metric(
    "Lower Risk",
    f"{len(lower_risk):,}",
    help="Health Factor of 1.50 or above. "
         "Does not mean risk-free.",
)

if (
    len(liquidatable)
    + len(near_liquidation)
    + len(high)
    + len(elevated)
    + len(lower_risk)
    != len(positions_df)
):
    st.error("Risk category accounting mismatch detected.")

st.caption(
    "Risk categories above HF 1.00 are monitor-defined. "
    "Aave liquidation eligibility begins below HF 1.00."
)

# ── Section 1: Risk Distribution ─────────────────────────────
st.divider()
st.subheader("Health Factor Distribution")

risk_order = [
    "Liquidatable",
    "Near Liquidation",
    "High Risk",
    "Elevated Risk",
    "Lower Risk",
]

risk_colors = {
    "Liquidatable": "#d62728",
    "Near Liquidation": "#ff7f0e",
    "High Risk": "#e6b800",
    "Elevated Risk": "#4c78a8",
    "Lower Risk": "#2ca02c",
}

risk_labels = [
    "Liquidatable (< 1.00)",
    "Near Liquidation (1.00–1.05)",
    "High Risk (1.05–1.20)",
    "Elevated (1.20–1.50)",
    "Lower Risk (≥ 1.50)",
]

risk_distribution = pd.DataFrame({
    "Risk Category": risk_labels,
    "Positions": [
        len(liquidatable),
        len(near_liquidation),
        len(high),
        len(elevated),
        len(lower_risk),
    ],
})

risk_colors = dict(zip(
    risk_labels,
    ["#d62728", "#ff7f0e", "#e6b800", "#4c78a8", "#2ca02c"],
))

fig_risk = px.bar(
    risk_distribution,
    x="Risk Category",
    y="Positions",
    color="Risk Category",
    color_discrete_map=risk_colors,
    category_orders={"Risk Category": risk_labels},
    text="Positions",
)

fig_risk.update_traces(
    textposition="outside",
    hovertemplate="%{x}: %{y:,} positions<extra></extra>",
)

fig_risk.update_layout(
    showlegend=False,
    yaxis_title="Number of Positions",
    xaxis_title=None,
    margin=dict(t=30, b=20),
)

st.plotly_chart(fig_risk, width="stretch")

st.caption(
    "Health Factor below 1.00 indicates liquidation eligibility. "
    "Other ranges are monitoring categories, not official Aave tiers."
)
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

st.subheader("Asset-Specific Price Shock")
st.caption(
    "Explore how changing one asset's price affects monitored wallets. "
    "Results are hypothetical."
)

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

        asset_col, shock_col = st.columns([1, 2])

        with asset_col:
            asset_label = st.selectbox(
                "Asset",
                options=list(options),
            )

        with shock_col:
            drop_pct = st.slider(
                "Price decrease (%)",
                min_value=0,
                max_value=80,
                value=20,
                step=5,
            )

        try:
            result, stressed_prices_result = simulate_price_shock(
                prepared,
                prices,
                {options[asset_label]: -drop_pct / 100},
                return_prices=True,
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
                "Simulated liquidation eligibility, not actual liquidations. "
                "Debt shown is outstanding debt, not expected losses."
            )

            st.markdown("#### 20 Lowest Simulated Health Factors")

            st.caption(
                "Lowest simulated HF among monitored wallets, including those "
                "unaffected by the selected asset. "
                "HF Change = simulated HF − baseline HF."
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

            show_liquidation_wallet_selector(
                result,
                prepared,
                stressed_prices_result,
                "single_asset",
                snapshot_block=freshness.get("snapshot_block"),
                data_source=data_source,
                scenario_inputs_present=scenario_inputs is not None,
                historical_debt_verified=verified,
            )

        except ValueError as exc:
            st.warning(
                "This scenario could not be compared consistently: "
                f"{exc}"
            )

        st.divider()
        st.subheader("Multi-Asset Stress Scenario")
        st.caption(
            "Combine price changes using a preset scenario or your own assumptions."
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
            help="Presets are illustrative stress assumptions, not forecasts.",
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
                    f"{label} change (%)",
                    min_value=-80,
                    max_value=100,
                    value=-20,
                    step=5,
                    key=f"custom_{asset_options[label]}",
                )
                if pct != 0:
                    changes[asset_options[label]] = pct / 100

        else:
            changes, missing_assets = resolve_preset(scenario, assets)

            if missing_assets:
                st.error(
                    "INCOMPLETE SCENARIO — Missing priced assets: "
                    + ", ".join(missing_assets)
                    + ". Results do not represent the full preset."
                )

        if changes:
            st.markdown("#### Scenario Price Changes")

            st.caption(
                "Price changes apply to each selected token across monitored wallets."
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
                column_config={
                    "Current Oracle Price (USD)": st.column_config.NumberColumn(
                        "Current Oracle Price (USD)",
                        format="$%.2f",
                    ),
                    "Simulated Price Change (%)": st.column_config.NumberColumn(
                        "Simulated Price Change (%)",
                        format="%.2f%%",
                    ),
                    "Simulated Price (USD)": st.column_config.NumberColumn(
                        "Simulated Price (USD)",
                        format="$%.2f",
                    ),
                },
                width="stretch",
                hide_index=True,
            )

            try:
                multi_result, stressed_prices_multi_result = simulate_price_shock(
                    prepared,
                    prices,
                    changes,
                    return_prices=True,
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

                show_liquidation_wallet_selector(
                    multi_result,
                    prepared,
                    stressed_prices_multi_result,
                    "multi_asset",
                    snapshot_block=freshness.get("snapshot_block"),
                    data_source=data_source,
                    scenario_inputs_present=scenario_inputs is not None,
                    historical_debt_verified=verified,
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
