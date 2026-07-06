#!/usr/bin/env python3
"""E9d: Build L0-SL physics labels for stack-risk / recovery gating."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import load_baskets
from basket_replay import leg_unrealized_at, load_window_legs
from e9c_context_geometry import enrich_baskets

PHYSICS_FEATURES = [
    "entry_adx",
    "entry_atr",
    "atr_pips",
    "l0_hold_hours",
    "l0_loss_usd",
    "l0_mae_usd",
    "l0_mfe_usd",
    "l0_mae_atr",
    "hour",
    "weekday",
    "bad_hour",
    "bias_sell",
    "session_london",
    "session_ny",
    "rolling_pf_20",
    "rolling_wr_20",
    "consec_losses",
]

WINDOWS = ("w03_longest", "w02_ext19mo", "AI806_805p")


def l0_path_extremes(l0: dict, checkpoints: int = 12) -> tuple[float, float]:
    """MAE/MFE on L0 leg via linear unrealized path (causal)."""
    open_t = l0["open_time"]
    close_t = l0["close_time"]
    duration = max((close_t - open_t).total_seconds(), 1.0)
    step = duration / checkpoints
    vals = []
    t = open_t
    while t <= close_t:
        vals.append(leg_unrealized_at(l0, t))
        t += pd.Timedelta(seconds=step)
    vals.append(float(l0["profit"]))
    return float(min(vals)), float(max(vals))


def build_l0_sl_rows(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    window: str,
) -> pd.DataFrame:
    enriched = enrich_baskets(baskets)
    meta = enriched.set_index(enriched["basket_key"].astype(str))
    rows: list[dict] = []

    for basket_key, grp in legs.groupby("basket_key", sort=False):
        bk = str(basket_key)
        if bk not in meta.index:
            continue
        brow = meta.loc[bk]
        grp = grp.sort_values(["level", "open_time"])
        l0_rows = grp.loc[grp["level"] == 0]
        if l0_rows.empty:
            continue
        l0 = l0_rows.iloc[0].to_dict()
        l0["open_time"] = pd.to_datetime(l0["open_time"])
        l0["close_time"] = pd.to_datetime(l0["close_time"])

        if str(l0.get("exit_reason", "")).upper() != "SL":
            continue

        deeper = grp.loc[grp["level"] >= 1]
        if deeper.empty:
            continue

        l0_pnl = float(l0["profit"])
        full_pnl = float(grp["profit"].sum())
        mae, mfe = l0_path_extremes(l0)
        atr = float(l0.get("atr") or brow["entry_atr"] or 0.0001)
        atr_pips = atr * 10000.0

        rows.append(
            {
                "window": window,
                "basket_key": bk,
                "open_time": brow["open_time"],
                "l0_loss_usd": l0_pnl,
                "l0_hold_hours": round(
                    (l0["close_time"] - l0["open_time"]).total_seconds() / 3600.0, 3
                ),
                "l0_mae_usd": mae,
                "l0_mfe_usd": mfe,
                "l0_mae_atr": round(abs(min(mae, 0.0)) / max(atr_pips * 0.1, 0.01), 3),
                "entry_adx": float(l0.get("adx") or brow["entry_adx"]),
                "entry_atr": atr,
                "atr_pips": round(atr_pips, 2),
                "hour": int(l0.get("hour", brow["hour"])),
                "weekday": int(l0.get("weekday", brow["weekday"])),
                "bad_hour": bool(int(l0.get("bad_hour", brow["bad_hour"]))),
                "bias_sell": int(str(l0.get("direction", brow["bias"])) == "SELL"),
                "session_london": int(str(l0.get("session", brow["session"])) == "London"),
                "session_ny": int(str(l0.get("session", brow["session"])) == "NY"),
                "rolling_pf_20": float(brow.get("rolling_pf_20", np.nan))
                if pd.notna(brow.get("rolling_pf_20"))
                else np.nan,
                "rolling_wr_20": float(brow.get("rolling_wr_20", np.nan))
                if pd.notna(brow.get("rolling_wr_20"))
                else np.nan,
                "consec_losses": int(brow.get("consec_losses", 0)),
                "full_basket_pnl": full_pnl,
                "l0_only_pnl": l0_pnl,
                "recovery_delta": round(l0_pnl - full_pnl, 2),
                "label_block_beneficial": int(l0_pnl > full_pnl),
                "label_stack_fail": int(full_pnl < -5.0),
            }
        )

    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="E9d L0-SL physics label builder")
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "physics_l0_sl.parquet",
    )
    args = parser.parse_args()
    load_config()

    parts = []
    for window in WINDOWS:
        path = ROOT / "features" / f"baskets_{window}.parquet"
        if window == "AI806_805p":
            path = ROOT / "features" / "baskets_ai806.parquet"
        if not path.is_file():
            path = path.with_suffix(".csv")
        baskets = load_baskets(path, window, args.export_dir)
        legs = load_window_legs(args.export_dir, window)
        part = build_l0_sl_rows(legs, baskets, window)
        parts.append(part)
        print(f"  {window}: {len(part)} L0-SL+D1+ rows")

    out = pd.concat(parts, ignore_index=True).sort_values("open_time")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.output, index=False)
    out.to_csv(args.output.with_suffix(".csv"), index=False)

    n = len(out)
    pos = int(out["label_block_beneficial"].sum())
    print(f"[E9d] physics labels — {n} rows, block_beneficial={pos} ({100*pos/n:.1f}%)")
    h1 = out[(out["open_time"] >= "2024-01-01") & (out["open_time"] < "2024-07-01")]
    if len(h1):
        print(
            f"  2024 H1: n={len(h1)} block_rate={100*h1['label_block_beneficial'].mean():.1f}% "
            f"avg_recovery_delta=${h1['recovery_delta'].mean():.2f}"
        )
    print(f"  output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
