"""Conservative correction for tiny negative subgraph debt dust."""

from decimal import Decimal, InvalidOperation


def normalize_negative_debt_dust(raw):
    result = raw.copy()
    corrected = 0

    for idx, row in result.iterrows():
        try:
            scaled = Decimal(str(row["scaled_vdebt_raw"]))
            stable = Decimal(str(row["stable_debt_raw"]))
            total = Decimal(str(row["debt_raw"]))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("Invalid source debt data") from exc

        if not all(x.is_finite() for x in (scaled, stable, total)):
            raise ValueError("Non-finite source debt data")

        if scaled >= 0:
            if stable < 0 or total < 0:
                raise ValueError(
                    f"Unexpected negative source debt: "
                    f"{row['wallet']} {row['symbol']}"
                )
            continue

        # Tiny subgraph indexing dust; never correct meaningful debt.
        if (
            Decimal("-10") <= scaled < 0
            and stable == 0
            and Decimal("-20") <= total <= Decimal("20")
        ):
            result.at[idx, "scaled_vdebt_raw"] = "0"
            result.at[idx, "debt_raw"] = "0"
            corrected += 1
        else:
            raise ValueError(
                f"Untrusted negative source debt: "
                f"{row['wallet']} {row['symbol']}, "
                f"scaled={scaled}, stable={stable}, total={total}"
            )

    if corrected:
        print(
            f"F16: Normalized {corrected} tiny negative "
            "subgraph debt balances"
        )

    return result
