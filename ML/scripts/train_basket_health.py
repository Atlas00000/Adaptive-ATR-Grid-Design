#!/usr/bin/env python3
"""AI-805: Train basket health / tail-loss classifier."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config

HEALTH_FEATURES = [
    "grid_depth",
    "floating_pl",
    "seconds_open",
    "atr_delta",
    "adx_delta",
    "dist_anchor_atr",
    "mfe_so_far",
    "mae_so_far",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train basket health model")
    parser.add_argument("--features", type=Path, default=ROOT / "features" / "train.parquet")
    parser.add_argument("--out", type=Path, default=ROOT / "models" / "basket_health_v0.joblib")
    parser.add_argument("--meta", type=Path, default=ROOT / "models" / "basket_health_v0.json")
    args = parser.parse_args()

    cfg = load_config()
    df = pd.read_parquet(args.features)
    df = df[df["window"].isin(["w02_ext19mo", "w03_longest"])].copy()

    for col in HEALTH_FEATURES:
        if col not in df.columns:
            raise SystemExit(f"Missing feature column: {col}")

    df = df[df["max_level"] >= 2].copy()
    if df.empty:
        raise SystemExit("No D2+ baskets for health training")

    atr = df["entry_atr"].astype(float).replace(0, np.nan)
    # Features approximating live state at L1 add decision (no close leakage)
    df["grid_depth"] = 1.0
    df["floating_pl"] = np.minimum(0.0, df["worst_leg"].astype(float))
    df["seconds_open"] = df["hold_sec"].astype(float) * 0.35
    df["atr_delta"] = 0.0
    df["adx_delta"] = 0.0
    df["dist_anchor_atr"] = (df["worst_leg"].abs() / atr).fillna(0.0)
    df["mfe_so_far"] = np.maximum(0.0, df["best_leg"].astype(float))
    df["mae_so_far"] = np.minimum(0.0, df["worst_leg"].astype(float))

    df = df.fillna(0.0)
    y = df["label_tail_loss"].astype(int)
    X = df[HEALTH_FEATURES].astype(float)

    model = Pipeline(
        [
            ("scaler", StandardScaler()),
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
    auc = roc_auc_score(y, proba) if y.nunique() > 1 else 0.0
    ap = average_precision_score(y, proba) if y.nunique() > 1 else 0.0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out)

    meta = {
        "model_id": cfg["models"]["basket_health"],
        "features": HEALTH_FEATURES,
        "auc_train": float(auc),
        "ap_train": float(ap),
        "positive_rate": float(y.mean()),
        "rows": int(len(df)),
        "thresholds": {
            "no_add": cfg["thresholds"]["health_no_add"],
            "flatten": cfg["thresholds"]["health_flatten"],
            "tighten": 72,
        },
    }
    args.meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"[AI-805] train_basket_health")
    print(f"  rows: {len(df)} | tail_loss: {y.mean():.1%}")
    print(f"  AUC: {auc:.3f} | AP: {ap:.3f}")
    print(f"  model: {args.out}")
    print(f"  meta:  {args.meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
