#!/usr/bin/env python3
"""E10e: Conditional L0 TP widen on high oscillation (EDGE-1001, no clip)."""
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
from e9b_grid_geometry import segment_mask
from e9d_physics_labels import l0_path_extremes
from e10c_depth_by_oscillation import LABELS_PATH, load_scores

BASE_TP_ATR = 1.5
WINDOW_FILES = {
    "w03_longest": ROOT / "features" / "baskets_w03_longest.parquet",
    "w02_ext19mo": ROOT / "features" / "baskets_w02_ext19mo.parquet",
    "AI806_805p": ROOT / "features" / "baskets_ai806.parquet",
}

# band filter → L0 tp_atr mult (never < 1.5)
TP_POLICIES: dict[str, dict] = {
    "l0_tp_175_high": {"bands": ("high",), "tp_mult": 1.75, "mfe_check": False},
    "l0_tp_200_high": {"bands": ("high",), "tp_mult": 2.0, "mfe_check": False},
    "l0_tp_175_mid_high": {"bands": ("mid", "high"), "tp_mult": 1.75, "mfe_check": False},
    "l0_tp_175_high_mfe": {"bands": ("high",), "tp_mult": 1.75, "mfe_check": True},
    "l0_tp_200_high_mfe": {"bands": ("high",), "tp_mult": 2.0, "mfe_check": True},
}


def adjust_l0_tp_profit(
    l0: dict,
    tp_mult: float,
    *,
    mfe_check: bool,
) -> float:
    """Widen L0 TP profit only — never tighten."""
    profit = float(l0["profit"])
    if str(l0.get("exit_reason", "")).upper() != "TP" or profit <= 0:
        return profit
    if tp_mult <= BASE_TP_ATR:
        return profit

    scale = tp_mult / BASE_TP_ATR
    if not mfe_check:
        return round(profit * scale, 2)

    l0t = dict(l0)
    l0t["open_time"] = pd.to_datetime(l0t["open_time"])
    l0t["close_time"] = pd.to_datetime(l0t["close_time"])
    _, mfe = l0_path_extremes(l0t)
    target = profit * scale
    if mfe >= target * 0.92:
        return round(target, 2)
    # partial credit if MFE between base TP and target
    if mfe > profit:
        return round(min(target, mfe * 0.98), 2)
    return profit


def simulate_l0_tp_widen(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    scores: pd.DataFrame,
    policy: dict,
) -> pd.DataFrame:
    bands = set(policy["bands"])
    tp_mult = float(policy["tp_mult"])
    mfe_check = bool(policy.get("mfe_check", False))

    rows = []
    for _, brow in baskets.iterrows():
        bk = str(brow["basket_key"])
        grp = legs.loc[legs["basket_key"] == bk].sort_values(["level", "open_time"])
        if grp.empty:
            continue

        band = "mid"
        if bk in scores.index:
            band = str(scores.loc[bk, "enhancement_band"])

        baseline_pnl = float(grp["profit"].sum())
        sim_pnl = baseline_pnl
        l0_adjusted = False

        if band in bands:
            l0_rows = grp.loc[grp["level"] == 0]
            if not l0_rows.empty:
                l0 = l0_rows.iloc[0].to_dict()
                old_l0 = float(l0["profit"])
                new_l0 = adjust_l0_tp_profit(l0, tp_mult, mfe_check=mfe_check)
                if new_l0 > old_l0 + 0.01:
                    sim_pnl = baseline_pnl - old_l0 + new_l0
                    l0_adjusted = True

        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": baseline_pnl,
                "sim_pnl": sim_pnl,
                "max_level": int(brow["max_level"]),
                "enhancement_band": band,
                "l0_tp_widened": l0_adjusted,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def evaluate_gates(w02: dict, baseline_w02: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    exp = w02["expectancy"]
    base = baseline_w02["expectancy"]
    wr_drop = base["win_rate_pct"] - exp["win_rate_pct"]
    if wr_drop > gates["max_wr_drop_w02_pts"]:
        reasons.append(f"wr_drop {wr_drop:.1f}pts > {gates['max_wr_drop_w02_pts']}")
    high = w02.get("high_band") or {}
    if high.get("baskets", 0) >= 10:
        if high.get("avg_win", 0) <= abs(high.get("avg_loss", 0)):
            reasons.append("high_band_avg_win_not_gt_avg_loss")
    elif exp["avg_win"] <= abs(exp["avg_loss"]):
        reasons.append("avg_win_not_gt_avg_loss")
    return len(reasons) == 0, reasons


def run_policy(
    name: str,
    policy: dict,
    export_dir: Path,
    cfg: dict,
) -> dict:
    gates = cfg.get("e10e_gates", {})
    windows: dict[str, dict] = {}

    for window, path in WINDOW_FILES.items():
        baskets = load_baskets(path, window, export_dir)
        legs = load_window_legs(export_dir, window)
        scores = load_scores(window)
        sim = simulate_l0_tp_widen(legs, baskets, scores, policy)
        base_exp = expectancy_block(sim["baseline_pnl"])
        sim_exp = expectancy_block(sim["sim_pnl"])
        widened = int(sim["l0_tp_widened"].sum())
        windows[window] = {
            "expectancy": sim_exp,
            "baseline": base_exp,
            "baseline_net": round(float(sim["baseline_pnl"].sum()), 2),
            "sim_net": round(float(sim["sim_pnl"].sum()), 2),
            "net_delta": round(float(sim["sim_pnl"].sum() - sim["baseline_pnl"].sum()), 2),
            "l0_widened_baskets": widened,
            "l0_widened_pct": round(100.0 * widened / len(sim), 1) if len(sim) else 0.0,
            "high_band": expectancy_block(sim.loc[sim["enhancement_band"] == "high", "sim_pnl"])
            if (sim["enhancement_band"] == "high").any()
            else {},
        }
        for seg in ("2024_h1",):
            sub = sim.loc[segment_mask(sim, seg)]
            if len(sub):
                windows[window]["segments"] = {
                    seg: {
                        "net_delta": round(
                            float(sub["sim_pnl"].sum() - sub["baseline_pnl"].sum()), 2
                        ),
                        "expectancy": expectancy_block(sub["sim_pnl"]),
                    }
                }

    w02 = windows["w02_ext19mo"]
    baseline_w02 = {"expectancy": w02["baseline"]}
    passed, fail = evaluate_gates(w02, baseline_w02, gates)

    return {
        "policy": name,
        "params": policy,
        "windows": windows,
        "gate_pass": passed,
        "gate_fail": fail,
    }


def print_policy(res: dict) -> None:
    w02 = res["windows"]["w02_ext19mo"]
    w03 = res["windows"]["w03_longest"]
    e = w02["expectancy"]
    b = w02["baseline"]
    print(
        f"\n  [{res['policy']}] tp={res['params']['tp_mult']} bands={res['params']['bands']}  "
        f"gate={'PASS' if res['gate_pass'] else 'FAIL'}"
    )
    if res["gate_fail"]:
        print(f"    fail: {', '.join(res['gate_fail'])}")
    print(
        f"    w02 net=${w02['sim_net']:.0f} dnet=${w02['net_delta']:+.1f}  "
        f"WR {b['win_rate_pct']:.1f}% -> {e['win_rate_pct']:.1f}%  "
        f"avgW ${b['avg_win']:.2f} -> ${e['avg_win']:.2f}  "
        f"widened {w02['l0_widened_pct']:.0f}%"
    )
    print(
        f"    w03 dnet=${w03['net_delta']:+.1f}  "
        f"high-band avgW=${w02.get('high_band', {}).get('avg_win', 0):.2f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="E10e L0 TP widen sweep")
    parser.add_argument("--policy", default="all", choices=["all", *TP_POLICIES.keys()])
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10e_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    if "e10e_gates" not in cfg:
        cfg["e10e_gates"] = {
            "max_wr_drop_w02_pts": 3.0,
            "net_vs_baseline_pct": 0.0,
        }

    policies = TP_POLICIES if args.policy == "all" else {args.policy: TP_POLICIES[args.policy]}

    print("[E10e] L0 TP widen x oscillation band (high only, never clip)")
    print("-" * 72)

    results = [run_policy(n, p, args.export_dir, cfg) for n, p in policies.items()]
    for r in results:
        print_policy(r)

    best = max(
        results,
        key=lambda r: (r["gate_pass"], r["windows"]["w02_ext19mo"]["net_delta"]),
    )
    print("\n" + "=" * 72)
    print(
        f"[E10e] best: {best['policy']}  "
        f"w02 dnet=${best['windows']['w02_ext19mo']['net_delta']:+.0f}  "
        f"gate={'PASS' if best['gate_pass'] else 'FAIL'}"
    )

    report = {
        "e10e": "leg_tp_widen",
        "edge_id": "EDGE-1001",
        "rules": "L0 only; never tighten; no basket TP",
        "gates": cfg["e10e_gates"],
        "policies": results,
        "best_policy": best["policy"],
        "best_gate_pass": best["gate_pass"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
