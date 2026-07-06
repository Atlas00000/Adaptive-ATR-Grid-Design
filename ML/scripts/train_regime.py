#!/usr/bin/env python3
"""AI-806: Train regime / bad-basket skip classifier with walk-forward evaluation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from build_features import assign_walk_forward
from label_basket_opens import REGIME_FEATURES

LABEL_COL = "label_bad_basket"


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


def eval_fold(
    train: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    skip_prob: float,
) -> dict:
    X_train = train[features].astype(float)
    y_train = train[LABEL_COL].astype(int)
    X_test = test[features].astype(float)
    y_test = test[LABEL_COL].astype(int)

    model = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "clf",
                HistGradientBoostingClassifier(
                    max_depth=3,
                    max_iter=120,
                    learning_rate=0.08,
                    min_samples_leaf=8,
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]

    skip = proba >= skip_prob
    kept = test.loc[~skip]
    skipped = test.loc[skip]

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
        "skip_rate": float(skip.mean()),
        "skipped_bad_rate": float(skipped[LABEL_COL].mean()) if len(skipped) else 0.0,
        "kept_net": float(kept["basket_pnl"].sum()) if len(kept) else 0.0,
        "baseline_net": float(test["basket_pnl"].sum()),
        "kept_n": int(len(kept)),
        "calibration": calibration_bins(y_test.values, proba),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train regime skip classifier")
    parser.add_argument(
        "--features",
        type=Path,
        default=ROOT / "features" / "basket_opens.parquet",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "regime_v0.joblib")
    parser.add_argument("--meta", type=Path, default=ROOT / "models" / "regime_v0.json")
    parser.add_argument(
        "--train-window",
        default="AI806_805p",
        help="Window used for final model fit (805p = tail-safe labels)",
    )
    args = parser.parse_args()

    cfg = load_config()
    skip_prob = cfg["thresholds"]["regime_trend_skip_prob"]

    df = pd.read_parquet(args.features)
    df["open_time"] = pd.to_datetime(df["open_time"])

    feature_cols = [c for c in REGIME_FEATURES if c in df.columns]
    missing = [c for c in REGIME_FEATURES if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing feature columns: {missing}")

    df = df.fillna({c: 0.0 for c in feature_cols})

    train_m = cfg["walk_forward"]["train_months"]
    test_m = cfg["walk_forward"]["test_months"]
    wf_source = df[df["window"] == args.train_window].copy()
    if wf_source.empty:
        wf_source = df.copy()
    wf = assign_walk_forward(wf_source, train_m, test_m)
    wf = wf[wf["wf_fold"] >= 0].copy()

    print(f"[AI-806] train_regime — label={LABEL_COL} skip_prob={skip_prob}")
    print(f"  rows: {len(df)} | wf rows: {len(wf)} | features: {len(feature_cols)}")

    fold_results: list[dict] = []
    last_model = None
    for fold, grp in wf.groupby("wf_fold", sort=True):
        train = grp[grp["wf_split"] == "train"]
        test = grp[grp["wf_split"] == "test"]
        if train.empty or test.empty:
            continue
        res = eval_fold(train, test, feature_cols, skip_prob)
        last_model = res.pop("model")
        res["fold"] = int(fold)
        fold_results.append(res)
        print(
            f"  fold {fold}: test={res['n_test']:3d} AUC={res['auc']:.3f} "
            f"skip={100*res['skip_rate']:4.1f}% kept_net=${res['kept_net']:7.1f} "
            f"(base ${res['baseline_net']:7.1f})"
        )

    train_all = df[df["window"] == args.train_window].copy()
    if train_all.empty:
        train_all = df.copy()

    final = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "clf",
                HistGradientBoostingClassifier(
                    max_depth=3,
                    max_iter=120,
                    learning_rate=0.08,
                    min_samples_leaf=8,
                    random_state=42,
                ),
            ),
        ]
    )
    y = train_all[LABEL_COL].astype(int)
    final.fit(train_all[feature_cols].astype(float), y)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, args.out)

    lr_model = Pipeline(
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
    lr_model.fit(train_all[feature_cols].astype(float), y)
    lr_path = args.out.with_name("regime_v0_lr.joblib")
    joblib.dump(lr_model, lr_path)

    meta = {
        "model_id": cfg["models"]["regime"],
        "label": LABEL_COL,
        "features": feature_cols,
        "skip_prob_threshold": skip_prob,
        "train_window": args.train_window,
        "train_rows": int(len(train_all)),
        "positive_rate": float(y.mean()),
        "walk_forward": fold_results,
        "calibration_pooled": (
            calibration_bins(
                wf[wf["wf_split"] == "test"][LABEL_COL].astype(int).values,
                final.predict_proba(
                    wf[wf["wf_split"] == "test"][feature_cols].astype(float)
                )[:, 1],
            )
            if len(wf[wf["wf_split"] == "test"])
            else []
        ),
    }
    args.meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if fold_results:
        avg_skip = np.mean([r["skip_rate"] for r in fold_results])
        avg_auc = np.nanmean([r["auc"] for r in fold_results])
        print(f"\n  WF mean AUC={avg_auc:.3f} skip={100*avg_skip:.1f}%")
        if avg_skip > 0.15:
            print("  WARN  skip rate > 15% target — tune threshold offline")

    print(f"  model: {args.out}")
    print(f"  lr:    {lr_path}")
    print(f"  meta:  {args.meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
