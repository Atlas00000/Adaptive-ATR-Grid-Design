#!/usr/bin/env python3
"""AI-805m: Grid sweep for basket cap + surgical cascade params (offline)."""
from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from basket_replay import load_window_legs, simulate_health_replay
from simulate_policy import equity_metrics


def load_baskets(cfg: dict, window: str) -> pd.DataFrame:
    path = ROOT / "features" / "baskets.parquet"
    df = pd.read_parquet(path)
    df["open_time"] = pd.to_datetime(df["open_time"])
    if ":" in window:
        start, end = window.split(":", 1)
        mask = (df["open_time"] >= pd.Timestamp(start)) & (
            df["open_time"] <= pd.Timestamp(end) + pd.Timedelta(days=1)
        )
        return df.loc[mask].copy().sort_values("open_time").reset_index(drop=True)
    return df.loc[df["window"].astype(str) == window].copy().sort_values("open_time").reset_index(drop=True)


def run_sweep(
    baskets: pd.DataFrame,
    legs: pd.DataFrame,
    cfg: dict,
    *,
    cap_values: list[float],
    cascade_values: list[float],
) -> pd.DataFrame:
    rows = []
    for cap_usd, cascade_loss in product(cap_values, cascade_values):
        sim = simulate_health_replay(
            baskets,
            legs,
            mode="flatten_only",
            flatten_at=cfg["thresholds"]["health_flatten"],
            no_add_at=cfg["thresholds"]["health_no_add"],
            checkpoint_sec=60,
            flatten_float=-18.0,
            stress_flatten_at=75.0,
            hard_cap_enabled=True,
            hard_cap_usd=-25.0,
            hard_cap_l1_enabled=True,
            hard_cap_l1_usd=-28.0,
            hard_cap_l1_min_sec=30.0,
            basket_cap_enabled=True,
            basket_cap_usd=cap_usd,
            basket_cap_min_legs=2,
            sl_cascade_enabled=True,
            sl_cascade_min_legs=2,
            sl_cascade_loss_usd=cascade_loss,
            sl_cascade_use_float=False,
        )
        m = equity_metrics(sim["sim_pnl"])
        worst = float(sim["sim_pnl"].min())
        caps = int((sim["health_intervention"] == "basket_cap").sum())
        cascades = int((sim["health_intervention"] == "sl_cascade").sum())
        rows.append(
            {
                "basket_cap_usd": cap_usd,
                "cascade_loss_usd": cascade_loss,
                "net": m["net"],
                "pf": round(m["pf"], 3),
                "trades": m["trades"],
                "max_dd_pct": round(m["max_dd_pct"], 1),
                "worst_basket": round(worst, 2),
                "basket_cap_n": caps,
                "sl_cascade_n": cascades,
                "tail_ok": worst > -35.0,
                "net_ok": m["net"] >= 560.0,
            }
        )
    out = pd.DataFrame(rows).sort_values(
        ["tail_ok", "net_ok", "net"], ascending=[False, False, False]
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-805m parameter sweep")
    parser.add_argument("--window", default="w02", help="Diagnostics window prefix")
    parser.add_argument(
        "--caps",
        default="-28,-30,-32,-35",
        help="Comma-separated basket cap USD values",
    )
    parser.add_argument(
        "--cascade",
        default="-12,-15,-18",
        help="Comma-separated cascade loss USD values",
    )
    parser.add_argument("--top", type=int, default=10, help="Rows to print")
    args = parser.parse_args()

    cfg = load_config()
    baskets = load_baskets(cfg, args.window)
    export_dir = ROOT / cfg["paths"]["export_dir"]
    legs = load_window_legs(export_dir, args.window)
    keys = set(baskets["basket_key"].astype(str))
    legs = legs.loc[legs["basket_key"].isin(keys)].copy()

    cap_values = [float(x) for x in args.caps.split(",")]
    cascade_values = [float(x) for x in args.cascade.split(",")]

    baseline = equity_metrics(baskets["basket_pnl"])
    print(f"Baseline: net={baseline['net']:.2f} pf={baseline['pf']:.3f} "
          f"worst={baskets['basket_pnl'].min():.2f}")
    print()

    result = run_sweep(
        baskets,
        legs,
        cfg,
        cap_values=cap_values,
        cascade_values=cascade_values,
    )
    print(result.head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
