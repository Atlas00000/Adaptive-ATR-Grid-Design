#!/usr/bin/env python3
"""E10a: Three-way stacked wire validation — LOCK-202 vs LOCK-809 vs LOCK-AI+809."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import load_baskets
from basket_replay import load_window_legs, replay_basket
from e7_validate import run_validation
from e9c_context_geometry import enrich_baskets
from e9d_simulate import make_model_gate, meta_lookup_for_windows
from simulate_policy import health_805p_kwargs, simulate_memory

POLICIES = (
    ("lock202", "LOCK-202", "AAG_EURUSD_M5_production.set"),
    ("lock202_physics_p45", "LOCK-809", "AAG_EURUSD_M5_AI-809_physics-p45.set"),
    ("lock_ai_physics_p45", "LOCK-AI+809", "AAG_EURUSD_M5_LOCK-AI+809_physics-p45.set"),
)
WINDOWS = (
    ("w02_ext19mo", "Jan 2025–Jul 2026 (wire)"),
    ("w03_longest", "Jan 2022–Jul 2026 (ext22)"),
)
TAIL_GATE = -35.0


def stacked_intervention_stats(
    baskets: pd.DataFrame,
    cfg: dict,
    export_dir: Path,
    window: str,
) -> dict:
    """Offline proxy for E10a-004: physics gate + SL cascade counts."""
    model_path = ROOT / "models" / "stack_risk_v0.joblib"
    model = joblib.load(model_path)
    meta = meta_lookup_for_windows(export_dir, window)
    gate_fn = make_model_gate(model, 0.45, meta)
    enriched = enrich_baskets(baskets)
    legs = load_window_legs(export_dir, window)
    kw = health_805p_kwargs(cfg)

    physics_blocks = 0
    l0_sl_events = 0
    interventions: Counter[str] = Counter()

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
        interventions[result.intervention] += 1
        if result.intervention == "physics_l0_sl_gate":
            physics_blocks += 1
        l0 = grp.loc[grp["level"] == 0]
        if not l0.empty and str(l0.iloc[0].get("reason", "")).upper().find("SL") >= 0:
            l0_sl_events += 1

    n = len(enriched)
    return {
        "baskets": n,
        "physics_l0_sl_gate_baskets": physics_blocks,
        "physics_gate_pct": round(100.0 * physics_blocks / n, 1) if n else 0.0,
        "sl_cascade_baskets": int(interventions.get("sl_cascade", 0)),
        "sl_cascade_pct": round(100.0 * interventions.get("sl_cascade", 0) / n, 1) if n else 0.0,
        "interventions": dict(interventions),
    }


def evaluate_promote(comparison: dict) -> dict:
    """Promote LOCK-AI+809 if tail < -35 and net >= LOCK-809 on wire window."""
    wire = comparison.get("w02_ext19mo", {})
    p809 = wire.get("LOCK-809", {})
    stacked = wire.get("LOCK-AI+809", {})
    if not p809 or not stacked:
        return {"promote": False, "reason": "missing wire window results"}

    tail_ok = stacked.get("worst", 0.0) > TAIL_GATE
    net_ok = stacked.get("net", 0.0) >= p809.get("net", 0.0)
    dd_ok = stacked.get("max_dd_pct", 999.0) <= p809.get("max_dd_pct", 999.0)

    promote = tail_ok and net_ok
    reasons = []
    if not tail_ok:
        reasons.append(f"tail {stacked.get('worst'):.2f} not > {TAIL_GATE}")
    if not net_ok:
        reasons.append(f"net ${stacked.get('net'):.2f} < LOCK-809 ${p809.get('net'):.2f}")
    if promote and not dd_ok:
        reasons.append(f"DD improved caution: {stacked.get('max_dd_pct'):.1f}% vs {p809.get('max_dd_pct'):.1f}%")

    return {
        "promote": promote,
        "tail_ok": tail_ok,
        "net_ok": net_ok,
        "dd_ok": dd_ok,
        "reason": "; ".join(reasons) if reasons else "PASS wire gate",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E10a stacked wire validation")
    parser.add_argument("--deposit", type=float, default=200.0)
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10a_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    report: dict = {
        "e10a": "stacked wire validation",
        "deposit": args.deposit,
        "tail_gate_usd": TAIL_GATE,
        "runs": [],
        "comparison": {},
        "interventions": {},
        "promote": {},
    }

    print("[E10a] Three-way stacked wire validation ($200)")
    print("=" * 80)

    for window, label in WINDOWS:
        print(f"\n  Window: {window} — {label}")
        print("-" * 80)
        report["comparison"][window] = {}

        for policy, bundle, preset in POLICIES:
            result = run_validation(
                policy=policy,
                window=window,
                baskets_path=ROOT / "features" / f"baskets_{window}.parquet",
                export_dir=args.export_dir,
                cfg=cfg,
                deposit=args.deposit,
            )
            f = result["full_window"]
            wf = result["walk_forward"]
            row = {
                "bundle": bundle,
                "preset": preset,
                "policy": policy,
                **f,
                "worst": result["worst_basket"],
                "geometry_gated_pct": result.get("geometry_gated_pct"),
                "wf_pass_rate": wf["pass_rate"],
                "wf_n_pass": wf["n_pass"],
                "wf_n_folds": wf["n_folds"],
                "verdict": result["verdict"],
            }
            report["runs"].append({"window": window, **row})
            report["comparison"][window][bundle] = row

            gate_s = (
                f" gated={result['geometry_gated_pct']:.1f}%"
                if result.get("geometry_gated_pct") is not None
                else ""
            )
            print(
                f"  {bundle:12s} net=${f['net']:7.2f} PF={f['pf']:.2f} "
                f"DD={f['max_dd_pct']:5.1f}% worst=${result['worst_basket']:6.2f} "
                f"WF={wf['n_pass']}/{wf['n_folds']}{gate_s}"
            )

        if window == "w02_ext19mo":
            baskets = load_baskets(
                ROOT / "features" / f"baskets_{window}.parquet",
                window,
                args.export_dir,
            )
            report["interventions"][window] = stacked_intervention_stats(
                baskets, cfg, args.export_dir, window
            )
            iv = report["interventions"][window]
            print(
                f"\n  [E10a-004 offline] physics gate: {iv['physics_gate_pct']:.1f}% "
                f"({iv['physics_l0_sl_gate_baskets']}/{iv['baskets']}) | "
                f"SL cascade: {iv['sl_cascade_pct']:.1f}% "
                f"({iv['sl_cascade_baskets']}/{iv['baskets']})"
            )

    report["promote"] = evaluate_promote(report["comparison"])
    print("\n" + "=" * 80)
    print(f"[E10a] Promote LOCK-AI+809 (wire): {'YES' if report['promote']['promote'] else 'NO'}")
    print(f"       {report['promote']['reason']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
