#!/usr/bin/env python3
"""AI-802: Build leak-free feature matrix + walk-forward splits from baskets."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config

SESSION_START_HOUR = 15
SESSION_END_HOUR = 17

ENTRY_SAFE_FEATURES = [
    "adx",
    "atr",
    "atr_pips",
    "atr_pct_100",
    "hour",
    "minute",
    "minute_in_session",
    "weekday",
    "month",
    "bias_buy",
    "bad_hour",
    "rolling_wr_10",
    "rolling_wr_20",
    "rolling_pf_20",
    "rolling_avg_dd_20",
]

HEALTH_FEATURES = [
    "grid_depth",
    "floating_pl",
    "seconds_open",
    "atr_delta",
    "adx_delta",
    "dist_anchor_atr",
    "mfe_so_far",
    "mae_so_far",
]

LABEL_COLUMNS = [
    "label_basket_won",
    "label_tail_loss",
    "label_health_severe",
    "label_regime",
    "label_regime_rotation",
]

META_COLUMNS = [
    "basket_key",
    "window",
    "open_time",
    "close_time",
    "basket_pnl",
    "wf_fold",
    "wf_split",
]


def _rolling_pf(pnl: pd.Series, window: int) -> pd.Series:
    def pf(x: np.ndarray) -> float:
        wins = x[x > 0].sum()
        losses = abs(x[x < 0].sum())
        if losses == 0:
            return float(wins > 0)
        return float(wins / losses)

    return pnl.shift(1).rolling(window, min_periods=3).apply(pf, raw=True)


def session_minute_in_window(ts: pd.Series) -> pd.Series:
    """Minutes elapsed from session start (15:00) for production window."""
    minutes = ts.dt.hour * 60 + ts.dt.minute
    start = SESSION_START_HOUR * 60
    end = SESSION_END_HOUR * 60
    mid = minutes.clip(lower=start, upper=end)
    return mid - start


def regime_from_atr_pct(atr_pct: pd.Series) -> pd.Series:
    """Regime proxy when ADX is capped by EA gate (~20). Uses vol percentile."""
    return pd.Series(
        np.where(
            atr_pct < 0.90,
            "compression",
            np.where(atr_pct > 1.10, "expansion", "rotation"),
        ),
        index=atr_pct.index,
    )


def compute_group_features(group: pd.DataFrame) -> pd.DataFrame:
    """Leak-free features computed within one backtest window (chronological)."""
    g = group.sort_values("open_time").copy()
    g["open_time"] = pd.to_datetime(g["open_time"])
    g["close_time"] = pd.to_datetime(g["close_time"])

    # --- entry context (known at basket open) ---
    g["adx"] = g["entry_adx"].astype(float)
    g["atr"] = g["entry_atr"].astype(float)
    g["atr_pips"] = g["atr"] * 10_000.0

    atr_med = g["atr"].shift(1).rolling(100, min_periods=10).median()
    g["atr_pct_100"] = np.where(atr_med > 0, g["atr"] / atr_med, np.nan)

    g["hour"] = g["open_time"].dt.hour
    g["minute"] = g["open_time"].dt.minute
    g["minute_in_session"] = session_minute_in_window(g["open_time"])
    g["weekday"] = g["open_time"].dt.dayofweek
    g["month"] = g["open_time"].dt.month
    g["bias_buy"] = (g["bias"].str.upper() == "BUY").astype(int)
    g["bad_hour"] = g["bad_hour"].astype(int)

    won = g["basket_won"].astype(float)
    pnl = g["basket_pnl"].astype(float)
    dd = g["path_mae"].clip(upper=0).abs()

    g["rolling_wr_10"] = won.shift(1).rolling(10, min_periods=3).mean()
    g["rolling_wr_20"] = won.shift(1).rolling(20, min_periods=5).mean()
    g["rolling_pf_20"] = _rolling_pf(pnl, 20)
    g["rolling_avg_dd_20"] = dd.shift(1).rolling(20, min_periods=5).mean()

    # --- health / close-state (for AI-805 offline training) ---
    g["grid_depth"] = g["max_level"].astype(int)
    g["floating_pl"] = g["basket_pnl"].astype(float)
    g["seconds_open"] = g["hold_sec"].astype(int)
    g["atr_delta"] = g["atr"].diff()
    g["adx_delta"] = g["adx"].diff()
    g["mfe_so_far"] = g["path_mfe"].astype(float)
    g["mae_so_far"] = g["path_mae"].astype(float)
    g["dist_anchor_atr"] = np.where(
        g["atr"] > 0,
        g["worst_leg"].abs() / g["atr"],
        np.nan,
    )

    # --- labels ---
    g["label_basket_won"] = g["basket_won"].astype(int)
    g["label_tail_loss"] = g["tail_loss"].astype(int)
    g["label_health_severe"] = (g["basket_pnl"] < -20.0).astype(int)
    g["label_regime"] = regime_from_atr_pct(g["atr_pct_100"])
    g["label_regime_rotation"] = (g["label_regime"] == "rotation").astype(int)

    # placeholders until bar-level join (AI-802b)
    g["rsi"] = np.nan
    g["ema_slope"] = np.nan
    g["spread_pips"] = np.nan

    return g


def assign_walk_forward(
    df: pd.DataFrame,
    train_months: int,
    test_months: int,
) -> pd.DataFrame:
    """Expand baskets into walk-forward rows (one basket may appear in multiple folds)."""
    base = df.copy()
    base["period"] = base["open_time"].dt.to_period("M")
    months = sorted(base["period"].unique())

    chunks: list[pd.DataFrame] = []
    fold = 0
    i = train_months
    while i < len(months):
        test_periods = months[i : i + test_months]
        train_periods = months[i - train_months : i]
        if not test_periods:
            break

        mask = base["period"].isin(train_periods + test_periods)
        chunk = base.loc[mask].copy()
        chunk["wf_fold"] = fold
        chunk["wf_split"] = np.where(
            chunk["period"].isin(test_periods),
            "test",
            "train",
        )
        chunks.append(chunk)
        fold += 1
        i += test_months

    if not chunks:
        out = base.copy()
        out["wf_fold"] = -1
        out["wf_split"] = "none"
        return out.drop(columns=["period"])

    return pd.concat(chunks, ignore_index=True).drop(columns=["period"])


def correlation_report(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    threshold: float = 0.85,
) -> dict:
    rows = []
    leaks = []
    y = df[label_col]
    for col in feature_cols:
        if col not in df.columns:
            continue
        x = df[col]
        mask = x.notna() & y.notna()
        if mask.sum() < 20:
            corr = None
        else:
            corr = float(x[mask].corr(y[mask]))
        row = {"feature": col, "label": label_col, "correlation": corr, "n": int(mask.sum())}
        rows.append(row)
        if corr is not None and abs(corr) > threshold:
            leaks.append(row)

    return {"pairs": rows, "leak_warnings": leaks, "threshold": threshold}


def label_summary(df: pd.DataFrame) -> dict:
    return {
        "basket_won_rate": float(df["label_basket_won"].mean()),
        "tail_loss_rate": float(df["label_tail_loss"].mean()),
        "health_severe_rate": float(df["label_health_severe"].mean()),
        "regime_rotation_rate": float(df["label_regime_rotation"].mean()),
        "regime_counts": df["label_regime"].value_counts().to_dict(),
    }


def print_report(df: pd.DataFrame, report: dict, wf_window: str, wf_expanded: pd.DataFrame) -> None:
    print("\n[AI-802] Label rates")
    for k, v in report["labels"].items():
        if k == "regime_counts":
            print(f"  regime: {v}")
        else:
            print(f"  {k}: {v:.1%}" if isinstance(v, float) else f"  {k}: {v}")

    wf = wf_expanded
    n_folds = int(wf["wf_fold"].max()) + 1 if len(wf) and wf["wf_fold"].max() >= 0 else 0
    n_train = int((wf["wf_split"] == "train").sum())
    n_test = int((wf["wf_split"] == "test").sum())
    print(f"\n[AI-802] Walk-forward ({wf_window})")
    print(f"  folds: {n_folds} | wf rows: {len(wf)} | train: {n_train} | test: {n_test}")

    print("\n[AI-802] Leakage check (entry features vs basket_won)")
    if report["leakage_entry"]["leak_warnings"]:
        for w in report["leakage_entry"]["leak_warnings"]:
            print(f"  WARN  {w['feature']}: r={w['correlation']:.3f}")
    else:
        print("  PASS  no entry feature |r| > 0.85")

    missing = report["missing_entry_features"]
    if missing:
        print(f"\n[AI-802] Pending bar join: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ML features from baskets")
    parser.add_argument("--input", type=Path, default=ROOT / "features" / "baskets.parquet")
    parser.add_argument("--output", type=Path, default=ROOT / "features" / "train.parquet")
    parser.add_argument(
        "--windows",
        default="all",
        help="Comma-separated window names or 'all'",
    )
    parser.add_argument(
        "--walk-forward-window",
        default="w02_ext19mo",
        help="Window used for walk-forward fold assignment",
    )
    args = parser.parse_args()

    cfg = load_config()
    train_m = cfg["walk_forward"]["train_months"]
    test_m = cfg["walk_forward"]["test_months"]

    print(f"[AI-802] build_features — {train_m}m train / {test_m}m test")

    baskets = pd.read_parquet(args.input)
    baskets["open_time"] = pd.to_datetime(baskets["open_time"])

    if args.windows != "all":
        keep = {w.strip() for w in args.windows.split(",")}
        baskets = baskets[baskets["window"].isin(keep)].copy()
        if baskets.empty:
            raise SystemExit(f"No baskets for windows: {keep}")

    parts = [compute_group_features(g) for _, g in baskets.groupby("window", sort=True)]
    featured = pd.concat(parts, ignore_index=True).sort_values(["window", "open_time"])

    wf_mask = featured["window"] == args.walk_forward_window
    wf_base = featured.loc[wf_mask].copy()
    wf_expanded = assign_walk_forward(wf_base, train_m, test_m)

    featured["wf_fold"] = -1
    featured["wf_split"] = "holdout"
    featured.loc[~wf_mask, "wf_split"] = "holdout"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    featured.to_parquet(args.output, index=False)
    featured.to_csv(args.output.with_suffix(".csv"), index=False)

    folds_path = args.output.parent / "train_folds.parquet"
    wf_expanded.to_parquet(folds_path, index=False)

    entry_cols = list(
        dict.fromkeys(
            META_COLUMNS
            + ENTRY_SAFE_FEATURES
            + LABEL_COLUMNS
            + ["wf_fold", "wf_split"]
        )
    )
    entry_cols = [c for c in entry_cols if c in featured.columns]
    entry_path = args.output.parent / "train_entry.parquet"
    featured[entry_cols].to_parquet(entry_path, index=False)

    health_cols = list(
        dict.fromkeys(
            META_COLUMNS
            + HEALTH_FEATURES
            + ["label_tail_loss", "label_health_severe", "wf_fold", "wf_split"]
        )
    )
    health_cols = [c for c in health_cols if c in featured.columns]
    health_path = args.output.parent / "train_health.parquet"
    featured[health_cols].to_parquet(health_path, index=False)

    wf_eval = wf_expanded
    report = {
        "rows": len(featured),
        "wf_rows": len(wf_expanded),
        "windows": featured["window"].value_counts().to_dict(),
        "labels": label_summary(featured),
        "labels_w02": label_summary(featured[featured["window"] == args.walk_forward_window]),
        "missing_entry_features": ["rsi", "ema_slope", "spread_pips"],
        "leakage_entry": correlation_report(
            wf_eval[wf_eval["wf_split"].isin(["train", "test"])],
            ENTRY_SAFE_FEATURES,
            "label_basket_won",
        ),
        "walk_forward_window": args.walk_forward_window,
        "train_months": train_m,
        "test_months": test_m,
    }

    report_path = args.output.parent / "feature_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"  input:  {args.input} ({len(baskets)} baskets)")
    print(f"  output: {args.output} ({len(featured)} rows)")
    print(f"  entry:  {entry_path}")
    print(f"  health: {health_path}")
    print(f"  folds:  {folds_path}")

    print(f"  report: {report_path}")

    print_report(featured, report, args.walk_forward_window, wf_expanded)

    w02 = report["labels_w02"]
    gate_wr = 0.55 <= w02.get("basket_won_rate", 0) <= 0.75
    gate_tail = 0.05 <= w02.get("tail_loss_rate", 0) <= 0.30
    gate_leak = len(report["leakage_entry"]["leak_warnings"]) == 0
    print("\n[AI-802] Gates (w02)")
    print(f"  basket_won rate 55-75%: {'PASS' if gate_wr else 'FAIL'} ({w02.get('basket_won_rate', 0):.1%})")
    print(f"  tail_loss rate 5-30%:   {'PASS' if gate_tail else 'FAIL'} ({w02.get('tail_loss_rate', 0):.1%})")
    print(f"  entry leakage:          {'PASS' if gate_leak else 'FAIL'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
