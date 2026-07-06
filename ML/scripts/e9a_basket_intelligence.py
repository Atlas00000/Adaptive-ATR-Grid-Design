#!/usr/bin/env python3
"""E9a: Basket intelligence metrics — recovery, lifetime, capital efficiency."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets

SEGMENT_DEFS: dict[str, tuple[str, str | None]] = {
    "all": ("All baskets", None),
    "2024_h1": ("2024 H1 (Jan–Jun)", "2024_h1"),
    "2024_h1_apr_jul": ("2024 Apr–Jul (E7 bleed)", "2024_h1_apr_jul"),
    "rest": ("Outside 2024 H1", "rest"),
    "2022_h1": ("2022 H1", "2022_h1"),
    "d2_plus": ("Depth ≥ 2", "d2_plus"),
    "l0_only": ("L0 only (1 leg)", "l0_only"),
    "tail_loss": ("Tail loss baskets", "tail_loss"),
}


def segment_mask(df: pd.DataFrame, key: str) -> pd.Series:
    ot = df["open_time"]
    if key == "2024_h1":
        return (ot >= "2024-01-01") & (ot < "2024-07-01")
    if key == "2024_h1_apr_jul":
        return (ot >= "2024-04-01") & (ot < "2024-08-01")
    if key == "rest":
        return ~((ot >= "2024-01-01") & (ot < "2024-07-01"))
    if key == "2022_h1":
        return (ot >= "2022-01-01") & (ot < "2022-07-01")
    if key == "d2_plus":
        return df["max_level"] >= 2
    if key == "l0_only":
        return df["max_level"] <= 1
    if key == "tail_loss":
        return df["tail_loss"].astype(bool)
    return pd.Series(True, index=df.index)


def recovery_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    underwater = df["path_mae"] < -1.0
    n_uw = int(underwater.sum())
    if n_uw == 0:
        return {"baskets": len(df), "underwater_pct": 0.0, "recovery_rate_pct": 0.0}

    uw = df.loc[underwater].copy()
    recovered = uw["basket_won"].astype(bool)
    depth_ratio = (uw["path_mae"].abs() / uw["basket_pnl"].abs().clip(lower=0.01)).where(
        recovered, np.nan
    )
    d2_uw = uw[uw["max_level"] >= 2]
    return {
        "baskets": len(df),
        "underwater_pct": round(100.0 * n_uw / len(df), 1),
        "recovery_rate_pct": round(100.0 * recovered.mean(), 1),
        "d2_underwater_recovery_pct": round(
            100.0 * d2_uw["basket_won"].mean(), 1
        )
        if len(d2_uw)
        else None,
        "mean_depth_ratio_winners": round(float(depth_ratio.mean()), 2)
        if depth_ratio.notna().any()
        else None,
        "mean_path_mae_losers": round(float(uw.loc[~recovered, "path_mae"].mean()), 2)
        if (~recovered).any()
        else None,
    }


def lifetime_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    hrs = df["hold_sec"] / 3600.0
    return {
        "hold_hours_median": round(float(hrs.median()), 2),
        "hold_hours_p90": round(float(hrs.quantile(0.9)), 2),
        "hold_hours_mean": round(float(hrs.mean()), 2),
        "long_basket_pct": round(100.0 * float((df["hold_sec"] > 14400).mean()), 1),
        "long_basket_wr_pct": round(
            100.0 * float(df.loc[df["hold_sec"] > 14400, "basket_won"].mean()), 1
        )
        if (df["hold_sec"] > 14400).any()
        else None,
    }


def capital_efficiency_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    pnl = df["basket_pnl"].astype(float)
    levels = df["levels_filled"].clip(lower=1)
    hrs = (df["hold_sec"] / 3600.0).clip(lower=1.0 / 3600.0)
    exposure = df["path_mae"].abs().clip(lower=0.01)
    uw = df["path_mae"] < -1.0
    return {
        "pnl_per_level_mean": round(float((pnl / levels).mean()), 2),
        "pnl_per_hour_mean": round(float((pnl / hrs).mean()), 2),
        "exposure_efficiency_uw": round(float((pnl[uw] / exposure[uw]).mean()), 3)
        if uw.any()
        else None,
        "d2_pnl_per_level": round(float((pnl[df["max_level"] >= 2] / levels[df["max_level"] >= 2]).mean()), 2)
        if (df["max_level"] >= 2).any()
        else None,
    }


def depth_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    d2 = df["max_level"] >= 2
    l0 = df["max_level"] <= 1
    sl_legs = df["legs_sl"].astype(float)
    levels = df["levels_filled"].clip(lower=1)
    return {
        "d2_plus_pct": round(100.0 * float(d2.mean()), 1),
        "d2_wr_pct": round(100.0 * float(df.loc[d2, "basket_won"].mean()), 1) if d2.any() else None,
        "l0_wr_pct": round(100.0 * float(df.loc[l0, "basket_won"].mean()), 1) if l0.any() else None,
        "sl_leg_rate_pct": round(100.0 * float((sl_legs / levels).mean()), 1),
        "primary_exit_sl_pct": round(
            100.0 * float((df["primary_exit"] == "SL").mean()), 1
        ),
    }


def entry_context_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    return {
        "entry_adx_mean": round(float(df["entry_adx"].mean()), 1),
        "entry_atr_mean": round(float(df["entry_atr"].mean()), 6),
        "bad_hour_pct": round(100.0 * float(df["bad_hour"].astype(bool).mean()), 1),
        "session_ny_pct": round(100.0 * float((df["session"] == "NY").mean()), 1),
        "session_london_pct": round(100.0 * float((df["session"] == "London").mean()), 1),
    }


def intelligence_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"baskets": 0}
    return {
        "expectancy": expectancy_block(df["basket_pnl"]),
        "recovery": recovery_block(df),
        "lifetime": lifetime_block(df),
        "capital_efficiency": capital_efficiency_block(df),
        "depth": depth_block(df),
        "entry_context": entry_context_block(df),
    }


def delta_vs_rest(h1: dict, rest: dict) -> dict:
    """Highlight 2024 H1 degradation vs rest."""
    out: dict = {}
    if not h1.get("expectancy") or not rest.get("expectancy"):
        return out
    h, r = h1["expectancy"], rest["expectancy"]
    out["wr_delta_pts"] = round(h["win_rate_pct"] - r["win_rate_pct"], 1)
    out["pf_delta"] = round(h["profit_factor"] - r["profit_factor"], 3)
    out["avg_loss_delta"] = round(h["avg_loss"] - r["avg_loss"], 2)
    out["net_per_basket_delta"] = round(
        h["expectancy"] - r["expectancy"], 2
    )
    if h1.get("recovery") and rest.get("recovery"):
        out["recovery_rate_delta_pts"] = round(
            (h1["recovery"]["recovery_rate_pct"] or 0)
            - (rest["recovery"]["recovery_rate_pct"] or 0),
            1,
        )
    if h1.get("depth") and rest.get("depth"):
        out["d2_wr_delta_pts"] = round(
            (h1["depth"]["d2_wr_pct"] or 0) - (rest["depth"]["d2_wr_pct"] or 0),
            1,
        )
        out["sl_exit_delta_pts"] = round(
            (h1["depth"]["primary_exit_sl_pct"] or 0)
            - (rest["depth"]["primary_exit_sl_pct"] or 0),
            1,
        )
    return out


def monthly_pnl(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    tmp = df.copy()
    tmp["ym"] = tmp["open_time"].dt.to_period("M").astype(str)
    rows = []
    for ym, grp in tmp.groupby("ym", sort=True):
        exp = expectancy_block(grp["basket_pnl"])
        rows.append(
            {
                "month": ym,
                "baskets": exp["baskets"],
                "net": exp["net"],
                "pf": exp["profit_factor"],
                "wr_pct": exp["win_rate_pct"],
            }
        )
    return rows


def diagnose_window(segments: dict) -> dict:
    h1 = segments.get("2024_h1", {})
    rest = segments.get("rest", {})
    diag = {
        "2024_h1_vs_rest": delta_vs_rest(h1, rest),
    }
    d = diag["2024_h1_vs_rest"]
    modes: list[str] = []
    if d.get("wr_delta_pts", 0) < -8:
        modes.append("wr_collapse")
    if d.get("avg_loss_delta", 0) < -2:
        modes.append("larger_losses")
    if d.get("recovery_rate_delta_pts", 0) < -10:
        modes.append("poor_recovery")
    if d.get("d2_wr_delta_pts", 0) < -10:
        modes.append("deep_stack_fail")
    if d.get("sl_exit_delta_pts", 0) > 8:
        modes.append("sl_dominant_exits")
    diag["failure_modes"] = modes or ["mixed"]
    diag["primary_hypothesis"] = modes[0] if modes else "mixed"
    return diag


def analyze_window(
    window: str,
    policy: str,
    baskets_path: Path | None,
    export_dir: Path,
) -> dict:
    path = baskets_path or ROOT / "features" / f"baskets_{window.lower()}.parquet"
    if not path.is_file():
        csv = path.with_suffix(".csv")
        path = csv if csv.is_file() else path
    baskets = load_baskets(path, window, export_dir)
    if baskets.empty:
        return {"window": window, "policy": policy, "error": "no baskets"}

    baskets = baskets.sort_values("open_time").reset_index(drop=True)
    segments: dict = {}
    for seg_key, (_, mask_key) in SEGMENT_DEFS.items():
        if mask_key is None:
            sub = baskets
        else:
            sub = baskets.loc[segment_mask(baskets, mask_key)]
        segments[seg_key] = intelligence_block(sub)

    return {
        "window": window,
        "policy": policy,
        "date_range": {
            "start": str(baskets["open_time"].min()),
            "end": str(baskets["open_time"].max()),
        },
        "segments": segments,
        "monthly": monthly_pnl(baskets),
        "diagnosis": diagnose_window(segments),
    }


WINDOW_SPECS = (
    ("w03_longest", "lock202", "features/baskets_w03_longest.parquet"),
    ("AI806_805p", "lock_ai", "features/baskets_ai806.parquet"),
    ("w02_ext19mo", "lock202_wire", "features/baskets_w02_ext19mo.parquet"),
)


def print_summary(report: dict) -> None:
    print(f"\n[E9a] {report['policy']} — {report['window']}")
    print("-" * 72)
    for seg in ("all", "2024_h1", "rest"):
        s = report["segments"].get(seg, {})
        e = s.get("expectancy", {})
        if not e.get("baskets"):
            continue
        r = s.get("recovery", {})
        d = s.get("depth", {})
        print(
            f"  {seg:16s}  n={e['baskets']:3d}  net=${e['net']:7.1f}  "
            f"PF={e['profit_factor']:.2f}  WR={e['win_rate_pct']:.1f}%  "
            f"recv={r.get('recovery_rate_pct', 0):.0f}%  D2+WR={d.get('d2_wr_pct', 0):.0f}%"
        )
    diag = report.get("diagnosis", {})
    modes = diag.get("failure_modes", [])
    print(f"  diagnosis: {', '.join(modes)} (primary: {diag.get('primary_hypothesis')})")


def main() -> int:
    parser = argparse.ArgumentParser(description="E9a basket intelligence analysis")
    parser.add_argument(
        "--window",
        choices=[w[0] for w in WINDOW_SPECS] + ["all"],
        default="all",
    )
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e9a_report.json",
    )
    args = parser.parse_args()
    load_config()

    specs = WINDOW_SPECS if args.window == "all" else [s for s in WINDOW_SPECS if s[0] == args.window]
    if not specs:
        print(f"Unknown window {args.window!r}")
        return 1

    runs = []
    for window, policy, rel_path in specs:
        path = ROOT / rel_path
        run = analyze_window(window, policy, path, args.export_dir)
        runs.append(run)
        if "error" not in run:
            print_summary(run)

    out = {"e9a": "basket_intelligence", "runs": runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
