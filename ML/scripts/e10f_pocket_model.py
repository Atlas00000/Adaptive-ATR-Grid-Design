#!/usr/bin/env python3
"""E10f: 2024 H1 pocket model — autopsy, train pre-2024, policy sweep."""
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
from e9b_grid_geometry import replay_kwargs, segment_mask
from e9c_context_geometry import enrich_baskets
from e9d_simulate import make_model_gate, meta_lookup_for_windows, simulate_physics
from e10c_depth_by_oscillation import LABELS_PATH

WINDOW = "w03_longest"
BASKETS_PATH = ROOT / "features" / "baskets_w03_longest.parquet"
BLEED_MONTHS = (4, 5, 6, 7)

POCKET_FEATURES = [
    "entry_adx",
    "atr_pips",
    "hour",
    "weekday",
    "bad_hour",
    "month_sin",
    "month_cos",
    "rolling_pf_20",
    "rolling_wr_20",
    "consec_losses",
    "oscillation_score_open",
    "direction_chop_20",
    "atr_pct_100",
    "session_london",
    "session_ny",
]


def month_cyclical(month: pd.Series) -> tuple[pd.Series, pd.Series]:
    ang = 2.0 * np.pi * (month.astype(float) - 1.0) / 12.0
    return np.sin(ang), np.cos(ang)


def build_entry_frame(baskets: pd.DataFrame, labels: pd.DataFrame | None = None) -> pd.DataFrame:
    g = enrich_baskets(baskets.sort_values("open_time").copy())
    g["open_time"] = pd.to_datetime(g["open_time"])
    g["month"] = g["open_time"].dt.month
    g["month_sin"], g["month_cos"] = month_cyclical(g["month"])
    g["atr_pips"] = g["entry_atr"] * 10_000.0
    atr_med = g["entry_atr"].shift(1).rolling(100, min_periods=10).median()
    g["atr_pct_100"] = np.where(atr_med > 0, g["entry_atr"] / atr_med, np.nan)
    g["session_london"] = (g["session"] == "London").astype(int)
    g["session_ny"] = (g["session"] == "NY").astype(int)

    if labels is not None and not labels.empty:
        lab = labels.loc[labels["window"] == WINDOW]
        score_map = lab.set_index(lab["basket_key"].astype(str))["oscillation_score_open"]
        chop_map = lab.set_index(lab["basket_key"].astype(str))["direction_chop_20"]
        g["oscillation_score_open"] = g["basket_key"].astype(str).map(score_map)
        g["direction_chop_20"] = g["basket_key"].astype(str).map(chop_map)
    else:
        g["oscillation_score_open"] = np.nan
        g["direction_chop_20"] = np.nan

    buy = (g["bias"].str.upper() == "BUY").astype(float)
    g["direction_chop_20"] = g["direction_chop_20"].fillna(
        buy.shift(1).rolling(20, min_periods=5).apply(
            lambda x: np.sum(x[1:] != x[:-1]) / max(len(x) - 1, 1) if len(x) > 1 else 0.5,
            raw=True,
        )
    )

    g["in_bleed_month"] = g["month"].isin(BLEED_MONTHS)
    g["is_2024_h1"] = (g["open_time"] >= "2024-01-01") & (g["open_time"] < "2024-07-01")
    g["is_apr_jul_2024"] = (g["open_time"] >= "2024-04-01") & (g["open_time"] < "2024-08-01")
    g["label_pocket_loss"] = (
        g["in_bleed_month"] & (g["basket_pnl"].astype(float) < -5.0)
    ).astype(int)
    return g


def autopsy_monthly(baskets: pd.DataFrame, legs: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    b = baskets.copy()
    b["ym"] = b["open_time"].dt.to_period("M").astype(str)
    l = legs.copy()
    l["open_time"] = pd.to_datetime(l["open_time"])
    l["ym"] = l["open_time"].dt.to_period("M").astype(str)

    for ym, grp in b.groupby("ym", sort=True):
        leg_grp = l.loc[l["ym"] == ym]
        tp = leg_grp.loc[leg_grp["exit_reason"] == "TP"]
        sl = leg_grp.loc[leg_grp["exit_reason"] == "SL"]
        rows.append(
            {
                "month": ym,
                "baskets": int(len(grp)),
                "basket_net": round(float(grp["basket_pnl"].sum()), 2),
                "basket_wr_pct": round(100.0 * float(grp["basket_won"].mean()), 1),
                "legs": int(len(leg_grp)),
                "leg_tp_pct": round(100.0 * len(tp) / len(leg_grp), 1) if len(leg_grp) else 0.0,
                "leg_sl_pct": round(100.0 * len(sl) / len(leg_grp), 1) if len(leg_grp) else 0.0,
                "entry_adx_mean": round(float(grp["entry_adx"].mean()), 1),
                "entry_atr_pips": round(float(grp["entry_atr"].mean()) * 10000, 2),
                "d2_plus_pct": round(100.0 * float((grp["max_level"] >= 2).mean()), 1),
            }
        )
    return rows


def train_pocket_model(df: pd.DataFrame) -> tuple[Pipeline, dict]:
    train = df.loc[df["open_time"] < "2024-01-01"].copy()
    X = train[POCKET_FEATURES].astype(float)
    y = train["label_pocket_loss"].astype(int)
    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "clf",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=2000,
                    C=0.5,
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(X, y)
    proba = model.predict_proba(X)[:, 1]
    auc = roc_auc_score(y, proba) if y.nunique() > 1 else float("nan")
    ap = average_precision_score(y, proba) if y.nunique() > 1 else float("nan")

    h1 = df.loc[df["is_2024_h1"]].copy()
    if len(h1):
        h1_proba = model.predict_proba(h1[POCKET_FEATURES].astype(float))[:, 1]
        h1_auc = (
            roc_auc_score(h1["label_pocket_loss"], h1_proba)
            if h1["label_pocket_loss"].nunique() > 1
            else float("nan")
        )
    else:
        h1_auc = float("nan")

    return model, {
        "n_train": int(len(train)),
        "pos_rate": round(float(y.mean()), 3),
        "train_auc": round(float(auc), 3),
        "train_ap": round(float(ap), 3),
        "h1_auc": round(float(h1_auc), 3) if h1_auc == h1_auc else None,
    }


def pocket_probs(model: Pipeline, df: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(df[POCKET_FEATURES].astype(float))[:, 1]


def simulate_entry_policy(
    legs: pd.DataFrame,
    frame: pd.DataFrame,
    *,
    cfg: dict,
    pocket_prob: np.ndarray | None = None,
    pocket_threshold: float | None = None,
    max_levels_cap: int = 2,
    spacing_mult: float | None = None,
    rule_apr_jul_2024: bool = False,
    rule_bleed_month: bool = False,
    physics_gate_fn: Callable | None = None,
) -> pd.DataFrame:
    kw_base = replay_kwargs({}, cfg)
    rows = []
    for i, (_, brow) in enumerate(frame.iterrows()):
        bk = str(brow["basket_key"])
        grp = legs.loc[legs["basket_key"] == bk]
        if grp.empty:
            continue

        apply_policy = False
        if rule_apr_jul_2024:
            apply_policy = bool(brow.get("is_apr_jul_2024"))
        elif rule_bleed_month:
            apply_policy = bool(brow.get("in_bleed_month"))
        elif pocket_prob is not None and pocket_threshold is not None:
            apply_policy = float(pocket_prob[i]) >= pocket_threshold

        kw = dict(kw_base)
        if apply_policy:
            if max_levels_cap:
                kw["max_grid_levels"] = max_levels_cap
            if spacing_mult is not None:
                kw["spacing_mult"] = spacing_mult
                kw["spacing_min_gap_sec"] = 180.0

        leg_dicts = []
        for _, r in grp.sort_values(["level", "open_time"]).iterrows():
            d = r.to_dict()
            d["basket_key"] = bk
            d["open_time"] = pd.to_datetime(d["open_time"])
            d["close_time"] = pd.to_datetime(d["close_time"])
            leg_dicts.append(d)

        result = replay_basket(
            pd.DataFrame(leg_dicts),
            l0_sl_gate_fn=physics_gate_fn,
            **kw,
        )
        rows.append(
            {
                "basket_key": bk,
                "open_time": brow["open_time"],
                "baseline_pnl": float(brow["basket_pnl"]),
                "sim_pnl": float(result.sim_pnl),
                "pocket_applied": apply_policy,
                "intervention": result.intervention,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time")


def evaluate_policy(sim: pd.DataFrame, w02_baseline_net: float, gates: dict) -> dict:
    exp = expectancy_block(sim["sim_pnl"])
    h1 = sim[(sim["open_time"] >= "2024-01-01") & (sim["open_time"] < "2024-07-01")]
    h1_net = float(h1["sim_pnl"].sum()) if len(h1) else 0.0
    h1_base = float(h1["baseline_pnl"].sum()) if len(h1) else 0.0
    w02 = sim[sim["open_time"] >= "2025-01-01"]
    w02_net = float(w02["sim_pnl"].sum()) if len(w02) else 0.0
    w02_base_sum = float(w02["baseline_pnl"].sum()) if len(w02) else w02_baseline_net
    reg_pct = (
        100.0 * (w02_net - w02_base_sum) / max(abs(w02_base_sum), 1.0)
        if w02_base_sum != 0
        else 0.0
    )
    applied_pct = round(100.0 * float(sim["pocket_applied"].mean()), 1) if len(sim) else 0.0
    return {
        "expectancy": exp,
        "net_delta": round(float(sim["sim_pnl"].sum() - sim["baseline_pnl"].sum()), 2),
        "h1_net": round(h1_net, 2),
        "h1_baseline_net": round(h1_base, 2),
        "h1_delta": round(h1_net - h1_base, 2),
        "w02_net": round(w02_net, 2),
        "w02_regression_pct": round(reg_pct, 2),
        "pocket_applied_pct": applied_pct,
    }


def gate_pass(metrics: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons = []
    if metrics["h1_net"] < gates["h1_net_min"]:
        reasons.append(f"h1_net ${metrics['h1_net']:.0f} < ${gates['h1_net_min']:.0f}")
    if metrics["w02_regression_pct"] < -100.0 * gates["w02_regression_max_pct"]:
        reasons.append(f"w02_regression {metrics['w02_regression_pct']:.1f}%")
    return len(reasons) == 0, reasons


def sweep_policies(
    legs: pd.DataFrame,
    frame: pd.DataFrame,
    model: Pipeline,
    cfg: dict,
    physics_gate_fn: Callable | None,
) -> list[dict]:
    probs = pocket_probs(model, frame)
    frame = frame.reset_index(drop=True)
    w02_base = float(
        frame.loc[frame["open_time"] >= "2025-01-01", "basket_pnl"].sum()
    )
    gates = cfg.get("e10f_gates", {})

    candidates: list[dict[str, Any]] = [
        {"name": "rule_apr_jul_cap2", "rule_apr_jul_2024": True, "max_levels_cap": 2},
        {"name": "rule_bleed_month_cap2", "rule_bleed_month": True, "max_levels_cap": 2},
    ]
    for thr in (0.35, 0.45, 0.55, 0.65):
        candidates.append(
            {
                "name": f"pocket_cap2_p{int(thr*100)}",
                "pocket_threshold": thr,
                "max_levels_cap": 2,
            }
        )
        candidates.append(
            {
                "name": f"pocket_cap2_phys_p{int(thr*100)}",
                "pocket_threshold": thr,
                "max_levels_cap": 2,
                "physics_gate_fn": physics_gate_fn,
            }
        )

    results = []
    for spec in candidates:
        name = spec.pop("name")
        sim = simulate_entry_policy(
            legs,
            frame,
            cfg=cfg,
            pocket_prob=probs if "pocket_threshold" in spec else None,
            pocket_threshold=spec.get("pocket_threshold"),
            max_levels_cap=spec.get("max_levels_cap", 2),
            spacing_mult=spec.get("spacing_mult"),
            rule_apr_jul_2024=spec.get("rule_apr_jul_2024", False),
            rule_bleed_month=spec.get("rule_bleed_month", False),
            physics_gate_fn=spec.get("physics_gate_fn"),
        )
        metrics = evaluate_policy(sim, w02_base, gates)
        passed, fail = gate_pass(metrics, gates)
        results.append(
            {
                "policy": name,
                "params": {k: v for k, v in spec.items() if k != "physics_gate_fn"},
                "metrics": metrics,
                "gate_pass": passed,
                "gate_fail": fail,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="E10f 2024 H1 pocket model")
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10f_report.json",
    )
    parser.add_argument(
        "--model-out",
        type=Path,
        default=ROOT / "models" / "pocket_risk_v0.joblib",
    )
    args = parser.parse_args()
    cfg = load_config()

    baskets = load_baskets(BASKETS_PATH, WINDOW, args.export_dir)
    legs = load_window_legs(args.export_dir, WINDOW)
    labels = pd.read_parquet(LABELS_PATH) if LABELS_PATH.is_file() else None

    print("[E10f] 2024 H1 pocket model")
    print("-" * 72)

    # E10f-001 autopsy
    monthly = autopsy_monthly(baskets, legs)
    h1_months = [m for m in monthly if m["month"].startswith("2024") and m["month"] < "2024-07"]
    print("[E10f-001] Monthly autopsy (2024 H1):")
    for m in h1_months:
        print(
            f"  {m['month']}  net=${m['basket_net']:7.1f}  WR={m['basket_wr_pct']:.0f}%  "
            f"leg TP={m['leg_tp_pct']:.0f}% SL={m['leg_sl_pct']:.0f}%  "
            f"ADX={m['entry_adx_mean']:.1f}  D2+={m['d2_plus_pct']:.0f}%"
        )

    frame = build_entry_frame(baskets, labels)
    h1 = frame.loc[frame["is_2024_h1"]]
    print(
        f"\n  2024 H1 total: n={len(h1)} net=${h1['basket_pnl'].sum():.1f} "
        f"WR={100*h1['basket_won'].mean():.1f}%  gate target >= -$20"
    )

    # E10f-002 train
    model, train_report = train_pocket_model(frame)
    print(
        f"\n[E10f-002] Train pre-2024: n={train_report['n_train']}  "
        f"AUC={train_report['train_auc']}  H1 holdout AUC={train_report['h1_auc']}"
    )

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.model_out)

    # Physics gate for combo policies
    stack_path = ROOT / "models" / "stack_risk_v0.joblib"
    physics_gate_fn = None
    if stack_path.is_file():
        stack_model = joblib.load(stack_path)
        meta = meta_lookup_for_windows(args.export_dir, WINDOW)
        physics_gate_fn = make_model_gate(stack_model, 0.45, meta)

    # E10f-003 policy sweep
    policies = sweep_policies(legs, frame, model, cfg, physics_gate_fn)
    print("\n[E10f-003] Policy sweep (w03):")
    for p in sorted(policies, key=lambda x: (-x["gate_pass"], -x["metrics"]["h1_net"])):
        m = p["metrics"]
        mark = "PASS" if p["gate_pass"] else "FAIL"
        print(
            f"  {p['policy']:28s} H1=${m['h1_net']:7.1f} (d{m['h1_delta']:+.0f})  "
            f"w02=${m['w02_net']:.0f}  applied={m['pocket_applied_pct']:.0f}%  {mark}"
        )

    best = max(policies, key=lambda p: (p["gate_pass"], p["metrics"]["h1_net"]))
    baseline_h1 = float(h1["basket_pnl"].sum())

    report = {
        "e10f": "pocket_model",
        "tasks": {
            "E10f-001": {"monthly_autopsy": monthly, "h1_summary": {
                "baskets": int(len(h1)),
                "net": round(baseline_h1, 2),
                "wr_pct": round(100.0 * float(h1["basket_won"].mean()), 1),
            }},
            "E10f-002": train_report,
            "E10f-003": policies,
        },
        "gates": cfg.get("e10f_gates", {}),
        "best_policy": best["policy"],
        "best_gate_pass": best["gate_pass"],
        "model_path": str(args.model_out),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print("\n" + "=" * 72)
    print(
        f"[E10f] best: {best['policy']}  H1=${best['metrics']['h1_net']:.0f}  "
        f"gate={'PASS' if best['gate_pass'] else 'FAIL'}"
    )
    print(f"  report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
