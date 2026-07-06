#!/usr/bin/env python3
"""E9d: Train stack-risk model + simulate physics-gated no_add_after_l0_sl."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import expectancy_block, load_baskets
from basket_replay import load_window_legs, replay_basket
from e9b_grid_geometry import WINDOW_FILES, replay_kwargs
from e9c_context_geometry import enrich_baskets, simulate_gated, build_gates
from e9d_physics_labels import PHYSICS_FEATURES, l0_path_extremes

RULE_GATES: dict[str, Callable[[dict], bool]] = {
    "adx_lt_18": lambda leg: float(leg.get("adx", 99)) < 18.0,
    "l0_hold_gt_1h": lambda leg: float(leg.get("hold_sec", 0)) > 3600,
    "l0_fast_sl": lambda leg: float(leg.get("hold_sec", 0)) < 900,
    "adx18_hold_gt_1h": lambda leg: float(leg.get("adx", 99)) < 18.0
    and float(leg.get("hold_sec", 0)) > 3600,
    "adx18_l0_mae_deep": lambda leg: _l0_mae_deep(leg),
}


def _l0_mae_deep(leg: dict) -> bool:
    mae, _ = l0_path_extremes(leg)
    return float(leg.get("adx", 99)) < 18.0 and abs(min(mae, 0.0)) >= 9.5


def leg_feature_row(leg: dict, meta: dict | None = None) -> dict:
    mae, mfe = l0_path_extremes(leg)
    atr = float(leg.get("atr", 0.0001))
    atr_pips = atr * 10000.0
    hold_h = float(leg.get("hold_sec", 0)) / 3600.0
    meta = meta or {}
    return {
        "entry_adx": float(leg.get("adx", 0)),
        "entry_atr": atr,
        "atr_pips": atr_pips,
        "l0_hold_hours": hold_h,
        "l0_loss_usd": float(leg.get("profit", 0)),
        "l0_mae_usd": mae,
        "l0_mfe_usd": mfe,
        "l0_mae_atr": abs(min(mae, 0.0)) / max(atr_pips * 0.1, 0.01),
        "hour": int(leg.get("hour", 0)),
        "weekday": int(leg.get("weekday", 0)),
        "bad_hour": bool(int(leg.get("bad_hour", 0))),
        "bias_sell": int(str(leg.get("direction", "")) == "SELL"),
        "session_london": int(str(leg.get("session", "")) == "London"),
        "session_ny": int(str(leg.get("session", "")) == "NY"),
        "rolling_pf_20": float(meta.get("rolling_pf_20", np.nan))
        if meta and pd.notna(meta.get("rolling_pf_20"))
        else np.nan,
        "rolling_wr_20": float(meta.get("rolling_wr_20", np.nan))
        if meta and pd.notna(meta.get("rolling_wr_20"))
        else np.nan,
        "consec_losses": int(meta.get("consec_losses", 0)) if meta else 0,
    }


def train_stack_risk(
    labels: pd.DataFrame,
    train_windows: tuple[str, ...] = ("w03_longest",),
) -> tuple[Pipeline, dict]:
    train = labels[labels["window"].isin(train_windows)].copy()
    X = train[PHYSICS_FEATURES].astype(float)
    y = train["label_block_beneficial"].astype(int)

    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "clf",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    C=0.4,
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(X, y)
    proba = model.predict_proba(X)[:, 1]
    auc = roc_auc_score(y, proba) if y.nunique() > 1 else float("nan")
    ap = average_precision_score(y, proba) if y.nunique() > 1 else float("nan")
    report = {
        "n_train": int(len(train)),
        "pos_rate": round(float(y.mean()), 3),
        "train_auc": round(float(auc), 3),
        "train_ap": round(float(ap), 3),
    }
    return model, report


def make_model_gate(
    model: Pipeline,
    threshold: float,
    meta_lookup: dict[str, dict],
) -> Callable[[dict, float], bool]:
    def gate(leg: dict, _realized: float) -> bool:
        bk = str(leg.get("basket_key", ""))
        row = leg_feature_row(leg, meta_lookup.get(bk))
        X = pd.DataFrame([row])[PHYSICS_FEATURES].astype(float)
        return float(model.predict_proba(X)[0, 1]) >= threshold

    return gate


def make_rule_gate(rule_name: str) -> Callable[[dict, float], bool]:
    fn = RULE_GATES[rule_name]

    def gate(leg: dict, _realized: float) -> bool:
        return bool(fn(leg))

    return gate


def simulate_physics(
    legs: pd.DataFrame,
    baskets: pd.DataFrame,
    gate_fn: Callable[[dict, float], bool],
    cfg: dict,
) -> pd.DataFrame:
    kw = replay_kwargs({}, cfg)
    meta_rows = enrich_baskets(baskets)
    meta = {str(r["basket_key"]): r.to_dict() for _, r in meta_rows.iterrows()}
    rows = []
    for _, brow in meta_rows.iterrows():
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
        fired = result.intervention in ("physics_l0_sl_gate", "no_add_after_l0_sl")
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "max_level": int(brow["max_level"]),
                "gated": fired,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time").reset_index(drop=True)


def window_metrics(sim: pd.DataFrame, prod_net: float | None = None) -> dict:
    exp = expectancy_block(sim["sim_pnl"])
    base = sim["baseline_pnl"]
    h1 = sim[(sim["open_time"] >= "2024-01-01") & (sim["open_time"] < "2024-07-01")]
    h1_net = float(h1["sim_pnl"].sum()) if len(h1) else 0.0
    return {
        "expectancy": exp,
        "baseline_net": round(float(base.sum()), 2),
        "net_delta": round(float(sim["sim_pnl"].sum() - base.sum()), 2),
        "gated_pct": round(100.0 * float(sim["gated"].mean()), 1),
        "h1_net": round(h1_net, 2),
        "h1_baskets": int(len(h1)),
        "vs_prod": round(float(exp["net"] - prod_net), 2) if prod_net is not None else None,
    }


def evaluate_e9d_combo(w02: dict, w03: dict, cfg: dict) -> tuple[bool, list[str]]:
    g = cfg.get("e9c_gates", {})
    prod = float(cfg["baseline"]["production_net_19mo"])
    reasons = []
    if w02["expectancy"]["net"] < prod * (1.0 + g.get("net_vs_prod_pct", -0.05)):
        reasons.append("w02_net_vs_prod")
    if w03["net_delta"] < g.get("w03_net_delta_min", 50.0):
        reasons.append("w03_delta")
    if w02["gated_pct"] > g.get("max_gated_pct", 55.0):
        reasons.append("w02_gated_broad")
    if w03["h1_net"] < g.get("e9d_h1_net_min", -80.0):
        reasons.append("h1_still_bleed")
    return len(reasons) == 0, reasons


def meta_lookup_for_windows(export_dir: Path, window: str | None = None) -> dict[str, dict]:
    """Basket meta for physics gate at L0 close."""
    meta: dict[str, dict] = {}
    windows = (window,) if window else ("w03_longest", "w02_ext19mo")
    for w in windows:
        path = WINDOW_FILES.get(w, ROOT / "features" / f"baskets_{w}.parquet")
        for _, r in enrich_baskets(load_baskets(path, w, export_dir)).iterrows():
            meta[str(r["basket_key"])] = r.to_dict()
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="E9d physics gate simulation")
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--labels",
        type=Path,
        default=ROOT / "features" / "physics_l0_sl.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e9d_report.json",
    )
    args = parser.parse_args()
    cfg = load_config()
    if "e9c_gates" not in cfg:
        cfg["e9c_gates"] = {}
    cfg["e9c_gates"]["e9d_h1_net_min"] = -80.0

    if not args.labels.is_file():
        import e9d_physics_labels

        e9d_physics_labels.main()

    labels = pd.read_parquet(args.labels)
    model, train_report = train_stack_risk(labels)

    test = labels[labels["window"] == "w02_ext19mo"]
    if len(test) > 10:
        proba = model.predict_proba(test[PHYSICS_FEATURES].astype(float))[:, 1]
        y_test = test["label_block_beneficial"].astype(int)
        train_report["w02_auc"] = round(
            float(roc_auc_score(y_test, proba)) if y_test.nunique() > 1 else float("nan"),
            3,
        )

    model_path = ROOT / "models" / "stack_risk_v0.joblib"
    model_path.parent.mkdir(exist_ok=True)
    joblib.dump(model, model_path)
    train_report["model_path"] = str(model_path)

    meta_lookup: dict[str, dict] = {}
    for window in ("w03_longest", "w02_ext19mo"):
        meta_lookup.update(meta_lookup_for_windows(args.export_dir, window))

    policies: list[dict[str, Any]] = []
    for rule in RULE_GATES:
        policies.append({"name": f"rule_{rule}", "gate_fn": make_rule_gate(rule)})
    for thr in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65):
        policies.append(
            {
                "name": f"lr_p{int(thr * 100)}",
                "threshold": thr,
                "gate_fn": make_model_gate(model, thr, meta_lookup),
            }
        )

    results = []
    prod_net = float(cfg["baseline"]["production_net_19mo"])

    for pol in policies:
        entry: dict[str, Any] = {"policy": pol["name"], "windows": {}}
        if "threshold" in pol:
            entry["threshold"] = pol["threshold"]
        for window in ("w02_ext19mo", "w03_longest"):
            baskets = load_baskets(WINDOW_FILES[window], window, args.export_dir)
            legs = load_window_legs(args.export_dir, window)
            sim = simulate_physics(legs, baskets, pol["gate_fn"], cfg)
            entry["windows"][window] = window_metrics(
                sim, prod_net if window == "w02_ext19mo" else None
            )
        passed, fail = evaluate_e9d_combo(
            entry["windows"]["w02_ext19mo"],
            entry["windows"]["w03_longest"],
            cfg,
        )
        entry["combo_pass"] = passed
        entry["combo_fail"] = fail
        entry["score"] = (
            entry["windows"]["w02_ext19mo"]["expectancy"]["net"]
            + entry["windows"]["w03_longest"]["net_delta"]
        )
        results.append(entry)

    adx_entry: dict[str, Any] = {"policy": "baseline_adx_lt_18", "windows": {}}
    adx_gate = build_gates()["adx_lt_18"]
    for window in ("w02_ext19mo", "w03_longest"):
        baskets = load_baskets(WINDOW_FILES[window], window, args.export_dir)
        legs = load_window_legs(args.export_dir, window)
        sim = simulate_gated(legs, baskets, adx_gate, {"no_add_after_l0_sl": True}, cfg)
        adx_entry["windows"][window] = window_metrics(
            sim, prod_net if window == "w02_ext19mo" else None
        )
    adx_pass, adx_fail = evaluate_e9d_combo(
        adx_entry["windows"]["w02_ext19mo"],
        adx_entry["windows"]["w03_longest"],
        cfg,
    )
    adx_entry["combo_pass"] = adx_pass
    adx_entry["combo_fail"] = adx_fail
    results.append(adx_entry)

    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    winners = [r for r in results if r.get("combo_pass")]

    print("[E9d] Physics-gated L0-SL stack risk")
    print(f"  train: {train_report}")
    print("-" * 72)
    for r in results[:12]:
        w2 = r["windows"]["w02_ext19mo"]
        w3 = r["windows"]["w03_longest"]
        mark = "PASS" if r.get("combo_pass") else "fail"
        print(
            f"  {r['policy']:24s}  w02=${w2['expectancy']['net']:6.0f}  "
            f"w03_d=${w3['net_delta']:+6.0f}  h1=${w3['h1_net']:6.0f}  "
            f"gated={w2['gated_pct']:.0f}%/{w3['gated_pct']:.0f}%  {mark}"
        )

    out = {
        "e9d": "physics_stack_risk",
        "train": train_report,
        "features": PHYSICS_FEATURES,
        "results": results,
        "winners": winners,
        "best_pass": winners[0] if winners else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
