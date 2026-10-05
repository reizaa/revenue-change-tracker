"""Compare current recurring revenue per account with a previous snapshot.

Categories (per account, on annualized value = monthly x 12):
  new        present now, absent (or zero) in the baseline
  churn      present in the baseline, absent (or zero) now
  upgrade    present in both, annualized value went up
  downgrade  present in both, annualized value went down

Foreign-currency accounts can move only because the exchange rate moved. The
diff of every account is therefore split into a price effect (the local amount
changed) and an FX effect (same local amount, different rate), and accounts
whose change is pure FX are reported separately instead of as up/downgrades.
"""
import pandas as pd

TOP_N = 15
KEY = "account_id"


def compare(base: pd.DataFrame, cur: pd.DataFrame) -> pd.DataFrame:
    cols = [KEY, "plan_tier", "currency", "local_monthly", "fx_rate", "monthly_revenue"]
    m = base[cols].merge(cur[cols], on=KEY, how="outer", suffixes=("_base", "_now"))
    for side in ("base", "now"):
        m[f"monthly_revenue_{side}"] = m[f"monthly_revenue_{side}"].fillna(0)
        m[f"local_monthly_{side}"] = m[f"local_monthly_{side}"].fillna(0)
        m[f"annual_{side}"] = m[f"monthly_revenue_{side}"] * 12
    m["plan_tier"] = m["plan_tier_now"].fillna(m["plan_tier_base"])
    m["currency"] = m["currency_now"].fillna(m["currency_base"])
    m["annual_diff"] = m["annual_now"] - m["annual_base"]

    both = (m["annual_base"] > 0) & (m["annual_now"] > 0)
    # FX effect: what the diff would have been with an unchanged local amount
    fx_effect = (m["local_monthly_base"] * (m["fx_rate_now"] - m["fx_rate_base"]) * 12)
    m["fx_effect"] = fx_effect.where(both, 0).round(2)
    m["price_effect"] = (m["annual_diff"] - m["fx_effect"]).round(2)

    m["category"] = "unchanged"
    m.loc[(m["annual_base"] == 0) & (m["annual_now"] > 0), "category"] = "new"
    m.loc[(m["annual_base"] > 0) & (m["annual_now"] == 0), "category"] = "churn"
    # classify on the local (contract) amount so rounding noise from FX never
    # turns into a fake upgrade or downgrade
    local_up = m["local_monthly_now"] > m["local_monthly_base"]
    local_down = m["local_monthly_now"] < m["local_monthly_base"]
    m.loc[both & local_up, "category"] = "upgrade"
    m.loc[both & local_down, "category"] = "downgrade"
    m.loc[both & ~local_up & ~local_down & (m["annual_diff"] != 0), "category"] = "fx_only"
    keep = [KEY, "plan_tier", "currency", "category", "annual_base", "annual_now",
            "annual_diff", "price_effect", "fx_effect"]
    return m[keep].sort_values("annual_diff", key=abs, ascending=False).reset_index(drop=True)


def summary(detail: pd.DataFrame, base_total: float, cur_total: float) -> pd.DataFrame:
    g = detail.groupby("category").agg(accounts=(KEY, "count"),
                                       annual_diff=("annual_diff", "sum"),
                                       price_effect=("price_effect", "sum"),
                                       fx_effect=("fx_effect", "sum"))
    order = ["new", "upgrade", "downgrade", "churn", "fx_only", "unchanged"]
    g = g.reindex(order, fill_value=0).reset_index()
    total = pd.DataFrame([{"category": "TOTAL", "accounts": int(g["accounts"].sum()),
                           "annual_diff": g["annual_diff"].sum(),
                           "price_effect": g["price_effect"].sum(),
                           "fx_effect": g["fx_effect"].sum()}])
    g = pd.concat([g, total], ignore_index=True)
    # bridge check: baseline ARR + every category's diff = current ARR
    g.attrs["bridge_ok"] = abs(base_total * 12 + g.iloc[-1]["annual_diff"] - cur_total * 12) < 0.01
    return g.round(2)


def top_movers(detail: pd.DataFrame, n: int = TOP_N) -> dict:
    out = {}
    for cat, ascending in [("new", False), ("upgrade", False),
                           ("downgrade", True), ("churn", True)]:
        out[cat] = (detail[detail["category"] == cat]
                    .sort_values("annual_diff", ascending=ascending).head(n)
                    .reset_index(drop=True))
    return out
