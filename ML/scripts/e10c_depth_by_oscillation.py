#!/usr/bin/env python3
"""E10c: Dynamic max_levels × oscillation score (enhancement, not blocking)."""
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
from e9b_grid_geometry import replay_kwargs, segment_mask
from simulate_policy import equity_metrics

WINDOW_FILES = {
    "w03_longest": ROOT / "features" / "baskets_w03_longest.parquet",
    "w02_ext19mo": ROOT / "features" / "baskets_w02_ext19mo.parquet",
    "AI806_805p": ROOT / "features" / "baskets_ai806.parquet",
}
LABELS_PATH = ROOT / "features" / "e10b_labels.parquet"

# low / mid / high tertile → max_grid_levels (level index cap; 6 = full grid)
DEPTH_POLICIES: dict[str, dict[str, int]] = {
    "osc_depth_246": {"low": 2, "mid": 4, "high": 6},
    "osc_depth_246_soft": {"low": 2, "mid": 6, "high": 6},
    "osc_depth_1246": {"low": 1, "mid": 2, "high": 6},
    "osc_depth_446": {"low": 4, "mid": 4, "high": 6},
    "osc_depth_266": {"low": 2, "mid": 6, "high": 6},
}


def load_scores(window: str) -> pd.DataFrame:
    if not LABELS_PATH.is_file():
        raise FileNotFoundError(f"Run e10b first: {LABELS_PATH}")
    df = pd.read_parquet(LABELS_PATH)
    sub = df.loc[df["window"] == window, ["basket_key", "enhancement_band", "oscillation_score_open"]]
    if sub.empty:
        raise ValueError(f"No E10b labels for window {window!r}")
    return sub.set_index(sub["basket_key"].astype(str))


def depth_for_band(policy_map: dict[str, int], band: str) -> int:
    return int(policy_map.get(str(band), policy_map.get("mid", 6)))


def simulate_osc_depth(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    scores: pd.DataFrame,
    policy_map: dict[str, int],
    cfg: dict,
    deposit: float = 200.0,
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
        cap = depth_for_band(policy_map, band)
        kw = dict(kw_base, max_grid_levels=cap)
        result = replay_basket(grp, **kw)
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "max_level": int(brow["max_level"]),
                "enhancement_band": band,
                "oscillation_score_open": score,
                "max_grid_levels": cap,
                "capped": cap < 6,
                "intervention": result.intervention,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def policy_metrics(sim: pd.DataFrame, baseline_pnls: pd.Series, deposit: float) -> dict:
    pnls = sim["sim_pnl"]
    base_pnls = sim["baseline_pnl"]
    exp = expectancy_block(pnls)
    eq = equity_metrics(pnls, deposit)
    d2 = sim.loc[sim["max_level"] >= 2]
    d2_exp = expectancy_block(d2["sim_pnl"]) if len(d2) else {"baskets": 0}
    capped = int(sim["capped"].sum()) if "capped" in sim.columns else 0
    changed = int((pnls.round(2) != base_pnls.round(2)).sum())
    return {
        "expectancy": exp,
        "equity": eq,
        "baseline_net": round(float(base_pnls.sum()), 2),
        "sim_net": round(float(pnls.sum()), 2),
        "net_delta": round(float(pnls.sum() - base_pnls.sum()), 2),
        "d2_plus": d2_exp,
        "capped_baskets": capped,
        "capped_pct": round(100.0 * capped / len(sim), 1) if len(sim) else 0.0,
        "pnl_changed_baskets": changed,
        "pnl_changed_pct": round(100.0 * changed / len(sim), 1) if len(sim) else 0.0,
    }


def evaluate_e10c_gates(
    w02: dict,
    w03: dict,
    prod_net_w02: float,
    gates: dict,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    w02_net = w02["sim_net"]
    floor = prod_net_w02 * (1.0 + gates["net_vs_prod_pct"])
    if w02_net < floor:
        reasons.append(f"w02_net ${w02_net:.0f} < floor ${floor:.0f}")
    if w03["net_delta"] < gates["w03_net_delta_min"]:
        reasons.append(f"w03_dnet ${w03['net_delta']:.0f} < ${gates['w03_net_delta_min']:.0f}")
    if w02["expectancy"]["worst"] < gates["tail_loss_usd"]:
        reasons.append(f"w02_worst ${w02['expectancy']['worst']:.1f}")
    if w02["capped_pct"] > gates["max_capped_pct"]:
        reasons.append(f"w02_capped {w02['capped_pct']:.0f}% > {gates['max_capped_pct']:.0f}%")
    return len(reasons) == 0, reasons


def run_policy(
    policy_name: str,
    policy_map: dict[str, int],
    export_dir: Path,
    cfg: dict,
    prod_net_w02: float,
) -> dict:
    gates = cfg.get("e10c_gates", cfg.get("e9c_gates", {}))
    window_results: dict[str, dict] = {}

    for window, path in WINDOW_FILES.items():
        baskets = load_baskets(path, window, export_dir)
        legs = load_window_legs(export_dir, window)
        scores = load_scores(window)
        sim = simulate_osc_depth(legs, baskets, scores, policy_map, cfg)
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
    passed, fail = evaluate_e10c_gates(w02, w03, prod_net_w02, gates)

    return {
        "policy": policy_name,
        "depth_map": policy_map,
        "windows": window_results,
        "gate_pass": passed,
        "gate_fail": fail,
    }


def print_policy(res: dict) -> None:
    print(f"\n  [{res['policy']}] map={res['depth_map']}  gate={'PASS' if res['gate_pass'] else 'FAIL'}")
    if res["gate_fail"]:
        print(f"    fail: {', '.join(res['gate_fail'])}")
    for window in WINDOW_FILES:
        m = res["windows"][window]["all"]
        e = m["expectancy"]
        h1 = res["windows"][window]["segments"].get("2024_h1", {})
        h1_net = h1.get("sim_net", h1.get("net_delta"))
        print(
            f"    {window:14s} net=${m['sim_net']:7.1f} dnet=${m['net_delta']:+6.1f} "
            f"PF={e['profit_factor']:.2f} worst=${e['worst']:.1f} "
            f"capped={m['capped_pct']:.0f}% changed={m['pnl_changed_pct']:.0f}%"
            + (f"  H1 dnet=${h1.get('net_delta', 0):+.1f}" if h1 else "")
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="E10c oscillation depth sweep")
    parser.add_argument(
        "--policy",
        default="all",
        choices=["all", *DEPTH_POLICIES.keys()],
    )
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10c_report.json",
    )
    args = parser.parse_args()

    cfg = load_config()
    if "e10c_gates" not in cfg:
        cfg["e10c_gates"] = {
            "net_vs_prod_pct": -0.05,
            "w03_net_delta_min": 50.0,
            "tail_loss_usd": -35.0,
            "max_capped_pct": 55.0,
        }

    prod_net = float(cfg["baseline"]["production_net_19mo"])
    policies = DEPTH_POLICIES if args.policy == "all" else {args.policy: DEPTH_POLICIES[args.policy]}

    print("[E10c] Dynamic max_levels x oscillation band (enhancement)")
    print(f"  w02 prod floor: ${prod_net * 0.95:.0f}  |  labels: {LABELS_PATH.name}")
    print("-" * 72)

    results = []
    for name, pmap in policies.items():
        res = run_policy(name, pmap, args.export_dir, cfg, prod_net)
        results.append(res)
        print_policy(res)

    best = max(results, key=lambda r: (r["gate_pass"], r["windows"]["w03_longest"]["all"]["net_delta"]))
    print("\n" + "=" * 72)
    print(
        f"[E10c] best: {best['policy']}  "
        f"w02=${best['windows']['w02_ext19mo']['all']['sim_net']:.0f}  "
        f"w03 dnet=${best['windows']['w03_longest']['all']['net_delta']:+.0f}  "
        f"gate={'PASS' if best['gate_pass'] else 'FAIL'}"
    )

    report = {
        "e10c": "osc_depth_by_oscillation",
        "purpose": "tertile band → max_grid_levels; no basket skip",
        "prod_net_w02": prod_net,
        "gates": cfg["e10c_gates"],
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
