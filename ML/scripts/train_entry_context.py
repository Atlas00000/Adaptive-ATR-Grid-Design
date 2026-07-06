#!/usr/bin/env python3
"""AI-804: Train entry context win-probability model (logistic regression for MT5 wire)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from build_features import ENTRY_SAFE_FEATURES, assign_walk_forward

ENTRY_CONTEXT_FEATURES = [
    c
    for c in ENTRY_SAFE_FEATURES
    if c not in ("minute", "rsi", "ema_slope", "spread_pips")
]

LABEL_COL = "label_basket_won"


def calibration_bins(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 5) -> list[dict]:
    order = np.argsort(proba)
    y = y_true[order]
    p = proba[order]
    chunks = np.array_split(np.arange(len(p)), n_bins)
    rows: list[dict] = []
    for idx in chunks:
        if len(idx) == 0:
            continue
        rows.append(
            {
                "n": int(len(idx)),
                "mean_pred": float(p[idx].mean()),
                "actual_rate": float(y[idx].mean()),
            }
        )
    return rows


def eval_fold(train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict:
    X_train = train[features].astype(float)
    y_train = train[LABEL_COL].astype(int)
    X_test = test[features].astype(float)
    y_test = test[LABEL_COL].astype(int)

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
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, proba) if y_test.nunique() > 1 else float("nan")
    ap = average_precision_score(y_test, proba) if y_test.nunique() > 1 else float("nan")
    brier = brier_score_loss(y_test, proba) if len(y_test) else float("nan")

    return {
        "model": model,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "auc": float(auc),
        "ap": float(ap),
        "brier": float(brier),
        "test_wr": float(y_test.mean()),
        "calibration": calibration_bins(y_test.values, proba),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train entry context scorer")
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "features" / "train_entry.parquet",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "entry_context_v0.joblib")
    parser.add_argument("--meta", type=Path, default=ROOT / "models" / "entry_context_v0.json")
    parser.add_argument(
        "--train-window",
        default="w02_ext19mo",
        help="Window used for final LR fit (805p labels: AI806_805p)",
    )
    parser.add_argument(
        "--wf-window",
        default=None,
        help="Walk-forward source window (default: same as --train-window)",
    )
    args = parser.parse_args()

    cfg = load_config()
    wf_window = args.wf_window or args.train_window

    df = pd.read_parquet(args.features)
    df["open_time"] = pd.to_datetime(df["open_time"])

    feature_cols = [c for c in ENTRY_CONTEXT_FEATURES if c in df.columns]
    missing = [c for c in ENTRY_CONTEXT_FEATURES if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing feature columns: {missing}")

    df = df.fillna({c: 0.0 for c in feature_cols})

    train_m = cfg["walk_forward"]["train_months"]
    test_m = cfg["walk_forward"]["test_months"]
    wf_source = df[df["window"] == wf_window].copy()
    if wf_source.empty:
        wf_source = df.copy()
    wf = assign_walk_forward(wf_source, train_m, test_m)
    wf = wf[wf["wf_fold"] >= 0].copy()

    print(f"[AI-804] train_entry_context — label={LABEL_COL}")
    print(f"  rows: {len(df)} | wf rows: {len(wf)} | features: {len(feature_cols)}")

    fold_results: list[dict] = []
    for fold, grp in wf.groupby("wf_fold", sort=True):
        train = grp[grp["wf_split"] == "train"]
        test = grp[grp["wf_split"] == "test"]
        if train.empty or test.empty:
            continue
        res = eval_fold(train, test, feature_cols)
        res.pop("model")
        res["fold"] = int(fold)
        fold_results.append(res)
        print(
            f"  fold {fold}: test={res['n_test']:3d} AUC={res['auc']:.3f} "
            f"Brier={res['brier']:.3f} WR={100*res['test_wr']:.1f}%"
        )

    train_all = df[df["window"] == args.train_window].copy()
    if train_all.empty:
        train_all = df.copy()

    final = Pipeline(
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
    y = train_all[LABEL_COL].astype(int)
    final.fit(train_all[feature_cols].astype(float), y)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, args.out)

    meta = {
        "model_id": cfg["models"]["entry_context"],
        "label": LABEL_COL,
        "features": feature_cols,
        "train_window": args.train_window,
        "wf_window": wf_window,
        "train_rows": int(len(train_all)),
        "positive_rate": float(y.mean()),
        "walk_forward": fold_results,
    }
    args.meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if fold_results:
        avg_auc = np.nanmean([r["auc"] for r in fold_results])
        avg_brier = np.nanmean([r["brier"] for r in fold_results])
        print(f"\n  WF mean AUC={avg_auc:.3f} Brier={avg_brier:.3f}")

    print(f"  model: {args.out}")
    print(f"  meta:  {args.meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
