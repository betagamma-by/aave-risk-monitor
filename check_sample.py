import data_fetcher as d

for top, per in [(5, 15), (8, 25)]:
    print(f"\n=== top_reserves={top}, borrowers_per_reserve={per} ===")
    df = d.fetch_high_risk_positions(top_reserves=top, borrowers_per_reserve=per)
    print("wallets:", len(df), "| total debt $M:", round(df["debt_usd"].sum() / 1e6, 1))
    print(df["risk_tier"].value_counts().to_string())
    print("debt by primary collateral ($M):")
    print((df.groupby("primary_collateral")["debt_usd"].sum() / 1e6).round(1)
          .sort_values(ascending=False).head(8).to_string())
    print(df.nsmallest(5, "health_factor")[["wallet_full", "health_factor", "emode_id",
          "primary_collateral", "debt_usd"]].to_string(index=False))