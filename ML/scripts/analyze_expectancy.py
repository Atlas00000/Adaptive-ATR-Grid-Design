#!/usr/bin/env python3
"""AI-807: Baseline expectancy / MFE capture analysis on basket history."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from build_baskets import apply_tail_loss_label, load_trade_files, aggregate_file, TRADE_GLOB


def expectancy_block(pnls: pd.Series) -> dict:
    pnls = pnls.astype(float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    n = len(pnls)
    wr = float(len(wins)) / n if n else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = wr * avg_win + (1.0 - wr) * avg_loss
    gross_win = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win > 0 else 1.0)
    return {
        "baskets": n,
        "win_rate_pct": round(100.0 * wr, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "profit_factor": round(pf, 3),
        "net": round(float(pnls.sum()), 2),
        "worst": round(float(pnls.min()), 2) if n else 0.0,
        "best": round(float(pnls.max()), 2) if n else 0.0,
    }


def replay_peak_floating(legs: pd.DataFrame, checkpoint_sec: int = 60) -> float:
    """Peak basket floating from linear leg paths (causal checkpoint scan)."""
    from datetime import timedelta

    from basket_replay import basket_floating_at

    legs = legs.sort_values(["level", "open_time"]).reset_index(drop=True)
    leg_rows = [row.to_dict() for _, row in legs.iterrows()]
    basket_start = min(r["open_time"] for r in leg_rows)
    basket_end = max(r["close_time"] for r in leg_rows)

    events: list[tuple] = []
    for leg in leg_rows:
        events.append((leg["open_time"], "open", leg))
        events.append((leg["close_time"], "close", leg))
    t = basket_start
    while t <= basket_end:
        events.append((t, "checkpoint", None))
        t += timedelta(seconds=checkpoint_sec)
    events.sort(key=lambda x: (x[0], {"open": 0, "checkpoint": 1, "close": 2}[x[1]]))

    open_legs: list[dict] = []
    realized = 0.0
    peak = 0.0

    for evt_time, kind, leg in events:
        if kind == "open":
            open_legs.append(dict(leg))
        elif kind == "close":
            open_idx = next(
                (i for i, o in enumerate(open_legs) if int(o["ticket"]) == int(leg["ticket"])),
                None,
            )
            if open_idx is None:
                continue
            closed = open_legs.pop(open_idx)
            realized += float(closed["profit"])

        fl = basket_floating_at(open_legs, realized, evt_time) if open_legs else realized
        peak = max(peak, fl)

    return peak


def mfe_block(baskets: pd.DataFrame, legs: pd.DataFrame | None = None) -> dict:
    df = baskets.copy()
    winners = df[df["basket_pnl"] > 0].copy()
    if winners.empty:
        return {"winners": 0}

    if legs is not None:
        peaks: dict[str, float] = {}
        for basket_key, grp in legs.groupby("basket_key", sort=False):
            peaks[str(basket_key)] = replay_peak_floating(grp)
        winners["peak_float"] = winners["basket_key"].astype(str).map(peaks)
        valid = winners["peak_float"] >= winners["basket_pnl"] * 0.5
        w = winners.loc[valid].copy()
        if w.empty:
            w = winners
        w["mfe_capture"] = (w["basket_pnl"] / w["peak_float"]).clip(upper=1.0)
        w["giveback_usd"] = w["peak_float"] - w["basket_pnl"]
        winners = w
        source = "replay_peak_float"
    else:
        winners["mfe_capture"] = winners["basket_pnl"] / winners["path_mfe"].clip(lower=0.01)
        winners["giveback_usd"] = winners["path_mfe"] - winners["basket_pnl"]
        source = "leg_close_cumsum"
    losers = df[df["basket_pnl"] <= 0]
    return {
        "source": source,
        "winners": int(len(winners)),
        "mfe_capture_mean": round(float(winners["mfe_capture"].mean()), 3),
        "mfe_capture_median": round(float(winners["mfe_capture"].median()), 3),
        "giveback_mean_usd": round(float(winners["giveback_usd"].mean()), 2),
        "giveback_median_usd": round(float(winners["giveback_usd"].median()), 2),
        "path_mfe_mean_winners": round(float(winners["path_mfe"].mean()), 2),
        "path_mae_mean_losers": round(float(losers["path_mae"].mean()), 2) if len(losers) else 0.0,
        "pct_winners_giveback_gt_5": round(
            100.0 * float((winners["giveback_usd"] > 5.0).mean()), 1
        ),
    }


def segment_report(baskets: pd.DataFrame) -> dict:
    out: dict = {}
    for label, mask in [
        ("all", baskets.index == baskets.index),
        ("L0_only", baskets["max_level"] <= 1),
        ("D2_plus", baskets["max_level"] >= 2),
        ("winners", baskets["basket_pnl"] > 0),
        ("losers", baskets["basket_pnl"] <= 0),
        ("tail_loss", baskets["tail_loss"]),
    ]:
        sub = baskets.loc[mask]
        if len(sub):
            out[label] = expectancy_block(sub["basket_pnl"])
    return out


def load_baskets(baskets_path: Path, window: str, export_dir: Path) -> pd.DataFrame:
    if baskets_path.is_file():
        df = pd.read_parquet(baskets_path)
    else:
        pattern = f"{window}_trades_*.csv"
        files = load_trade_files(export_dir, pattern)
        parts = [aggregate_file(p) for p in files]
        df = pd.concat(parts, ignore_index=True)
        df = apply_tail_loss_label(df)
    if window:
        df = df.loc[df["window"] == window].copy()
    return df.sort_values("open_time").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-807 baseline expectancy analysis")
    parser.add_argument("--window", default="AI806_805p")
    parser.add_argument(
        "--baskets",
        type=Path,
        default=ROOT / "features" / "baskets_ai806.parquet",
    )
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument("--replay-mfe", action="store_true", help="Peak floating from leg replay")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "expectancy_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    baskets = load_baskets(args.baskets, args.window, args.export_dir)
    if baskets.empty:
        print(f"No baskets for window {args.window!r}")
        return 1

    legs = None
    if args.replay_mfe:
        from basket_replay import load_window_legs

        legs = load_window_legs(args.export_dir, args.window)
        keys = set(baskets["basket_key"].astype(str))
        legs = legs.loc[legs["basket_key"].isin(keys)].copy()

    report = {
        "window": args.window,
        "overall": expectancy_block(baskets["basket_pnl"]),
        "mfe": mfe_block(baskets, legs),
        "segments": segment_report(baskets),
        "tail": {
            "count": int(baskets["tail_loss"].sum()),
            "pct": round(100.0 * baskets["tail_loss"].mean(), 1),
            "threshold_usd": round(float(baskets["tail_threshold"].iloc[0]), 2),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    o = report["overall"]
    m = report["mfe"]
    print(f"[AI-807] Expectancy baseline — {args.window}")
    print("-" * 72)
    print(
        f"  baskets={o['baskets']}  net=${o['net']:.2f}  PF={o['profit_factor']:.2f}  "
        f"WR={o['win_rate_pct']:.1f}%"
    )
    print(
        f"  avg_win=${o['avg_win']:.2f}  avg_loss=${o['avg_loss']:.2f}  "
        f"expectancy=${o['expectancy']:.2f}/basket"
    )
    print(
        f"  worst=${o['worst']:.2f}  tail={report['tail']['count']} "
        f"({report['tail']['pct']:.1f}%)"
    )
    if m.get("winners"):
        print(
            f"  MFE capture={m['mfe_capture_mean']:.0%} (median {m['mfe_capture_median']:.0%})  "
            f"giveback=${m['giveback_mean_usd']:.2f} avg"
        )
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
