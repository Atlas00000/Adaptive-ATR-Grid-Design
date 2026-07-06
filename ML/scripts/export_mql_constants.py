#!/usr/bin/env python3
"""AI-808: Export trained model weights to MQL5 constants."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from build_features import ENTRY_SAFE_FEATURES
from label_basket_opens import REGIME_FEATURES

ENTRY_CONTEXT_FEATURES = [
    c
    for c in ENTRY_SAFE_FEATURES
    if c not in ("minute", "rsi", "ema_slope", "spread_pips")
]


def _mqh_name(feature: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", feature.upper())


def export_logistic_imputer(
    model_path: Path,
    out_path: Path,
    *,
    version: str,
    version_define: str,
    guard: str,
    title: str,
    features: list[str],
    prob_fn: str,
    feature_prefix: str,
    count_define: str,
) -> None:
    pipe = joblib.load(model_path)
    imputer = pipe.named_steps["imputer"]
    clf = pipe.named_steps["clf"]
    medians = imputer.statistics_
    coefs = clf.coef_[0]
    intercept = float(clf.intercept_[0])

    lines = [
        "//+------------------------------------------------------------------+",
        f"//| {title}",
        "//| Auto-generated — do not edit manually                             |",
        "//+------------------------------------------------------------------+",
        f"#ifndef {guard}",
        f"#define {guard}",
        "",
        f'#define {version_define} "{version}"',
        f"#define {count_define} {len(features)}",
        "",
    ]

    for i, name in enumerate(features):
        lines.append(f"#define {feature_prefix}_{_mqh_name(name)} {i}")

    lines.append("")
    lines.append(f"double {feature_prefix}ImputeMedian(const int idx)")
    lines.append("  {")
    lines.append("   static const double m[] = {")
    lines.append("      " + ", ".join(f"{v:.8f}" for v in medians))
    lines.append("   };")
    lines.append(f"   return (idx >= 0 && idx < {count_define}) ? m[idx] : 0.0;")
    lines.append("  }")
    lines.append("")
    lines.append(f"double {feature_prefix}Coef(const int idx)")
    lines.append("  {")
    lines.append("   static const double c[] = {")
    lines.append("      " + ", ".join(f"{v:.8f}" for v in coefs))
    lines.append("   };")
    lines.append(f"   return (idx >= 0 && idx < {count_define}) ? c[idx] : 0.0;")
    lines.append("  }")
    lines.append("")
    lines.append(f"double {feature_prefix}Intercept() {{ return {intercept:.8f}; }}")
    lines.append("")
    lines.append("#ifndef AISIGMOIDPROB_DEFINED")
    lines.append("#define AISIGMOIDPROB_DEFINED")
    lines.append("double AISigmoidProb(const double x)")
    lines.append("  {")
    lines.append("   if(x > 20.0)  return 1.0;")
    lines.append("   if(x < -20.0) return 0.0;")
    lines.append("   return 1.0 / (1.0 + MathExp(-x));")
    lines.append("  }")
    lines.append("#endif")
    lines.append("")
    lines.append(f"double {prob_fn}(const double &f[])")
    lines.append("  {")
    lines.append(f"   double logit = {feature_prefix}Intercept();")
    lines.append(f"   for(int i = 0; i < {count_define}; i++)")
    lines.append("     {")
    lines.append("      double v = f[i];")
    lines.append("      if(!MathIsValidNumber(v))")
    lines.append(f"         v = {feature_prefix}ImputeMedian(i);")
    lines.append(f"      logit += {feature_prefix}Coef(i) * v;")
    lines.append("     }")
    lines.append("   return AISigmoidProb(logit);")
    lines.append("  }")
    lines.append("")
    lines.append(f"#endif // {guard}")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def export_health_lr(model_path: Path, out_path: Path, version: str) -> None:
    pipe = joblib.load(model_path)
    scaler = pipe.named_steps["scaler"]
    clf = pipe.named_steps["clf"]
    features = [
        "grid_depth",
        "floating_pl",
        "seconds_open",
        "atr_delta",
        "adx_delta",
        "dist_anchor_atr",
        "mfe_so_far",
        "mae_so_far",
    ]

    means = scaler.mean_
    scales = scaler.scale_
    coefs = clf.coef_[0]
    intercept = float(clf.intercept_[0])

    lines = [
        "//+------------------------------------------------------------------+",
        "//| AIHealthModel.mqh — AI-805 exported logistic health scorer        |",
        "//| Auto-generated — do not edit manually                             |",
        "//+------------------------------------------------------------------+",
        "#ifndef AAG_AIHEALTHMODEL_MQH",
        "#define AAG_AIHEALTHMODEL_MQH",
        "",
        f'#define AI_HEALTH_MODEL_VERSION "{version}"',
        f"#define AI_HEALTH_FEATURE_COUNT {len(features)}",
        "",
    ]

    for i, name in enumerate(features):
        lines.append(f"#define AI_HEALTH_F_{name.upper()} {i}")

    lines.append("")
    lines.append("double AIHealthFeatureMean(const int idx)")
    lines.append("  {")
    lines.append("   static const double m[] = {")
    lines.append("      " + ", ".join(f"{v:.8f}" for v in means))
    lines.append("   };")
    lines.append("   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? m[idx] : 0.0;")
    lines.append("  }")
    lines.append("")
    lines.append("double AIHealthFeatureScale(const int idx)")
    lines.append("  {")
    lines.append("   static const double s[] = {")
    lines.append("      " + ", ".join(f"{v:.8f}" for v in scales))
    lines.append("   };")
    lines.append("   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? s[idx] : 0.0;")
    lines.append("  }")
    lines.append("")
    lines.append("double AIHealthCoef(const int idx)")
    lines.append("  {")
    lines.append("   static const double c[] = {")
    lines.append("      " + ", ".join(f"{v:.8f}" for v in coefs))
    lines.append("   };")
    lines.append("   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? c[idx] : 0.0;")
    lines.append("  }")
    lines.append("")
    lines.append(f"double AIHealthIntercept() {{ return {intercept:.8f}; }}")
    lines.append("")
    lines.append("double AIHealthSigmoid(const double x)")
    lines.append("  {")
    lines.append("   if(x > 20.0)  return 1.0;")
    lines.append("   if(x < -20.0) return 0.0;")
    lines.append("   return 1.0 / (1.0 + MathExp(-x));")
    lines.append("  }")
    lines.append("")
    lines.append("double AIHealthScoreFromFeatures(const double &f[])")
    lines.append("  {")
    lines.append("   double logit = AIHealthIntercept();")
    lines.append("   for(int i = 0; i < AI_HEALTH_FEATURE_COUNT; i++)")
    lines.append("     {")
    lines.append("      const double scale = AIHealthFeatureScale(i);")
    lines.append("      const double z = (scale > 0.0) ? (f[i] - AIHealthFeatureMean(i)) / scale : 0.0;")
    lines.append("      logit += AIHealthCoef(i) * z;")
    lines.append("     }")
    lines.append("   return 100.0 * AIHealthSigmoid(logit);")
    lines.append("  }")
    lines.append("")
    lines.append("#endif // AAG_AIHEALTHMODEL_MQH")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def export_regime_lr(model_path: Path, out_path: Path, version: str) -> None:
    export_logistic_imputer(
        model_path,
        out_path,
        version=version,
        version_define="AI_REGIME_MODEL_VERSION",
        guard="AAG_AIREGIMEMODEL_MQH",
        title="AIRegimeModel.mqh — AI-806 bad-basket skip scorer",
        features=REGIME_FEATURES,
        prob_fn="AIRegimeBadBasketProb",
        feature_prefix="AIRegime",
        count_define="AI_REGIME_FEATURE_COUNT",
    )


def try_export_onnx(model_path: Path, out_path: Path) -> Path | None:
    """Optional skl2onnx export for MT5 OnnxCreate path."""
    try:
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
    except ImportError:
        return None

    pipe = joblib.load(model_path)
    n_features = None
    if hasattr(pipe, "named_steps"):
        clf = pipe.named_steps.get("clf")
        if clf is not None and hasattr(clf, "coef_"):
            n_features = clf.coef_.shape[1]
    if n_features is None:
        return None

    initial_type = [("input", FloatTensorType([None, n_features]))]
    try:
        onnx_model = convert_sklearn(pipe, initial_types=initial_type, target_opset=12)
    except Exception:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    return out_path


def export_entry_lr(model_path: Path, out_path: Path, version: str) -> None:
    meta_path = model_path.with_suffix(".json")
    features = ENTRY_CONTEXT_FEATURES
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        features = meta.get("features", features)
    export_logistic_imputer(
        model_path,
        out_path,
        version=version,
        version_define="AI_ENTRY_MODEL_VERSION",
        guard="AAG_AIENTRYCONTEXTMODEL_MQH",
        title="AIEntryContextModel.mqh — AI-804 entry win scorer",
        features=features,
        prob_fn="AIEntryWinProb",
        feature_prefix="AIEntry",
        count_define="AI_ENTRY_FEATURE_COUNT",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export model for AISupervisor.mqh")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--type", choices=("health", "regime", "entry", "stack"), default="health")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
    )
    parser.add_argument("--version", default=None)
    args = parser.parse_args()

    load_config()
    if args.type == "regime":
        out = args.out or ROOT.parent / "Include" / "AIRegimeModel.mqh"
        version = args.version or "AI-806_v0"
        export_regime_lr(args.model, out, version)
        print(f"[AI-806] export_mql_constants")
    elif args.type == "entry":
        out = args.out or ROOT.parent / "Include" / "AIEntryContextModel.mqh"
        version = args.version or "AI-804_v0"
        export_entry_lr(args.model, out, version)
        print(f"[AI-804] export_mql_constants")
    elif args.type == "stack":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from e9d_physics_labels import PHYSICS_FEATURES

        out = args.out or ROOT.parent / "Include" / "AIStackRiskModel.mqh"
        version = args.version or "AI-809_v0"
        export_logistic_imputer(
            args.model,
            out,
            version=version,
            version_define="AI_STACK_RISK_MODEL_VERSION",
            guard="AAG_AISTACKRISKMODEL_MQH",
            title="AIStackRiskModel.mqh — AI-809 L0-SL stack-risk scorer",
            features=PHYSICS_FEATURES,
            prob_fn="AIStackRiskBlockProb",
            feature_prefix="AIStack",
            count_define="AI_STACK_RISK_FEATURE_COUNT",
        )
        print(f"[AI-809] export_mql_constants")
    else:
        out = args.out or ROOT.parent / "Include" / "AIHealthModel.mqh"
        version = args.version or "AI-805_v0"
        export_health_lr(args.model, out, version)
        print(f"[AI-805] export_mql_constants")

    print(f"  model: {args.model}")
    print(f"  out:   {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
