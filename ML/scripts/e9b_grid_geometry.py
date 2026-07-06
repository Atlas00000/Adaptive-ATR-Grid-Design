#!/usr/bin/env python3
"""E9b: Offline grid geometry policy sweep on causal basket replay."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets
from basket_replay import load_window_legs, replay_basket
from simulate_policy import equity_metrics

POLICIES: dict[str, dict[str, Any]] = {
    "baseline": {},
    "cap_l0_only": {"max_grid_levels": 1},
    "cap_l2": {"max_grid_levels": 2},
    "no_add_after_l0_sl": {"no_add_after_l0_sl": True},
    "spacing_125": {"spacing_mult": 1.25, "spacing_min_gap_sec": 180},
    "spacing_150": {"spacing_mult": 1.50, "spacing_min_gap_sec": 180},
    "no_l0_sl_cap_l2": {"no_add_after_l0_sl": True, "max_grid_levels": 2},
    "stress_flat_15": {
        "flatten_float": -15.0,
        "stress_flatten_at": 50.0,
    },
}

WINDOW_FILES = {
    "w03_longest": ROOT / "features" / "baskets_w03_longest.parquet",
    "AI806_805p": ROOT / "features" / "baskets_ai806.parquet",
    "w02_ext19mo": ROOT / "features" / "baskets_w02_ext19mo.parquet",
}


def replay_kwargs(policy: dict, cfg: dict) -> dict:
    """Geometry replay without health overlays unless policy requests them."""
    base = {
        "sl_cascade_enabled": False,
        "hard_cap_enabled": False,
        "basket_cap_enabled": False,
    }
    base.update(policy)
    return base


def simulate_geometry(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    policy: dict,
    cfg: dict,
    deposit: float = 200.0,
) -> pd.DataFrame:
    kw = replay_kwargs(policy, cfg)
    rows = []
    for _, brow in baskets.iterrows():
        bk = str(brow["basket_key"])
        grp = legs.loc[legs["basket_key"] == bk]
        if grp.empty:
            continue
        result = replay_basket(grp, **kw)
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "max_level": int(brow["max_level"]),
                "intervention": result.intervention,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def segment_mask(df: pd.DataFrame, key: str) -> pd.Series:
    ot = df["open_time"]
    if key == "all":
        return pd.Series(True, index=df.index)
    if key == "2024_h1":
        return (ot >= "2024-01-01") & (ot < "2024-07-01")
    if key == "d2_plus":
        return df["max_level"] >= 2
    if key == "rest":
        return ~((ot >= "2024-01-01") & (ot < "2024-07-01"))
    raise ValueError(key)


def policy_metrics(sim: pd.DataFrame, baseline: pd.DataFrame, deposit: float) -> dict:
    pnls = sim["sim_pnl"]
    base_pnls = baseline["baseline_pnl"]
    eq = equity_metrics(pnls, deposit)
    base_eq = equity_metrics(base_pnls, deposit)
    exp = expectancy_block(pnls)
    d2 = sim.loc[sim["max_level"] >= 2]
    d2_exp = expectancy_block(d2["sim_pnl"]) if len(d2) else {"baskets": 0}
    blocked = int((sim["intervention"] != "none").sum())
    return {
        "expectancy": exp,
        "equity": eq,
        "baseline_net": round(float(base_pnls.sum()), 2),
        "net_delta": round(float(pnls.sum() - base_pnls.sum()), 2),
        "d2_plus": d2_exp,
        "interventions": blocked,
        "intervention_pct": round(100.0 * blocked / len(sim), 1) if len(sim) else 0.0,
        "trades_pct_vs_baseline": round(len(sim) / len(baseline), 4) if len(baseline) else 1.0,
        "baseline_pf": base_eq["pf"],
        "baseline_worst": round(float(base_pnls.min()), 2) if len(base_pnls) else 0.0,
    }


def evaluate_gates(metrics: dict, baseline: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    exp = metrics["expectancy"]
    if exp["baskets"] < baseline["expectancy"]["baskets"] * gates["min_trades_pct"]:
        reasons.append("trades_below_floor")
    if metrics["net_delta"] < baseline["expectancy"]["net"] * gates["net_vs_baseline_pct"]:
        reasons.append("net_vs_baseline")
    if exp["worst"] < gates["tail_loss_usd"]:
        reasons.append("tail_fail")
    d2 = metrics["d2_plus"]
    if d2.get("baskets", 0) >= 20 and d2.get("profit_factor", 0) < gates["d2_pf_floor"]:
        reasons.append("d2_pf_floor")
    return len(reasons) == 0, reasons


def run_window(window: str, export_dir: Path, cfg: dict, policies: list[str]) -> dict:
    baskets_path = WINDOW_FILES.get(window, ROOT / "features" / f"baskets_{window}.parquet")
    baskets = load_baskets(baskets_path, window, export_dir)
    legs = load_window_legs(export_dir, window)
    deposit = 200.0

    baseline_sim = simulate_geometry(legs, baskets, {}, cfg, deposit)
    baseline_metrics = {
        "all": policy_metrics(baseline_sim, baseline_sim, deposit),
    }
    for seg in ("2024_h1", "d2_plus", "rest"):
        sub = baseline_sim.loc[segment_mask(baseline_sim, seg)]
        if len(sub):
            baseline_metrics[seg] = policy_metrics(sub, sub, deposit)

    results = []
    for name in policies:
        if name not in POLICIES:
            continue
        sim = simulate_geometry(legs, baskets, POLICIES[name], cfg, deposit)
        entry = {
            "policy": name,
            "params": POLICIES[name],
            "segments": {},
        }
        for seg in ("all", "2024_h1", "d2_plus", "rest"):
            sub = sim.loc[segment_mask(sim, seg)]
            base_sub = baseline_sim.loc[segment_mask(baseline_sim, seg)]
            if len(sub):
                m = policy_metrics(sub, base_sub, deposit)
                gates = cfg.get("e9b_gates", {})
                passed, fail = evaluate_gates(
                    m,
                    {"expectancy": baseline_metrics.get(seg, baseline_metrics["all"])["expectancy"]},
                    gates,
                )
                m["gate_pass"] = passed
                m["gate_fail"] = fail
                entry["segments"][seg] = m
        results.append(entry)

    best = max(
        results,
        key=lambda r: r["segments"].get("all", {}).get("net_delta", -1e9),
    )
    return {
        "window": window,
        "policy_count": len(results),
        "baseline": baseline_metrics,
        "policies": results,
        "best_policy": best["policy"],
        "best_net_delta": best["segments"].get("all", {}).get("net_delta"),
    }


def print_summary(report: dict) -> None:
    print(f"\n[E9b] {report['window']} — best: {report['best_policy']} "
          f"(dnet ${report['best_net_delta']:+.1f})")
    print("-" * 72)
    base = report["baseline"]["all"]["expectancy"]
    print(f"  baseline  net=${base['net']:8.1f}  PF={base['profit_factor']:.2f}  "
          f"worst=${base['worst']:.1f}")
    for pol in report["policies"]:
        seg = pol["segments"].get("all", {})
        exp = seg.get("expectancy", {})
        if not exp.get("baskets"):
            continue
        gate = "PASS" if seg.get("gate_pass") else "FAIL"
        print(
            f"  {pol['policy']:22s}  net=${exp['net']:8.1f}  "
            f"dnet=${seg.get('net_delta', 0):+6.1f}  PF={exp['profit_factor']:.2f}  "
            f"worst=${exp['worst']:.1f}  D2+PF={seg.get('d2_plus', {}).get('profit_factor', 0):.2f}  "
            f"{gate}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="E9b grid geometry offline sweep")
    parser.add_argument("--window", default="all", choices=list(WINDOW_FILES) + ["all"])
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--policy",
        default="all",
        help="Policy name or 'all'",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e9b_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    if args.policy != "all":
        policies = [args.policy]
    else:
        policies = list(POLICIES.keys())

    windows = list(WINDOW_FILES) if args.window == "all" else [args.window]
    runs = [run_window(w, args.export_dir, cfg, policies) for w in windows]
    for r in runs:
        print_summary(r)

    out = {"e9b": "grid_geometry", "runs": runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
