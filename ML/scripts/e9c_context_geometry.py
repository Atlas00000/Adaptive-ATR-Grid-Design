#!/usr/bin/env python3
"""E9c: Context-gated geometry multipliers (offline sweep)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets
from basket_replay import load_window_legs, replay_basket
from e9b_grid_geometry import WINDOW_FILES, replay_kwargs

GeometryFn = Callable[[pd.Series], dict[str, Any]]


def rolling_pf(pnl: pd.Series, window: int) -> pd.Series:
    def _pf(x: np.ndarray) -> float:
        wins = x[x > 0].sum()
        losses = abs(x[x < 0].sum())
        if losses == 0:
            return float(wins > 0)
        return float(wins / losses)

    return pnl.shift(1).rolling(window, min_periods=5).apply(_pf, raw=True)


def enrich_baskets(baskets: pd.DataFrame) -> pd.DataFrame:
    out = baskets.sort_values("open_time").copy()
    out["open_time"] = pd.to_datetime(out["open_time"])
    out["rolling_pf_20"] = rolling_pf(out["basket_pnl"], 20)
    out["rolling_wr_20"] = (
        out["basket_won"].astype(float).shift(1).rolling(20, min_periods=5).mean()
    )
    streak = 0
    streaks: list[int] = []
    for won in out["basket_won"].shift(1):
        if pd.isna(won):
            streaks.append(0)
            continue
        streak = streak + 1 if not bool(won) else 0
        streaks.append(streak)
    out["consec_losses"] = streaks
    out["atr_pips"] = out["entry_atr"] * 10000.0
    out["ym"] = out["open_time"].dt.to_period("M").astype(str)
    return out


def simulate_gated(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    gate: Callable[[pd.Series], bool],
    geometry: dict[str, Any],
    cfg: dict,
) -> pd.DataFrame:
    kw_base = replay_kwargs({}, cfg)
    rows = []
    for _, brow in baskets.iterrows():
        bk = str(brow["basket_key"])
        grp = legs.loc[legs["basket_key"] == bk]
        if grp.empty:
            continue
        apply_geo = bool(gate(brow))
        kw = dict(kw_base)
        if apply_geo:
            kw.update(geometry)
        result = replay_basket(grp, **kw)
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "max_level": int(brow["max_level"]),
                "gated": apply_geo,
                "intervention": result.intervention,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def metrics(sim: pd.DataFrame, prod_net: float | None = None) -> dict:
    pnls = sim["sim_pnl"]
    base = sim["baseline_pnl"]
    exp = expectancy_block(pnls)
    gated_n = int(sim["gated"].sum())
    return {
        "expectancy": exp,
        "baseline_net": round(float(base.sum()), 2),
        "net_delta": round(float(pnls.sum() - base.sum()), 2),
        "gated_baskets": gated_n,
        "gated_pct": round(100.0 * gated_n / len(sim), 1) if len(sim) else 0.0,
        "vs_prod_net": round(float(pnls.sum() - prod_net), 2) if prod_net is not None else None,
    }


def build_gates() -> dict[str, Callable[[pd.Series], bool]]:
    """Entry-time context predicates — no future labels."""
    return {
        "always_on": lambda r: True,
        "always_off": lambda r: False,
        "stress_2024_h1": lambda r: pd.Timestamp("2024-01-01") <= r["open_time"] < pd.Timestamp("2024-07-01"),
        "adx_ge_22": lambda r: float(r["entry_adx"]) >= 22.0,
        "adx_ge_20": lambda r: float(r["entry_adx"]) >= 20.0,
        "adx_ge_18": lambda r: float(r["entry_adx"]) >= 18.0,
        "adx_lt_18": lambda r: float(r["entry_adx"]) < 18.0,
        "adx_lt_17": lambda r: float(r["entry_adx"]) < 17.0,
        "adx_lt_16": lambda r: float(r["entry_adx"]) < 16.0,
        "adx_lt_20": lambda r: float(r["entry_adx"]) < 20.0,
        "bad_hour": lambda r: bool(r["bad_hour"]),
        "session_london": lambda r: str(r["session"]) == "London",
        "session_ny": lambda r: str(r["session"]) == "NY",
        "rolling_pf20_lt_1": lambda r: pd.notna(r.get("rolling_pf_20")) and float(r["rolling_pf_20"]) < 1.0,
        "rolling_pf20_lt_115": lambda r: pd.notna(r.get("rolling_pf_20")) and float(r["rolling_pf_20"]) < 1.15,
        "rolling_wr20_lt_55": lambda r: pd.notna(r.get("rolling_wr_20")) and float(r["rolling_wr_20"]) < 0.55,
        "consec_loss_ge_2": lambda r: int(r.get("consec_losses", 0)) >= 2,
        "consec_loss_ge_3": lambda r: int(r.get("consec_losses", 0)) >= 3,
        "atr_pips_ge_6": lambda r: float(r.get("atr_pips", 0)) >= 6.0,
        "month_stress": lambda r: str(r["ym"]) in {"2024-02", "2024-03", "2024-04", "2024-06", "2024-07", "2024-11"},
        "adx18_or_pf_lt_115": lambda r: float(r["entry_adx"]) >= 18.0
        or (pd.notna(r.get("rolling_pf_20")) and float(r["rolling_pf_20"]) < 1.15),
        "adx20_or_wr_lt_55": lambda r: float(r["entry_adx"]) >= 20.0
        or (pd.notna(r.get("rolling_wr_20")) and float(r["rolling_wr_20"]) < 0.55),
        "bad_hour_or_pf_lt_1": lambda r: bool(r["bad_hour"])
        or (pd.notna(r.get("rolling_pf_20")) and float(r["rolling_pf_20"]) < 1.0),
        "london_and_adx18": lambda r: str(r["session"]) == "London" and float(r["entry_adx"]) >= 18.0,
        "pre_2025": lambda r: r["open_time"] < pd.Timestamp("2025-01-01"),
        "d2_only": lambda r: int(r["max_level"]) >= 2,
    }


def evaluate_combo(
    w02: dict,
    w03: dict,
    gates: dict,
    prod_net: float,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    g = gates
    w02_exp = w02["expectancy"]
    w03_exp = w03["expectancy"]
    if w02_exp["net"] < prod_net * (1.0 + g["net_vs_prod_pct"]):
        reasons.append("w02_net_vs_prod")
    if w03["net_delta"] < g.get("w03_net_delta_min", 0.0):
        reasons.append("w03_no_improve")
    if w02["gated_pct"] > g.get("max_gated_pct", 100.0):
        reasons.append("gated_too_broad_w02")
    if w03_exp["worst"] < g["tail_loss_usd"]:
        reasons.append("tail_fail")
    return len(reasons) == 0, reasons


def run_window(
    window: str,
    gate_name: str,
    gate_fn: Callable[[pd.Series], bool],
    export_dir: Path,
    cfg: dict,
) -> dict:
    path = WINDOW_FILES[window]
    baskets = enrich_baskets(load_baskets(path, window, export_dir))
    legs = load_window_legs(export_dir, window)
    geometry = {"no_add_after_l0_sl": True}
    sim = simulate_gated(legs, baskets, gate_fn, geometry, cfg)
    prod_net = None
    if window == "w02_ext19mo":
        prod_net = float(cfg["baseline"].get("production_net_19mo", 623.0))
    return {
        "window": window,
        "gate": gate_name,
        **metrics(sim, prod_net),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E9c context-gated geometry sweep")
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e9c_report.json",
    )
    args = parser.parse_args()
    cfg = load_config()
    e9c_gates = cfg.get(
        "e9c_gates",
        {
            "net_vs_prod_pct": -0.05,
            "w03_net_delta_min": 50.0,
            "tail_loss_usd": -35.0,
            "max_gated_pct": 60.0,
        },
    )

    gates = build_gates()
    results = []
    for name, fn in gates.items():
        if name in ("always_off", "d2_only"):
            continue
        w02 = run_window("w02_ext19mo", name, fn, args.export_dir, cfg)
        w03 = run_window("w03_longest", name, fn, args.export_dir, cfg)
        passed, fail = evaluate_combo(w02, w03, e9c_gates, float(cfg["baseline"]["production_net_19mo"]))
        entry = {
            "gate": name,
            "w02": w02,
            "w03": w03,
            "combo_pass": passed,
            "combo_fail": fail,
            "score": w02["expectancy"]["net"] + w03["net_delta"],
        }
        results.append(entry)

    results.sort(key=lambda r: r["score"], reverse=True)
    winners = [r for r in results if r["combo_pass"]]

    print("[E9c] Context-gated no_add_after_l0_sl — top combos")
    print("-" * 72)
    for r in results[:8]:
        w2, w3 = r["w02"]["expectancy"], r["w03"]["expectancy"]
        mark = "PASS" if r["combo_pass"] else "fail"
        print(
            f"  {r['gate']:28s}  w02=${w2['net']:6.0f}  w03_d=${r['w03']['net_delta']:+6.0f}  "
            f"gated={r['w02']['gated_pct']:.0f}%/{r['w03']['gated_pct']:.0f}%  {mark}"
        )
    if winners:
        best = winners[0]
        print(f"\n  best PASS: {best['gate']}")
    else:
        print("\n  no gate passed w02+w03 combo — best score:", results[0]["gate"])

    out = {
        "e9c": "context_geometry",
        "geometry": "no_add_after_l0_sl",
        "gates": e9c_gates,
        "results": results,
        "winners": winners,
        "best_pass": winners[0] if winners else None,
        "best_score": results[0] if results else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
