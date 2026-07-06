#!/usr/bin/env python3
"""AI-807: Offline exit-policy sweep on LOCK-AI (805p health replay baseline)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets
from basket_replay import load_window_legs
from exit_replay import ExitPolicyConfig, exit_policy_from_cfg, simulate_exit_replay
from simulate_policy import equity_metrics, health_805p_kwargs, resolve_export_window

POLICIES = ["baseline_805p", "partial_l0_1r", "dynamic_tp", "runner_lock", "combined"]


def run_policy(
    baskets: pd.DataFrame,
    legs: pd.DataFrame,
    cfg: dict,
    policy_name: str,
) -> pd.DataFrame:
    health_kw = health_805p_kwargs(cfg)
    if policy_name == "baseline_805p":
        return simulate_exit_replay(
            baskets,
            legs,
            exit_policy=ExitPolicyConfig(name="none"),
            **health_kw,
        )
    exit_cfg = exit_policy_from_cfg(cfg, policy_name)  # type: ignore[arg-type]
    return simulate_exit_replay(baskets, legs, exit_policy=exit_cfg, **health_kw)


def policy_summary(df: pd.DataFrame, deposit: float) -> dict:
    m = equity_metrics(df["sim_pnl"], deposit)
    exp = expectancy_block(df["sim_pnl"])
    exits = df["exit_intervention"].value_counts().to_dict() if "exit_intervention" in df else {}
    return {**m, **exp, "exit_events": exits}


def gate_check(baseline: dict, candidate: dict, gates: dict) -> dict:
    trade_floor = int(baseline["trades"] * gates["min_trades_pct"])
    net_floor = baseline["net"] * (1.0 + gates["net_vs_lock_ai_pct"])
    return {
        "trades": candidate["trades"] >= trade_floor,
        "net": candidate["net"] >= net_floor,
        "tail": candidate["worst"] >= gates["tail_loss_usd"],
        "avg_win_up": candidate["avg_win"] >= baseline["avg_win"] * (
            1.0 + gates["avg_win_improve_pct"]
        ),
        "avg_loss_up": candidate["avg_loss"] >= baseline["avg_loss"] * (
            1.0 + gates["avg_loss_improve_pct"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-807 exit policy offline sweep")
    parser.add_argument("--window", default="AI806_805p")
    parser.add_argument(
        "--baskets",
        type=Path,
        default=ROOT / "features" / "baskets_ai806.parquet",
    )
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument("--deposit", type=float, default=200.0)
    parser.add_argument(
        "--policy",
        default="all",
        choices=["all", *POLICIES],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "exit_policy_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    baskets = load_baskets(args.baskets, args.window, args.export_dir)
    if baskets.empty:
        print(f"No baskets for window {args.window!r}")
        return 1

    export_window = resolve_export_window(baskets, args.window)
    legs = load_window_legs(args.export_dir, export_window)
    keys = set(baskets["basket_key"].astype(str))
    legs = legs.loc[legs["basket_key"].isin(keys)].copy()

    to_run = POLICIES if args.policy == "all" else [args.policy]
    gates = cfg.get("expectancy_gates", {})
    results: dict = {"window": args.window, "policies": {}}

    print(f"[AI-807] Exit policy sweep — {args.window} ({len(baskets)} baskets)")
    print("-" * 88)
    print(
        f"{'Policy':<18} {'Net':>8} {'PF':>6} {'DD%':>6} {'AvgW':>7} {'AvgL':>7} "
        f"{'Worst':>8} {'Exit#':>6}"
    )
    print("-" * 88)

    baseline_summary: dict | None = None
    for name in to_run:
        sim_df = run_policy(baskets, legs, cfg, name)
        summary = policy_summary(sim_df, args.deposit)
        if name == "baseline_805p":
            baseline_summary = summary
        exit_n = sum(
            v for k, v in summary.get("exit_events", {}).items()
            if k not in ("none", "sl_cascade", "hard_cap", "hard_cap_l1", "flatten", "basket_cap")
        )
        results["policies"][name] = summary
        print(
            f"{name:<18} ${summary['net']:7.2f} {summary['pf']:6.2f} "
            f"{summary['max_dd_pct']:5.1f}% ${summary['avg_win']:6.2f} "
            f"${summary['avg_loss']:6.2f} ${summary['worst']:7.2f} {exit_n:6d}"
        )

    if baseline_summary:
        results["gates"] = {}
        for name, summary in results["policies"].items():
            if name == "baseline_805p":
                continue
            results["gates"][name] = gate_check(baseline_summary, summary, gates)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("-" * 88)
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
