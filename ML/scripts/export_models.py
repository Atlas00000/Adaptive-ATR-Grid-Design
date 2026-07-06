#!/usr/bin/env python3
"""AI-808: Export all models to MQL5 + ONNX + bundle manifest + registry."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from export_mql_constants import (
    export_entry_lr,
    export_health_lr,
    export_regime_lr,
    try_export_onnx,
)

INCLUDE = ROOT.parent / "Include"
MODELS = ROOT / "models"
ONNX_OUT = ROOT / "models" / "onnx"

BUNDLES: dict[str, dict] = {
    "LOCK-AI": {
        "preset_versions": ["LOCK-AI", "20260706_808"],
        "health": ("basket_health_v0.joblib", "AI-805_v0"),
        "entry": None,
        "regime": None,
        "promoted": True,
        "notes": "803 memory + 805p health — canonical AI stack",
    },
    "LOCK-AI+804": {
        "preset_versions": ["LOCK-AI+804"],
        "health": ("basket_health_v0.joblib", "AI-805_v0"),
        "entry": ("entry_context_v0.joblib", "AI-804_v0"),
        "regime": None,
        "promoted": False,
        "notes": "804 deferred — entry layer optional",
    },
}


def write_bundle_mqh(bundle_id: str, runtime_version: str, export_date: str) -> Path:
    out = INCLUDE / "AIModelBundle.mqh"
    text = f"""//+------------------------------------------------------------------+
//| AIModelBundle.mqh — AI-808 bundle manifest (auto-generated)       |
//+------------------------------------------------------------------+
#ifndef AAG_AIMODELBUNDLE_MQH
#define AAG_AIMODELBUNDLE_MQH

#include "Utils.mqh"
#include "AIHealthModel.mqh"
#include "AIEntryContextModel.mqh"
#include "AIRegimeModel.mqh"

#define AI_BUNDLE_RUNTIME_VERSION   "{runtime_version}"
#define AI_BUNDLE_LOCK_AI           "LOCK-AI"
#define AI_BUNDLE_LOCK_AI_804       "LOCK-AI+804"
#define AI_BUNDLE_EXPORT_DATE       "{export_date}"
#define AI_BUNDLE_PRIMARY_ID        "{bundle_id}"

#define AI_BUNDLE_HEALTH_VERSION    AI_HEALTH_MODEL_VERSION
#define AI_BUNDLE_ENTRY_VERSION     AI_ENTRY_MODEL_VERSION
#define AI_BUNDLE_REGIME_VERSION    AI_REGIME_MODEL_VERSION

bool AIModelVersionAccepted(const string preset_version)
  {{
   if(preset_version == "" || preset_version == "AI-800")
      return true;
   if(preset_version == AI_BUNDLE_LOCK_AI)
      return true;
   if(preset_version == AI_BUNDLE_LOCK_AI_804)
      return true;
   if(preset_version == AI_BUNDLE_RUNTIME_VERSION)
      return true;
   if(preset_version == AI_HEALTH_MODEL_VERSION)
      return true;
   if(preset_version == AI_ENTRY_MODEL_VERSION)
      return true;
   if(preset_version == AI_REGIME_MODEL_VERSION)
      return true;
   return false;
  }}

bool AIModelBundleMatchesToggles(const string preset_version, string &detail)
  {{
   detail = "";
   if(preset_version == "" || preset_version == "AI-800")
      return true;

   if(preset_version == AI_BUNDLE_LOCK_AI || preset_version == AI_BUNDLE_RUNTIME_VERSION)
     {{
      if(InpAIEntryContextEnabled)
        {{
         detail = "LOCK-AI expects InpAIEntryContextEnabled=false";
         return false;
        }}
      if(InpAIRegimeEnabled)
        {{
         detail = "LOCK-AI expects InpAIRegimeEnabled=false";
         return false;
        }}
      return true;
     }}

   if(preset_version == AI_BUNDLE_LOCK_AI_804)
     {{
      if(!InpAIEntryContextEnabled)
        {{
         detail = "LOCK-AI+804 expects InpAIEntryContextEnabled=true";
         return false;
        }}
      return true;
     }}

   return true;
  }}

#endif // AAG_AIMODELBUNDLE_MQH
"""
    out.write_text(text, encoding="utf-8")
    return out


def export_model_pair(joblib_name: str, version: str, mql_name: str, model_type: str) -> dict:
    model_path = MODELS / joblib_name
    mql_path = INCLUDE / mql_name
    entry = {
        "id": joblib_name.replace(".joblib", ""),
        "version": version,
        "path": f"models/{joblib_name}",
        "mql": f"Include/{mql_name}",
        "type": model_type,
        "exported": False,
        "onnx": None,
    }
    if not model_path.is_file():
        entry["status"] = "missing_joblib"
        return entry

    if model_type == "health":
        export_health_lr(model_path, mql_path, version)
    elif model_type == "entry":
        export_entry_lr(model_path, mql_path, version)
    elif model_type == "regime":
        export_regime_lr(model_path, mql_path, version)

    entry["exported"] = True
    entry["status"] = "embedded_lr"

    onnx_name = joblib_name.replace(".joblib", ".onnx")
    onnx_path = try_export_onnx(model_path, ONNX_OUT / onnx_name)
    if onnx_path:
        entry["onnx"] = f"models/onnx/{onnx_name}"
        entry["status"] = "embedded_lr+onnx"
    return entry


def update_registry(bundle_id: str, model_entries: list[dict]) -> Path:
    registry_path = MODELS / "registry.json"
    promoted = BUNDLES[bundle_id].get("promoted", False)
    data = {
        "bundle": bundle_id,
        "runtime_version": BUNDLES[bundle_id]["preset_versions"][-1],
        "models": model_entries,
        "promoted": bundle_id if promoted else None,
        "updated": date.today().isoformat(),
    }
    registry_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return registry_path


def main() -> int:
    parser = argparse.ArgumentParser(description="AI-808 export all models + bundle")
    parser.add_argument("--bundle", default="LOCK-AI", choices=list(BUNDLES.keys()))
    parser.add_argument(
        "--runtime-version",
        default=None,
        help="Override AI_BUNDLE_RUNTIME_VERSION (default: YYYYMMDD_808)",
    )
    args = parser.parse_args()

    load_config()
    bundle = BUNDLES[args.bundle]
    export_date = date.today().strftime("%Y%m%d")
    runtime_version = args.runtime_version or f"{export_date}_808"

    print(f"[AI-808] export_models — bundle={args.bundle} runtime={runtime_version}")

    model_entries: list[dict] = []
    specs = [
        ("health", bundle.get("health"), "AIHealthModel.mqh", "health"),
        ("entry", bundle.get("entry"), "AIEntryContextModel.mqh", "entry"),
        ("regime", bundle.get("regime"), "AIRegimeModel.mqh", "regime"),
    ]
    for label, spec, mql_name, model_type in specs:
        if spec is None:
            print(f"  {label}: skipped (not in bundle)")
            continue
        joblib_name, version = spec
        entry = export_model_pair(joblib_name, version, mql_name, model_type)
        model_entries.append(entry)
        print(f"  {label}: {entry['status']} -> {mql_name}")

    bundle_path = write_bundle_mqh(args.bundle, runtime_version, export_date)
    registry_path = update_registry(args.bundle, model_entries)

    print(f"  bundle mqh: {bundle_path}")
    print(f"  registry:   {registry_path}")
    print(f"  onnx dir:   {ONNX_OUT} (copy to Terminal/Common/Files/AI/ for live ONNX)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
