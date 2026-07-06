#!/usr/bin/env python3
"""AI-801: Aggregate leg-level diagnostics CSV into basket records."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config

TRADE_GLOB = "*_trades_*.csv"
WINDOW_RE = re.compile(r"^(w\d+_[^_]+(?:_[^_]+)*)_trades_", re.I)


def window_from_path(path: Path) -> str:
    m = WINDOW_RE.match(path.name)
    if m:
        return m.group(1)
    stem = path.stem.replace("_trades_EURUSD", "").replace("_trades", "")
    return stem or path.stem


def load_trade_files(input_dir: Path, pattern: str) -> list[Path]:
    files = sorted(input_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No trade CSV files matching {pattern!r} in {input_dir}")
    return files


def aggregate_file(path: Path) -> pd.DataFrame:
    window = window_from_path(path)
    df = pd.read_csv(path)
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["close_time"] = pd.to_datetime(df["close_time"])
    df["profit"] = df["profit"].astype(float)
    df["level"] = df["level"].astype(int)
    df["basket_id"] = df["basket_id"].astype(int)

    rows: list[dict] = []
    for bid, grp in df.groupby("basket_id", sort=True):
        grp = grp.sort_values(["close_time", "level", "ticket"])
        l0 = grp.loc[grp["level"] == 0]
        entry = l0.iloc[0] if not l0.empty else grp.iloc[0]

        close_last = grp["close_time"].max()
        open_first = entry["open_time"]
        hold_sec = int((close_last - open_first).total_seconds())

        cum = grp.sort_values("close_time")["profit"].cumsum()
        basket_pnl = float(grp["profit"].sum())

        exit_reasons = grp.sort_values("close_time")["exit_reason"].tolist()
        primary_exit = exit_reasons[-1] if exit_reasons else "UNKNOWN"

        rows.append(
            {
                "window": window,
                "basket_id": int(bid),
                "basket_key": f"{window}_{int(bid)}",
                "open_time": open_first,
                "close_time": close_last,
                "hold_sec": hold_sec,
                "bias": entry["direction"],
                "levels_filled": int(len(grp)),
                "max_level": int(grp["basket_max_levels"].max()),
                "basket_pnl": basket_pnl,
                "entry_adx": float(entry["adx"]),
                "entry_atr": float(entry["atr"]),
                "hour": int(entry["hour"]),
                "weekday": int(entry["weekday"]),
                "weekday_name": entry["weekday_name"],
                "month": int(entry["month"]),
                "year": int(entry["year"]),
                "session": entry["session"],
                "bad_hour": bool(int(entry["bad_hour"])),
                "path_mae": float(cum.min()),
                "path_mfe": float(cum.max()),
                "worst_leg": float(grp["profit"].min()),
                "best_leg": float(grp["profit"].max()),
                "legs_tp": int((grp["exit_reason"] == "TP").sum()),
                "legs_sl": int((grp["exit_reason"] == "SL").sum()),
                "primary_exit": primary_exit,
                "source_file": path.name,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["basket_won"] = out["basket_pnl"] > 0
    return out.sort_values(["open_time", "basket_key"]).reset_index(drop=True)


def apply_tail_loss_label(baskets: pd.DataFrame, tail_usd: float = 25.0) -> pd.DataFrame:
    wins = baskets.loc[baskets["basket_pnl"] > 0, "basket_pnl"]
    avg_win = float(wins.mean()) if len(wins) else 9.0
    threshold = max(-tail_usd, -2.0 * avg_win)
    baskets = baskets.copy()
    baskets["avg_win_ref"] = avg_win
    baskets["tail_threshold"] = threshold
    baskets["tail_loss"] = baskets["basket_pnl"] < threshold
    return baskets


def print_window_report(baskets: pd.DataFrame, cfg: dict) -> None:
    baseline_pf = cfg["baseline"]["production_pf_19mo"]
    baseline_trades = cfg["baseline"]["production_trades_19mo"]
    expected_net = baseline_pf  # placeholder — we compare leg-sum to summary

    print("\n[AI-801] Per-window summary")
    print("-" * 72)
    for window, grp in baskets.groupby("window", sort=True):
        leg_pnl = grp["basket_pnl"].sum()
        n = len(grp)
        wr = 100.0 * grp["basket_won"].mean() if n else 0.0
        tail_pct = 100.0 * grp["tail_loss"].mean() if n else 0.0
        d2 = grp[grp["max_level"] >= 2]
        d2_wr = 100.0 * d2["basket_won"].mean() if len(d2) else 0.0
        print(
            f"  {window:16s}  baskets={n:4d}  net=${leg_pnl:8.2f}  "
            f"WR={wr:5.1f}%  tail={tail_pct:4.1f}%  D2+ WR={d2_wr:5.1f}%"
        )

    w02 = baskets[baskets["window"].str.startswith("w02")]
    if len(w02):
        n = len(w02)
        net = w02["basket_pnl"].sum()
        w02_legs = int(w02["levels_filled"].sum())
        gate_baskets = n >= 230
        gate_pnl = abs(net - 623.30) <= max(12.47, abs(623.30) * 0.02)
        print("-" * 72)
        print(f"  w02 gate (>=230 baskets): {'PASS' if gate_baskets else 'FAIL'} ({n} baskets, {w02_legs} legs)")
        print(f"  w02 PnL reconcile ±2%:  {'PASS' if gate_pnl else 'FAIL'} "
              f"(baskets=${net:.2f} vs tester $623.30)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build basket dataset from diagnostics CSV")
    parser.add_argument("--input", type=Path, default=ROOT / "export")
    parser.add_argument("--output", type=Path, default=ROOT / "features" / "baskets.parquet")
    parser.add_argument("--glob", default=TRADE_GLOB)
    parser.add_argument("--csv", type=Path, default=None, help="Optional baskets CSV copy")
    args = parser.parse_args()

    cfg = load_config()
    print(f"[AI-801] build_baskets — baseline PF {cfg['baseline']['production_pf_19mo']}")

    files = load_trade_files(args.input, args.glob)
    print(f"  input:  {args.input} ({len(files)} file(s))")
    for f in files:
        print(f"    - {f.name}")

    parts = [aggregate_file(p) for p in files]
    baskets = pd.concat(parts, ignore_index=True)
    baskets = apply_tail_loss_label(baskets)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    baskets.to_parquet(args.output, index=False)

    csv_path = args.csv or args.output.with_suffix(".csv")
    baskets.to_csv(csv_path, index=False)

    print(f"  output: {args.output}")
    print(f"  csv:    {csv_path}")
    print(f"  total:  {len(baskets)} baskets | net=${baskets['basket_pnl'].sum():.2f} | "
          f"tail_loss={int(baskets['tail_loss'].sum())} ({100*baskets['tail_loss'].mean():.1f}%)")

    print_window_report(baskets, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
