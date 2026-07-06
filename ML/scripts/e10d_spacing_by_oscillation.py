#!/usr/bin/env python3
"""E10d: Dynamic spacing_mult x oscillation score (enhancement, one dimension)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets
from basket_replay import load_window_legs, replay_basket
from e9b_grid_geometry import replay_kwargs, segment_mask
from e10c_depth_by_oscillation import LABELS_PATH, load_scores, policy_metrics

WINDOW_FILES = {
    "w03_longest": ROOT / "features" / "baskets_w03_longest.parquet",
    "w02_ext19mo": ROOT / "features" / "baskets_w02_ext19mo.parquet",
    "AI806_805p": ROOT / "features" / "baskets_ai806.parquet",
}

# low / mid / high tertile → spacing_mult (1.0 = baseline)
SPACING_POLICIES: dict[str, dict[str, float]] = {
    "osc_space_085_100_125": {"low": 0.85, "mid": 1.0, "high": 1.25},
    "osc_space_090_100_150": {"low": 0.90, "mid": 1.0, "high": 1.50},
    "osc_space_100_100_125": {"low": 1.0, "mid": 1.0, "high": 1.25},
    "osc_space_100_100_150": {"low": 1.0, "mid": 1.0, "high": 1.50},
    "osc_space_085_100_100": {"low": 0.85, "mid": 1.0, "high": 1.0},
}


def spacing_for_band(policy_map: dict[str, float], band: str) -> float:
    return float(policy_map.get(str(band), policy_map.get("mid", 1.0)))


def simulate_osc_spacing(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    scores: pd.DataFrame,
    policy_map: dict[str, float],
    cfg: dict,
) -> pd.DataFrame:
    kw_base = replay_kwargs({}, cfg)
    rows = []
    for _, brow in baskets.iterrows():
        bk = str(brow["basket_key"])
        grp = legs.loc[legs["basket_key"] == bk]
        if grp.empty:
            continue
        band = "mid"
        score = float("nan")
        if bk in scores.index:
            band = str(scores.loc[bk, "enhancement_band"])
            score = float(scores.loc[bk, "oscillation_score_open"])
        mult = spacing_for_band(policy_map, band)
        kw = dict(
            kw_base,
            spacing_mult=mult,
            spacing_min_gap_sec=180.0 if mult > 1.0 else 300.0,
        )
        result = replay_basket(grp, **kw)
        adjusted = mult != 1.0
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "max_level": int(brow["max_level"]),
                "enhancement_band": band,
                "oscillation_score_open": score,
                "spacing_mult": mult,
                "capped": adjusted,
                "intervention": result.intervention,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def evaluate_e10d_gates(w02: dict, w03: dict, prod_net: float, gates: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    floor = prod_net * (1.0 + gates["net_vs_prod_pct"])
    if w02["sim_net"] < floor:
        reasons.append(f"w02_net ${w02['sim_net']:.0f} < ${floor:.0f}")
    if w03["net_delta"] < gates["w03_net_delta_min"]:
        reasons.append(f"w03_dnet ${w03['net_delta']:.0f} < ${gates['w03_net_delta_min']:.0f}")
    if w02["expectancy"]["worst"] < gates["tail_loss_usd"]:
        reasons.append("w02_tail")
    return len(reasons) == 0, reasons


def run_policy(
    policy_name: str,
    policy_map: dict[str, float],
    export_dir: Path,
    cfg: dict,
    prod_net: float,
) -> dict:
    gates = cfg.get("e10d_gates", cfg.get("e10c_gates", {}))
    window_results: dict[str, dict] = {}

    for window, path in WINDOW_FILES.items():
        baskets = load_baskets(path, window, export_dir)
        legs = load_window_legs(export_dir, window)
        scores = load_scores(window)
        sim = simulate_osc_spacing(legs, baskets, scores, policy_map, cfg)
        window_results[window] = {
            "all": policy_metrics(sim, sim["baseline_pnl"], 200.0),
            "segments": {},
        }
        for seg in ("2024_h1", "d2_plus", "rest"):
            sub = sim.loc[segment_mask(sim, seg)]
            if len(sub):
                window_results[window]["segments"][seg] = policy_metrics(
                    sub, sub["baseline_pnl"], 200.0
                )

    w02 = window_results["w02_ext19mo"]["all"]
    w03 = window_results["w03_longest"]["all"]
    passed, fail = evaluate_e10d_gates(w02, w03, prod_net, gates)

    return {
        "policy": policy_name,
        "spacing_map": policy_map,
        "windows": window_results,
        "gate_pass": passed,
        "gate_fail": fail,
    }


def print_policy(res: dict) -> None:
    print(f"\n  [{res['policy']}] map={res['spacing_map']}  gate={'PASS' if res['gate_pass'] else 'FAIL'}")
    if res["gate_fail"]:
        print(f"    fail: {', '.join(res['gate_fail'])}")
    for window in WINDOW_FILES:
        m = res["windows"][window]["all"]
        e = m["expectancy"]
        print(
            f"    {window:14s} net=${m['sim_net']:7.1f} dnet=${m['net_delta']:+6.1f} "
            f"PF={e['profit_factor']:.2f} worst=${e['worst']:.1f} "
            f"changed={m['pnl_changed_pct']:.0f}%"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="E10d oscillation spacing sweep")
    parser.add_argument("--policy", default="all", choices=["all", *SPACING_POLICIES.keys()])
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10d_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    if "e10d_gates" not in cfg:
        cfg["e10d_gates"] = cfg.get("e10c_gates", {})

    prod_net = float(cfg["baseline"]["production_net_19mo"])
    policies = (
        SPACING_POLICIES if args.policy == "all" else {args.policy: SPACING_POLICIES[args.policy]}
    )

    print("[E10d] Dynamic spacing_mult x oscillation band")
    print("-" * 72)

    results = [run_policy(n, m, args.export_dir, cfg, prod_net) for n, m in policies.items()]
    for r in results:
        print_policy(r)

    best = max(results, key=lambda r: (r["gate_pass"], r["windows"]["w03_longest"]["all"]["net_delta"]))
    print("\n" + "=" * 72)
    print(
        f"[E10d] best: {best['policy']}  "
        f"w02=${best['windows']['w02_ext19mo']['all']['sim_net']:.0f}  "
        f"w03 dnet=${best['windows']['w03_longest']['all']['net_delta']:+.0f}  "
        f"gate={'PASS' if best['gate_pass'] else 'FAIL'}"
    )

    report = {
        "e10d": "osc_spacing_by_oscillation",
        "gates": cfg.get("e10d_gates"),
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
