#!/usr/bin/env python3
"""E7 / EDGE-702+703: Walk-forward and Monte Carlo validation on basket history."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import load_baskets
from build_features import assign_walk_forward
from simulate_policy import (
    equity_metrics,
    health_805p_kwargs,
    simulate_memory,
    simulate_memory_805p,
)
from e9c_context_geometry import build_gates, enrich_baskets, simulate_gated
from basket_replay import load_window_legs, replay_basket
from e9d_simulate import make_model_gate, meta_lookup_for_windows, simulate_physics

POLICIES = (
    "lock202",
    "lock_ai",
    "lock202_adx_lt_18",
    "lock202_physics_p45",
    "lock_ai_physics_p45",
)
E9C_GEOMETRY = {"no_add_after_l0_sl": True}


def policy_pnls(
    baskets: pd.DataFrame,
    policy: str,
    cfg: dict,
    export_dir: Path,
    window: str,
) -> pd.DataFrame:
    """Return baskets frame with pnl column for E7 analysis."""
    df = baskets.sort_values("open_time").copy()
    if policy == "lock202":
        df["pnl"] = df["basket_pnl"].astype(float)
        df["policy"] = "lock202"
        return df

    if policy == "lock_ai":
        lot_min = float(cfg["thresholds"]["lot_mult_min"])
        sim_df, _ = simulate_memory_805p(
            df,
            cfg,
            export_dir=export_dir,
            window_arg=window,
            lot_min=lot_min,
        )
        sim_df["pnl"] = sim_df["sim_pnl"].astype(float)
        sim_df["policy"] = "lock_ai"
        return sim_df

    if policy == "lock202_adx_lt_18":
        gate_fn = build_gates()["adx_lt_18"]
        enriched = enrich_baskets(df)
        legs = load_window_legs(export_dir, window)
        sim = simulate_gated(legs, enriched, gate_fn, E9C_GEOMETRY, cfg)
        pnl_map = dict(zip(sim["basket_key"].astype(str), sim["sim_pnl"]))
        out = enriched.copy()
        out["pnl"] = out["basket_key"].astype(str).map(pnl_map).astype(float)
        out["policy"] = policy
        out["geometry_gated"] = out["basket_key"].astype(str).isin(
            sim.loc[sim["gated"], "basket_key"].astype(str)
        )
        return out

    if policy == "lock202_physics_p45":
        import joblib

        model_path = ROOT / "models" / "stack_risk_v0.joblib"
        if not model_path.is_file():
            raise FileNotFoundError(f"Train E9d first: {model_path}")
        model = joblib.load(model_path)
        meta = meta_lookup_for_windows(export_dir, window)
        gate_fn = make_model_gate(model, 0.45, meta)
        enriched = enrich_baskets(df)
        legs = load_window_legs(export_dir, window)
        sim = simulate_physics(legs, enriched, gate_fn, cfg)
        pnl_map = dict(zip(sim["basket_key"].astype(str), sim["sim_pnl"]))
        out = enriched.copy()
        out["pnl"] = out["basket_key"].astype(str).map(pnl_map).astype(float)
        out["policy"] = policy
        out["geometry_gated"] = out["basket_key"].astype(str).isin(
            sim.loc[sim["gated"], "basket_key"].astype(str)
        )
        return out

    if policy == "lock_ai_physics_p45":
        import joblib

        model_path = ROOT / "models" / "stack_risk_v0.joblib"
        if not model_path.is_file():
            raise FileNotFoundError(f"Train E9d first: {model_path}")
        model = joblib.load(model_path)
        meta = meta_lookup_for_windows(export_dir, window)
        gate_fn = make_model_gate(model, 0.45, meta)
        enriched = enrich_baskets(df)
        legs = load_window_legs(export_dir, window)
        kw = health_805p_kwargs(cfg)
        rows: list[dict] = []
        for _, brow in enriched.iterrows():
            bk = str(brow["basket_key"])
            grp = legs.loc[legs["basket_key"] == bk].copy()
            if grp.empty:
                continue
            leg_dicts = []
            for _, r in grp.sort_values(["level", "open_time"]).iterrows():
                d = r.to_dict()
                d["basket_key"] = bk
                d["open_time"] = pd.to_datetime(d["open_time"])
                d["close_time"] = pd.to_datetime(d["close_time"])
                leg_dicts.append(d)
            result = replay_basket(pd.DataFrame(leg_dicts), l0_sl_gate_fn=gate_fn, **kw)
            rows.append(
                {
                    "basket_key": bk,
                    "open_time": brow["open_time"],
                    "sim_pnl": float(result.sim_pnl),
                    "basket_pnl": float(brow["basket_pnl"]),
                }
            )
        sim_df = pd.DataFrame(rows).sort_values("open_time")
        lot_min = float(cfg["thresholds"]["lot_mult_min"])
        mem_in = sim_df.copy()
        mem_in["basket_pnl"] = mem_in["sim_pnl"].astype(float)
        out = simulate_memory(mem_in, lot_min)
        out["pnl"] = out["sim_pnl"].astype(float)
        out["policy"] = policy
        return out

    raise ValueError(f"Unknown policy {policy!r}")


def fold_metrics(pnls: pd.Series, deposit: float) -> dict:
    m = equity_metrics(pnls, deposit)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    return {
        **m,
        "worst": float(pnls.min()) if len(pnls) else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "wr_pct": round(100.0 * float((pnls > 0).mean()), 2) if len(pnls) else 0.0,
    }


def evaluate_fold_pass(metrics: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics["trades"] < gates["wf_test_min_trades"]:
        reasons.append(f"trades<{gates['wf_test_min_trades']}")
    if metrics["net"] < gates["wf_test_net_min"]:
        reasons.append(f"net<{gates['wf_test_net_min']}")
    if metrics["pf"] < gates["wf_test_pf_floor"]:
        reasons.append(f"pf<{gates['wf_test_pf_floor']}")
    return len(reasons) == 0, reasons


def walk_forward_report(
    df: pd.DataFrame,
    *,
    train_months: int,
    test_months: int,
    deposit: float,
    gates: dict,
) -> dict:
    wf = assign_walk_forward(df, train_months, test_months)
    if wf.empty or wf["wf_fold"].max() < 0:
        return {"folds": [], "n_folds": 0, "pass_rate": 0.0, "gate_pass": False}

    folds: list[dict] = []
    n_pass = 0
    for fold_id in sorted(wf["wf_fold"].unique()):
        if fold_id < 0:
            continue
        chunk = wf.loc[wf["wf_fold"] == fold_id]
        test = chunk.loc[chunk["wf_split"] == "test"].sort_values("open_time")
        train = chunk.loc[chunk["wf_split"] == "train"].sort_values("open_time")
        if test.empty:
            continue

        test_m = fold_metrics(test["pnl"], deposit)
        train_m = fold_metrics(train["pnl"], deposit) if len(train) else None
        passed, fail_reasons = evaluate_fold_pass(test_m, gates)

        test_periods = sorted(test["open_time"].dt.to_period("M").astype(str).unique())
        folds.append(
            {
                "fold": int(fold_id),
                "test_months": test_periods,
                "train_baskets": int(len(train)),
                "test_baskets": int(len(test)),
                "train": train_m,
                "test": test_m,
                "pass": passed,
                "fail_reasons": fail_reasons,
            }
        )
        if passed:
            n_pass += 1

    n_folds = len(folds)
    pass_rate = n_pass / n_folds if n_folds else 0.0
    min_pass = gates["wf_min_fold_pass_rate"]
    return {
        "folds": folds,
        "n_folds": n_folds,
        "n_pass": n_pass,
        "pass_rate": round(pass_rate, 4),
        "gate_pass": pass_rate >= min_pass,
        "min_pass_rate": min_pass,
    }


def monte_carlo_dd(
    pnls: np.ndarray,
    *,
    deposit: float,
    iterations: int,
    seed: int,
) -> dict:
    """Shuffle basket order; return max-DD distribution (EDGE-703)."""
    if len(pnls) == 0:
        return {"iterations": 0}

    rng = np.random.default_rng(seed)

    def max_dd_for(seq: np.ndarray) -> float:
        equity = deposit
        peak = deposit
        max_dd = 0.0
        for p in seq:
            equity += p
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        return max_dd

    actual_dd = max_dd_for(pnls)
    sim_dds: list[float] = []
    for _ in range(iterations):
        shuffled = rng.permutation(pnls)
        sim_dds.append(max_dd_for(shuffled))

    arr = np.array(sim_dds)
    return {
        "iterations": iterations,
        "actual_max_dd_pct": round(actual_dd, 2),
        "mc_dd_p50": round(float(np.percentile(arr, 50)), 2),
        "mc_dd_p95": round(float(np.percentile(arr, 95)), 2),
        "mc_dd_p99": round(float(np.percentile(arr, 99)), 2),
        "mc_dd_mean": round(float(arr.mean()), 2),
        "actual_worse_than_p95": actual_dd > float(np.percentile(arr, 95)),
    }


def full_window_gates(metrics: dict, worst: float, gates: dict, policy: str) -> dict:
    out: dict = {}
    lock202_like = policy in ("lock202", "lock202_adx_lt_18", "lock202_physics_p45")
    if lock202_like:
        out["wire_pf"] = metrics["pf"] >= gates["lock202_wire_pf_floor"]
        out["wire_dd"] = metrics["max_dd_pct"] <= gates["lock202_wire_dd_max_pct"]
        out["longest_pf"] = metrics["pf"] >= gates["longest_pf_floor"]
    else:
        out["wire_pf"] = metrics["pf"] >= gates["lock_ai_wire_pf_floor"]
        out["tail"] = worst >= gates["tail_loss_usd"]
        out["longest_pf"] = metrics["pf"] >= gates["lock_ai_longest_pf_floor"]
    out["net_positive"] = metrics["net"] > 0
    out["all_pass"] = all(out.values())
    return out


def run_validation(
    *,
    policy: str,
    window: str,
    baskets_path: Path | None,
    export_dir: Path,
    cfg: dict,
    deposit: float,
) -> dict:
    gates = cfg["e7_gates"]
    baskets = load_baskets(
        baskets_path or ROOT / "features" / f"baskets_{window}.parquet",
        window,
        export_dir,
    )
    if baskets.empty:
        raise ValueError(f"No baskets for window {window!r}")

    df = policy_pnls(baskets, policy, cfg, export_dir, window)
    pnls = df["pnl"].astype(float).values
    full_m = fold_metrics(df["pnl"], deposit)
    worst = float(df["pnl"].min())

    wf = walk_forward_report(
        df,
        train_months=int(cfg["walk_forward"]["train_months"]),
        test_months=int(cfg["walk_forward"]["test_months"]),
        deposit=deposit,
        gates=gates,
    )
    mc = monte_carlo_dd(
        pnls,
        deposit=deposit,
        iterations=int(gates["mc_iterations"]),
        seed=int(gates["mc_seed"]),
    )
    fw_gates = full_window_gates(full_m, worst, gates, policy)

    verdict = wf["gate_pass"] and fw_gates.get("net_positive", False)
    if policy in ("lock202", "lock202_adx_lt_18", "lock202_physics_p45"):
        verdict = verdict and fw_gates.get("wire_dd", False)
    if policy == "lock_ai" and "tail" in fw_gates:
        verdict = verdict and fw_gates["tail"]

    gated_pct = None
    if "geometry_gated" in df.columns:
        gated_pct = round(100.0 * float(df["geometry_gated"].mean()), 1)

    return {
        "policy": policy,
        "window": window,
        "deposit": deposit,
        "geometry_gate": (
            "adx_lt_18"
            if policy == "lock202_adx_lt_18"
            else "physics_lr_p45"
            if policy == "lock202_physics_p45"
            else None
        ),
        "geometry_gated_pct": gated_pct,
        "date_range": {
            "start": str(df["open_time"].min()),
            "end": str(df["open_time"].max()),
        },
        "full_window": full_m,
        "worst_basket": worst,
        "walk_forward": wf,
        "monte_carlo": mc,
        "gates": fw_gates,
        "verdict": "PASS" if verdict else "FAIL",
    }


def print_report(result: dict) -> None:
    pol = result["policy"]
    win = result["window"]
    f = result["full_window"]
    wf = result["walk_forward"]
    mc = result["monte_carlo"]

    print(f"\n[E7] {pol} — {win}")
    print("-" * 72)
    print(
        f"  full: net=${f['net']:.2f} PF={f['pf']:.2f} "
        f"DD={f['max_dd_pct']:.1f}% trades={f['trades']} worst=${result['worst_basket']:.2f}"
    )
    if result.get("geometry_gated_pct") is not None:
        print(f"        geometry gated: {result['geometry_gated_pct']:.1f}% of baskets")
    print(
        f"  WF:   {wf['n_pass']}/{wf['n_folds']} folds pass "
        f"({100*wf['pass_rate']:.0f}%) — {'PASS' if wf['gate_pass'] else 'FAIL'}"
    )
    for fold in wf.get("folds", []):
        t = fold["test"]
        mark = "PASS" if fold["pass"] else "FAIL"
        months = ",".join(fold["test_months"])
        print(
            f"    fold {fold['fold']:2d} [{months}] "
            f"net=${t['net']:7.2f} PF={t['pf']:.2f} n={t['trades']:3d} — {mark}"
        )
    print(
        f"  MC:   actual DD={mc['actual_max_dd_pct']:.1f}% "
        f"p95={mc['mc_dd_p95']:.1f}% "
        f"worse_than_p95={mc['actual_worse_than_p95']}"
    )
    print(f"  gates: {result['gates']}")
    print(f"  verdict: **{result['verdict']}**")


def main() -> int:
    parser = argparse.ArgumentParser(description="E7 walk-forward + Monte Carlo validation")
    parser.add_argument(
        "--policy",
        choices=["all", *POLICIES],
        default="all",
        help="lock202 | lock_ai | lock202_adx_lt_18 (E9c) | all",
    )
    parser.add_argument(
        "--window-lock202",
        default="w03_longest",
        help="Diagnostics window for LOCK-202 (w02_ext19mo | w03_longest)",
    )
    parser.add_argument(
        "--windows",
        default=None,
        help="Comma-separated windows (overrides per-policy defaults)",
    )
    parser.add_argument(
        "--window-lock-ai",
        default="AI806_805p",
        help="Diagnostics window for LOCK-AI replay",
    )
    parser.add_argument("--deposit", type=float, default=200.0)
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e7_report.json",
        help="Output JSON (e7_prime_report.json when --policy lock202_adx_lt_18 only)",
    )
    args = parser.parse_args()

    cfg = load_config()
    policies = list(POLICIES) if args.policy == "all" else [args.policy]

    if args.policy in ("lock202_adx_lt_18", "lock202_physics_p45") and args.output == ROOT / "features" / "e7_report.json":
        args.output = ROOT / "features" / "e7_prime_report.json"

    report: dict = {
        "e7": "EDGE-702/703",
        "e7_prime": args.policy in ("lock202_adx_lt_18", "lock202_physics_p45", "all"),
        "deposit": args.deposit,
        "runs": [],
    }

    print("[E7] Walk-forward + Monte Carlo validation")
    for pol in policies:
        if args.windows:
            windows = [w.strip() for w in args.windows.split(",")]
        elif pol in ("lock202", "lock202_adx_lt_18", "lock202_physics_p45"):
            windows = list(dict.fromkeys([args.window_lock202, "w02_ext19mo"]))
        else:
            windows = [args.window_lock_ai]

        for window in windows:
            baskets_path = ROOT / "features" / f"baskets_{window}.parquet"
            if not baskets_path.is_file():
                baskets_path = None
            try:
                result = run_validation(
                    policy=pol,
                    window=window,
                    baskets_path=baskets_path,
                    export_dir=args.export_dir,
                    cfg=cfg,
                    deposit=args.deposit,
                )
            except FileNotFoundError as exc:
                print(f"\n[E7] {pol}/{window} — SKIP ({exc})")
                continue
            report["runs"].append(result)
            print_report(result)

    if not report["runs"]:
        print("No policies validated — check export CSV files.")
        return 1

    # Summary
    print("\n" + "=" * 72)
    print("[E7] Summary")
    for res in report["runs"]:
        wf_ok = res["walk_forward"]["gate_pass"]
        print(
            f"  {res['policy']:8s} {res['window']:16s} "
            f"WF={wf_ok} ({res['walk_forward']['n_pass']}/{res['walk_forward']['n_folds']}) "
            f"verdict={res['verdict']}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
