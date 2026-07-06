#!/usr/bin/env python3
"""AI-806 Step 2: One row per L0 basket arm with leak-free open features + regime labels."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from build_baskets import aggregate_file, apply_tail_loss_label, window_from_path
from build_features import regime_from_atr_pct

TRADE_GLOB = "AI806_*_trades_*.csv"
TAIL_USD = 20.0

REGIME_FEATURES = [
    "adx",
    "atr",
    "atr_pips",
    "atr_pct_100",
    "hour",
    "weekday",
    "month",
    "bias_buy",
    "bad_hour",
    "rolling_pf_7d",
    "rolling_wr_10",
    "consec_losses",
    "prior_day_atr_max",
    "label_regime_rotation",
]


def _rolling_pf(pnl: pd.Series, window: int) -> pd.Series:
    def pf(x: np.ndarray) -> float:
        wins = x[x > 0].sum()
        losses = abs(x[x < 0].sum())
        if losses == 0:
            return float(wins > 0)
        return float(wins / losses)

    return pnl.shift(1).rolling(window, min_periods=3).apply(pf, raw=True)


def _consecutive_losses(won: pd.Series) -> pd.Series:
    streak = 0
    out: list[int] = []
    for w in won.shift(1):
        if pd.isna(w):
            out.append(0)
            continue
        if not bool(w):
            streak += 1
        else:
            streak = 0
        out.append(streak)
    return pd.Series(out, index=won.index, dtype=int)


def _prior_day_atr_max(open_time: pd.Series, atr: pd.Series) -> pd.Series:
    day = open_time.dt.normalize()
    daily_max = pd.Series(atr.values, index=open_time.index).groupby(day).transform("max")
    prior_day = day - pd.Timedelta(days=1)
    lookup = daily_max.groupby(day).first()
    return prior_day.map(lookup)


def label_from_baskets(baskets: pd.DataFrame) -> pd.DataFrame:
    """Build L0-open rows with chronologically leak-free features per window."""
    rows: list[pd.DataFrame] = []
    for window, grp in baskets.groupby("window", sort=True):
        g = grp.sort_values("open_time").copy()
        g["open_time"] = pd.to_datetime(g["open_time"])

        g["adx"] = g["entry_adx"].astype(float)
        g["atr"] = g["entry_atr"].astype(float)
        g["atr_pips"] = g["atr"] * 10_000.0
        atr_med = g["atr"].shift(1).rolling(100, min_periods=10).median()
        g["atr_pct_100"] = np.where(atr_med > 0, g["atr"] / atr_med, np.nan)

        g["hour"] = g["open_time"].dt.hour
        g["weekday"] = g["open_time"].dt.dayofweek
        g["month"] = g["open_time"].dt.month
        g["bias_buy"] = (g["bias"].str.upper() == "BUY").astype(int)
        g["bad_hour"] = g["bad_hour"].astype(int)

        pnl = g["basket_pnl"].astype(float)
        won = g["basket_won"].astype(bool)
        ts = g.set_index("open_time")
        prior_pnl = ts["basket_pnl"].shift(1)

        def _pf_series(s: pd.Series) -> float:
            x = s.values
            wins = x[x > 0].sum()
            losses = abs(x[x < 0].sum())
            if losses == 0:
                return float(wins > 0)
            return float(wins / losses)

        g["rolling_pf_7d"] = (
            prior_pnl.rolling("7D", min_periods=3).apply(_pf_series, raw=False).values
        )
        g["rolling_wr_10"] = won.shift(1).rolling(10, min_periods=3).mean()
        g["rolling_pf_20"] = _rolling_pf(pnl, 20)
        g["consec_losses"] = _consecutive_losses(won)
        g["prior_day_atr_max"] = _prior_day_atr_max(g["open_time"], g["atr"])

        g["label_regime"] = regime_from_atr_pct(g["atr_pct_100"])
        g["label_regime_rotation"] = (g["label_regime"] == "rotation").astype(int)

        g["basket_pnl"] = pnl
        g["is_tail"] = (pnl < -TAIL_USD).astype(int)
        g["is_d2_plus"] = (g["max_level"] >= 2).astype(int)
        g["is_d2_loss"] = ((g["max_level"] >= 2) & (pnl < 0)).astype(int)
        g["label_bad_basket"] = ((g["is_tail"] == 1) | (g["is_d2_loss"] == 1)).astype(int)
        g["label_negative_ev"] = (pnl < 0).astype(int)

        rows.append(g)

    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["window", "open_time"]).reset_index(drop=True)


def audit_buckets(baskets: pd.DataFrame, summary_path: Path | None, label: str) -> None:
    print(f"\n[AI-806] Audit — {label}")
    print("-" * 72)
    for window, grp in baskets.groupby("window", sort=True):
        n = len(grp)
        net = grp["basket_pnl"].sum()
        bad = grp["label_bad_basket"].mean()
        tail = grp["is_tail"].mean()
        d2l = grp["is_d2_loss"].mean()
        print(
            f"  {window:16s}  opens={n:4d}  net=${net:8.2f}  "
            f"bad={100*bad:4.1f}%  tail={100*tail:4.1f}%  D2loss={100*d2l:4.1f}%"
        )

        grp = grp.copy()
        ot = grp["open_time"]
        grp["period"] = np.select(
            [
                ot < pd.Timestamp("2025-01-01"),
                ot < pd.Timestamp("2025-07-01"),
            ],
            ["2024", "2025-H1"],
            default="2025-H2+",
        )
        for period, sub in grp.groupby("period", sort=True):
            if len(sub) < 5:
                continue
            print(
                f"    {period:8s}  n={len(sub):3d}  net=${sub['basket_pnl'].sum():7.1f}  "
                f"bad={100*sub['label_bad_basket'].mean():4.1f}%  "
                f"D2loss={100*sub['is_d2_loss'].mean():4.1f}%"
            )

    if summary_path and summary_path.is_file():
        sm = pd.read_csv(summary_path)
        d2 = sm[(sm["section"] == "basket_depth") & (sm["bucket"] == "D2")]
        if len(d2):
            print(f"  summary D2: trades={int(d2.iloc[0]['trades'])} pl=${d2.iloc[0]['total_pl']:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Label basket opens for AI-806 regime skip")
    parser.add_argument("--input", type=Path, default=ROOT / "export")
    parser.add_argument("--glob", default=TRADE_GLOB)
    parser.add_argument("--baskets", type=Path, default=ROOT / "features" / "baskets_ai806.parquet")
    parser.add_argument("--output", type=Path, default=ROOT / "features" / "basket_opens.parquet")
    parser.add_argument("--csv", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config()

    files = sorted(args.input.glob(args.glob))
    if not files:
        raise SystemExit(f"No files matching {args.glob!r} in {args.input}")

    print(f"[AI-806] label_basket_opens — {len(files)} export(s)")
    for f in files:
        print(f"  - {f.name}")

    parts = [aggregate_file(p) for p in files]
    baskets = pd.concat(parts, ignore_index=True)
    baskets = apply_tail_loss_label(baskets, tail_usd=TAIL_USD)

    args.baskets.parent.mkdir(parents=True, exist_ok=True)
    baskets.to_parquet(args.baskets, index=False)

    labeled = label_from_baskets(baskets)

    meta_cols = [
        "window",
        "basket_id",
        "basket_key",
        "open_time",
        "close_time",
        "bias",
        "max_level",
        "levels_filled",
        "source_file",
    ]
    label_cols = [
        "basket_pnl",
        "is_tail",
        "is_d2_plus",
        "is_d2_loss",
        "label_bad_basket",
        "label_negative_ev",
        "tail_loss",
        "label_regime",
    ]
    keep = meta_cols + REGIME_FEATURES + label_cols
    out = labeled[[c for c in keep if c in labeled.columns]].copy()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.output, index=False)
    csv_path = args.csv or args.output.with_suffix(".csv")
    out.to_csv(csv_path, index=False)

    print(f"\n  baskets: {args.baskets} ({len(baskets)} rows)")
    print(f"  opens:   {args.output} ({len(out)} rows)")
    print(f"  csv:     {csv_path}")
    print(
        f"  labels: bad_basket={out['label_bad_basket'].mean():.1%} | "
        f"tail={out['is_tail'].mean():.1%} | D2loss={out['is_d2_loss'].mean():.1%}"
    )

    for f in files:
        window = window_from_path(f)
        summary = f.parent / f.name.replace("_trades_", "_summary_")
        audit_buckets(out[out["window"] == window], summary if summary.is_file() else None, window)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
