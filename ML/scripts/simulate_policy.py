#!/usr/bin/env python3
"""AI-803/810: Offline policy simulator — apply AI multipliers to basket history."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from basket_replay import (
    load_window_legs,
    simulate_health_legacy,
    simulate_health_replay,
)
from label_basket_opens import REGIME_FEATURES
from train_entry_context import ENTRY_CONTEXT_FEATURES

MEMORY_WINDOW = 20
MEMORY_MIN_BASKETS = 5
MEMORY_PF_FLOOR = 1.15
MEMORY_PF_RECOVERY = 1.50
MEMORY_WR_RECOVERY = 0.68
MEMORY_THROTTLE_MULT = 0.80
MEMORY_RECOVERY_STEP = 0.05
MEMORY_LOSS_MULT = 2.00
LOT_MULT_MIN = 0.65


def rolling_stats(history: list[float]) -> tuple[float, float, float]:
    if not history:
        return 1.0, 0.0, 0.0
    arr = np.array(history[-MEMORY_WINDOW:])
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else (99.0 if gross_win > 0 else 1.0)
    wr = float(len(wins)) / len(arr)
    max_loss = float(arr.min()) if len(arr) else 0.0
    return pf, wr, max_loss


def avg_loss(history: list[float]) -> float:
    losses = [abs(x) for x in history if x < 0]
    return float(np.mean(losses)) if losses else 0.0


def memory_lot_mult(
    history: list[float],
    risk_mult: float,
    lot_mult_min: float,
) -> tuple[float, bool]:
    if len(history) < MEMORY_MIN_BASKETS:
        return risk_mult, False

    pf, wr, max_loss = rolling_stats(history)
    hist_avg_loss = avg_loss(history)
    loss_spike = hist_avg_loss > 0 and abs(max_loss) > MEMORY_LOSS_MULT * hist_avg_loss
    throttle = pf < 1.0 or (loss_spike and pf < MEMORY_PF_FLOOR)

    if throttle:
        return max(lot_mult_min, MEMORY_THROTTLE_MULT), True
    if pf > MEMORY_PF_RECOVERY and wr > MEMORY_WR_RECOVERY:
        return min(1.0, risk_mult + MEMORY_RECOVERY_STEP), False
    return risk_mult, False


def equity_metrics(pnls: pd.Series, deposit: float = 200.0) -> dict:
    equity = deposit
    peak = deposit
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
    gross_win = float(pnls[pnls > 0].sum())
    gross_loss = float(abs(pnls[pnls < 0].sum()))
    pf = gross_win / gross_loss if gross_loss > 0 else 99.0
    return {
        "net": float(pnls.sum()),
        "pf": pf,
        "trades": int(len(pnls)),
        "max_dd_pct": max_dd,
        "final_equity": equity,
    }


def simulate_memory(df: pd.DataFrame, lot_mult_min: float) -> pd.DataFrame:
    out = df.sort_values("open_time").copy()
    history: list[float] = []
    risk_mult = 1.0
    sim_pnls = []
    mults = []
    throttled = []

    for _, row in out.iterrows():
        risk_mult, is_throttle = memory_lot_mult(history, risk_mult, lot_mult_min)
        sim_pnl = float(row["basket_pnl"]) * risk_mult
        sim_pnls.append(sim_pnl)
        mults.append(risk_mult)
        throttled.append(is_throttle)
        history.append(float(row["basket_pnl"]))

    out["sim_pnl"] = sim_pnls
    out["lot_mult"] = mults
    out["memory_throttled"] = throttled
    return out


def rule_health_score(row: pd.Series) -> float:
    """Legacy close-state score (hindsight features). Prefer basket_replay.rule_health_score."""
    floating = float(min(0.0, row.get("worst_leg", 0.0)))
    open_count = int(row.get("max_level", 1))
    seconds_open = float(row.get("hold_sec", 0))
    atr = float(row.get("entry_atr", 0.0001) or 0.0001)
    dist = float(abs(row.get("worst_leg", 0.0)) / atr)

    h = 0.0
    if floating < 0:
        h += min(45.0, abs(floating) * 3.0)
    if open_count >= 2:
        h += 20.0
    if open_count >= 1 and floating < -10.0:
        h += 15.0
    if seconds_open > 2400:
        h += 10.0
    if seconds_open > 5400:
        h += 15.0
    if dist > 1.25:
        h += min(25.0, (dist - 1.0) * 15.0)
    return min(100.0, h)


def resolve_export_window(subset: pd.DataFrame, window_arg: str) -> str:
    """Map baskets subset to diagnostics export window prefix."""
    if "window" in subset.columns and window_arg not in subset["window"].astype(str).unique():
        windows = subset["window"].dropna().astype(str).unique().tolist()
        if len(windows) == 1:
            return windows[0]
    if ":" not in window_arg:
        return window_arg
    # Date-range filter — use dominant window label from rows
    if "window" in subset.columns and not subset.empty:
        return str(subset["window"].mode().iloc[0])
    return "w02_ext19mo"


def simulate_health(
    df: pd.DataFrame,
    cfg: dict,
    *,
    export_dir: Path,
    window_arg: str,
    mode: str = "flatten_only",
    checkpoint_sec: int = 60,
    flatten_float: float = -18.0,
    stress_flatten_at: float = 75.0,
    hard_cap_enabled: bool = True,
    hard_cap_usd: float = -25.0,
    hard_cap_l1_enabled: bool = True,
    hard_cap_l1_usd: float = -35.0,
    hard_cap_l1_min_sec: float = 60.0,
    legacy: bool = False,
) -> pd.DataFrame:
    if legacy:
        return simulate_health_legacy(df, cfg)

    export_window = resolve_export_window(df, window_arg)
    legs = load_window_legs(export_dir, export_window)
    keys = set(df["basket_key"].astype(str))
    legs = legs.loc[legs["basket_key"].isin(keys)].copy()

    return simulate_health_replay(
        df,
        legs,
        mode=mode,  # type: ignore[arg-type]
        flatten_at=cfg["thresholds"]["health_flatten"],
        no_add_at=cfg["thresholds"]["health_no_add"],
        checkpoint_sec=checkpoint_sec,
        flatten_float=flatten_float,
        stress_flatten_at=stress_flatten_at,
        hard_cap_enabled=hard_cap_enabled,
        hard_cap_usd=hard_cap_usd,
        hard_cap_l1_enabled=hard_cap_l1_enabled,
        hard_cap_l1_usd=hard_cap_l1_usd,
        hard_cap_l1_min_sec=hard_cap_l1_min_sec,
    )


def intervention_summary(df: pd.DataFrame) -> dict:
    if "health_intervention" not in df.columns:
        return {}
    counts = df["health_intervention"].value_counts().to_dict()
    changed = df.loc[df["sim_pnl"] != df["basket_pnl"]]
    return {
        "intervention_counts": counts,
        "baskets_changed": int(len(changed)),
        "pnl_delta": float(changed["sim_pnl"].sum() - changed["basket_pnl"].sum()) if len(changed) else 0.0,
    }


def simulate_memory_805p(
    df: pd.DataFrame,
    cfg: dict,
    *,
    export_dir: Path,
    window_arg: str,
    lot_min: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """AI-803 lot throttle on top of 805p health replay outcomes."""
    base_805p = simulate_805p(df, cfg, export_dir=export_dir, window_arg=window_arg)
    mem_in = base_805p.copy()
    mem_in["basket_pnl"] = mem_in["sim_pnl"].astype(float)
    out = simulate_memory(mem_in, lot_min)
    return out, base_805p


def entry_context_mult(
    p_win: float,
    *,
    lot_min: float,
    lot_max: float,
    block_floor: float,
    block_conf: float,
) -> tuple[float, bool]:
    conf = max(p_win, 1.0 - p_win)
    if p_win < block_floor and conf >= block_conf:
        return 0.0, True
    return lot_min + (lot_max - lot_min) * p_win, False


def score_entry_context(
    df: pd.DataFrame,
    entry_feats: pd.DataFrame,
    model,
    feature_cols: list[str],
) -> pd.DataFrame:
    out = df.sort_values("open_time").copy()
    feat = entry_feats.set_index("basket_key")
    probs: list[float] = []
    for key in out["basket_key"].astype(str):
        if key not in feat.index:
            probs.append(0.5)
            continue
        row = feat.loc[key]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        x = pd.DataFrame([row[feature_cols].astype(float).fillna(0.0).values], columns=feature_cols)
        probs.append(float(model.predict_proba(x)[0, 1]))
    out["entry_p_win"] = probs
    return out


def apply_entry_context(
    df: pd.DataFrame,
    *,
    lot_min: float,
    lot_max: float,
    block_floor: float,
    block_conf: float,
    pnl_col: str = "sim_pnl",
) -> pd.DataFrame:
    out = df.copy()
    mults: list[float] = []
    blocked: list[bool] = []
    sim_pnls: list[float] = []
    for _, row in out.iterrows():
        p_win = float(row["entry_p_win"])
        mult, is_block = entry_context_mult(
            p_win,
            lot_min=lot_min,
            lot_max=lot_max,
            block_floor=block_floor,
            block_conf=block_conf,
        )
        mults.append(mult)
        blocked.append(is_block)
        base = float(row[pnl_col])
        sim_pnls.append(0.0 if is_block else base * mult)
    out["entry_lot_mult"] = mults
    out["entry_blocked"] = blocked
    out["sim_pnl"] = sim_pnls
    out["lot_mult"] = mults
    out["trade_taken"] = ~pd.Series(blocked)
    return out


def simulate_entry_lock_ai(
    df: pd.DataFrame,
    cfg: dict,
    *,
    export_dir: Path,
    window_arg: str,
    entry_feats: pd.DataFrame,
    model,
    feature_cols: list[str],
    lot_min: float,
    lot_max: float,
    block_floor: float,
    block_conf: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """LOCK-AI + AI-804: 805p replay → entry lot scale → memory throttle."""
    base_805p = simulate_805p(df, cfg, export_dir=export_dir, window_arg=window_arg)
    scored = score_entry_context(base_805p, entry_feats, model, feature_cols)
    entry_out = apply_entry_context(
        scored,
        lot_min=lot_min,
        lot_max=lot_max,
        block_floor=block_floor,
        block_conf=block_conf,
        pnl_col="sim_pnl",
    )
    mem_in = entry_out.copy()
    mem_in["basket_pnl"] = mem_in["sim_pnl"].astype(float)
    out = simulate_memory(mem_in, lot_min)
    if "entry_blocked" in entry_out.columns:
        out["trade_taken"] = (~entry_out["entry_blocked"]).astype(bool)
        out["entry_blocked"] = entry_out["entry_blocked"].values
    return out, base_805p


def parse_window_arg(window: str, df: pd.DataFrame) -> pd.DataFrame:
    if ":" in window and len(window.split(":")) == 2:
        start, end = window.split(":", 1)
        mask = (df["open_time"] >= pd.Timestamp(start)) & (
            df["open_time"] <= pd.Timestamp(end) + pd.Timedelta(days=1)
        )
        return df.loc[mask].copy()
    return df[df["window"] == window].copy()


def health_805p_kwargs(cfg: dict) -> dict:
    h = cfg.get("health_805p", {})
    return {
        "mode": h.get("mode", "flatten_only"),
        "checkpoint_sec": int(h.get("checkpoint_sec", 60)),
        "flatten_float": float(h.get("flatten_float_usd", -18.0)),
        "stress_flatten_at": float(h.get("stress_flatten_at", 75.0)),
        "hard_cap_enabled": bool(h.get("hard_cap_enabled", True)),
        "hard_cap_usd": float(h.get("hard_cap_usd", -25.0)),
        "hard_cap_l1_enabled": bool(h.get("hard_cap_l1_enabled", True)),
        "hard_cap_l1_usd": float(h.get("hard_cap_l1_usd", -28.0)),
        "hard_cap_l1_min_sec": float(h.get("hard_cap_l1_min_sec", 30.0)),
        "basket_cap_enabled": bool(h.get("basket_cap_enabled", True)),
        "basket_cap_usd": float(h.get("basket_cap_usd", -32.0)),
        "basket_cap_min_legs": int(h.get("basket_cap_min_legs", 1)),
        "sl_cascade_enabled": bool(h.get("sl_cascade_enabled", True)),
        "sl_cascade_min_legs": int(h.get("sl_cascade_min_legs", 2)),
        "sl_cascade_any_partial": bool(h.get("sl_cascade_any_partial", False)),
        "sl_cascade_loss_usd": float(h.get("sl_cascade_loss_usd", -9.0)),
        "sl_cascade_stack_usd": float(h.get("sl_cascade_stack_usd", -28.0)),
        "sl_cascade_use_float": bool(h.get("sl_cascade_use_float", False)),
        "sl_cascade_float_usd": float(h.get("sl_cascade_float_usd", -8.0)),
        "flatten_at": cfg["thresholds"]["health_flatten"],
        "no_add_at": cfg["thresholds"]["health_no_add"],
    }


def simulate_805p(
    df: pd.DataFrame,
    cfg: dict,
    *,
    export_dir: Path,
    window_arg: str,
) -> pd.DataFrame:
    export_window = resolve_export_window(df, window_arg)
    legs = load_window_legs(export_dir, export_window)
    keys = set(df["basket_key"].astype(str))
    legs = legs.loc[legs["basket_key"].isin(keys)].copy()
    return simulate_health_replay(df, legs, **health_805p_kwargs(cfg))


def load_regime_model(model_path: Path):
    if not model_path.is_file():
        raise FileNotFoundError(f"Regime model not found: {model_path}")
    return joblib.load(model_path)


def score_regime_skips(
    df: pd.DataFrame,
    opens: pd.DataFrame,
    model,
    skip_prob: float,
    feature_cols: list[str],
) -> pd.DataFrame:
    """Mark baskets to skip at arm time using precomputed leak-free open features."""
    out = df.sort_values("open_time").copy()
    feat = opens.set_index("basket_key")
    missing_keys = set(out["basket_key"].astype(str)) - set(feat.index.astype(str))
    if missing_keys:
        print(f"  WARN  {len(missing_keys)} basket(s) missing open features — never skipped")

    probs: list[float] = []
    skipped: list[bool] = []
    for key in out["basket_key"].astype(str):
        if key not in feat.index:
            probs.append(0.0)
            skipped.append(False)
            continue
        row = feat.loc[key]
        x = pd.DataFrame([row[feature_cols].astype(float).fillna(0.0).values], columns=feature_cols)
        p_bad = float(model.predict_proba(x)[0, 1])
        probs.append(p_bad)
        skipped.append(p_bad >= skip_prob)

    out["regime_p_bad"] = probs
    out["regime_skipped"] = skipped
    return out


def apply_regime_skip(
    df: pd.DataFrame,
    *,
    pnl_col: str = "basket_pnl",
) -> pd.DataFrame:
    out = df.copy()
    out["sim_pnl"] = np.where(out["regime_skipped"], 0.0, out[pnl_col].astype(float))
    out["lot_mult"] = 1.0
    out["trade_taken"] = ~out["regime_skipped"]
    return out


def attach_open_labels(df: pd.DataFrame, opens: pd.DataFrame) -> pd.DataFrame:
    cols = ["basket_key", "label_bad_basket", "is_tail", "is_d2_loss"]
    keep = [c for c in cols if c in opens.columns]
    if len(keep) <= 1:
        return df
    return df.merge(opens[keep], on="basket_key", how="left", suffixes=("", "_open"))


def simulate_regime_stack(
    df: pd.DataFrame,
    cfg: dict,
    *,
    export_dir: Path,
    window_arg: str,
    opens: pd.DataFrame,
    model,
    skip_prob: float,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """806 skip at open + 805p health replay on kept baskets."""
    base_805p = simulate_805p(df, cfg, export_dir=export_dir, window_arg=window_arg)
    scored = score_regime_skips(base_805p, opens, model, skip_prob, feature_cols)
    out = scored.copy()
    out["sim_pnl"] = np.where(
        out["regime_skipped"],
        0.0,
        out["sim_pnl"].astype(float),
    )
    out["lot_mult"] = 1.0
    out["trade_taken"] = ~out["regime_skipped"]
    out = attach_open_labels(out, opens)
    return out, base_805p


def regime_gate_report(
    baseline_m: dict,
    sim_m: dict,
    *,
    baseline_trades: int,
    sim_pnls: pd.Series,
    skip_rate: float,
    gates: dict,
) -> dict:
    net_floor = baseline_m["net"] * (1.0 + gates["net_vs_805p_pct"])
    trade_floor = int(baseline_trades * gates["min_trades_pct"])
    worst = float(sim_pnls.min()) if len(sim_pnls) else 0.0
    dd_delta = baseline_m["max_dd_pct"] - sim_m["max_dd_pct"]

    return {
        "net_vs_805p": sim_m["net"] >= net_floor,
        "net_floor": net_floor,
        "trades_volume": sim_m["trades"] >= trade_floor,
        "trade_floor": trade_floor,
        "pf_floor": sim_m["pf"] >= gates["longest_pf_floor"],
        "pf_floor_value": gates["longest_pf_floor"],
        "tail_loss": worst >= gates["tail_loss_usd"],
        "worst_basket": worst,
        "tail_limit": gates["tail_loss_usd"],
        "skip_rate_ok": skip_rate <= gates["max_skip_rate"],
        "skip_rate": skip_rate,
        "dd_improved": dd_delta >= 0,
        "dd_delta": dd_delta,
    }


def gates_all_pass(gates: dict) -> bool:
    return all(
        gates.get(k, False)
        for k in (
            "net_vs_805p",
            "trades_volume",
            "pf_floor",
            "tail_loss",
            "skip_rate_ok",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate AI policy offline")
    parser.add_argument("--baskets", type=Path, default=ROOT / "features" / "baskets_ai806.parquet")
    parser.add_argument(
        "--opens",
        type=Path,
        default=ROOT / "features" / "basket_opens.parquet",
        help="Basket-open features for regime skip (AI-806)",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "models" / "regime_v0.joblib",
        help="Regime classifier for --policy regime*",
    )
    parser.add_argument(
        "--entry-features",
        type=Path,
        default=ROOT / "features" / "train_entry.parquet",
        help="Entry-safe features for AI-804",
    )
    parser.add_argument(
        "--entry-model",
        type=Path,
        default=ROOT / "models" / "entry_context_v0.joblib",
        help="Entry context classifier for --policy entry_804*",
    )
    parser.add_argument(
        "--policy",
        default="memory",
        help="neutral | memory | memory_805p | entry_804_lock_ai | health | 805p | regime | regime_805p",
    )
    parser.add_argument("--window", default="AI806_805p")
    parser.add_argument("--deposit", type=float, default=200.0)
    parser.add_argument("--report", type=Path, default=ROOT / "features" / "sim_report.json")
    parser.add_argument("--csv", type=Path, default=ROOT / "features" / "sim_regime_805p.csv")
    parser.add_argument(
        "--skip-prob",
        type=float,
        default=None,
        help="P(bad) skip threshold (default config thresholds.regime_trend_skip_prob)",
    )
    parser.add_argument(
        "--health-mode",
        choices=("flatten_only", "full"),
        default=None,
        help="AI-805 replay mode (default from config.yaml health_sim.mode)",
    )
    parser.add_argument(
        "--health-checkpoint-sec",
        type=int,
        default=None,
        help="Seconds between causal health checkpoints (default config)",
    )
    parser.add_argument(
        "--legacy-health",
        action="store_true",
        help="Use deprecated post-hoc PnL cap (hindsight) for comparison",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=ROOT / "export",
        help="Diagnostics CSV directory for leg-level replay",
    )
    args = parser.parse_args()

    cfg = load_config()
    health_sim = cfg.get("health_sim", {})
    health_mode = args.health_mode or health_sim.get("mode", "flatten_only")
    checkpoint_sec = args.health_checkpoint_sec or int(health_sim.get("checkpoint_sec", 60))
    flatten_float = float(health_sim.get("flatten_float_usd", -18.0))
    stress_flatten_at = float(health_sim.get("stress_flatten_at", 75.0))
    hard_cap_enabled = bool(health_sim.get("hard_cap_enabled", True))
    hard_cap_usd = float(health_sim.get("hard_cap_usd", -25.0))
    hard_cap_l1_enabled = bool(health_sim.get("hard_cap_l1_enabled", True))
    hard_cap_l1_usd = float(health_sim.get("hard_cap_l1_usd", -35.0))
    hard_cap_l1_min_sec = float(health_sim.get("hard_cap_l1_min_sec", 60.0))
    baseline = cfg["baseline"]
    gates = cfg["promotion_gates"]
    regime_gates = cfg.get("regime_gates", {})
    lot_min = cfg["thresholds"]["lot_mult_min"]
    lot_max = cfg["thresholds"]["lot_mult_max"]
    block_floor = cfg["thresholds"]["entry_block_floor"]
    block_conf = cfg["thresholds"]["entry_block_confidence_min"]
    skip_prob = args.skip_prob if args.skip_prob is not None else cfg["thresholds"]["regime_trend_skip_prob"]

    baskets = pd.read_parquet(args.baskets)
    baskets["open_time"] = pd.to_datetime(baskets["open_time"])
    subset = parse_window_arg(args.window, baskets)
    if subset.empty:
        raise SystemExit(f"No baskets for window {args.window!r}")

    base_805p_df: pd.DataFrame | None = None
    lock_ai_base_df: pd.DataFrame | None = None

    if args.policy == "neutral":
        subset = subset.copy()
        subset["sim_pnl"] = subset["basket_pnl"]
        subset["lot_mult"] = 1.0
    elif args.policy == "memory":
        subset = simulate_memory(subset, lot_min)
    elif args.policy == "805p":
        subset = simulate_805p(
            subset, cfg, export_dir=args.export_dir, window_arg=args.window
        )
        subset["lot_mult"] = 1.0
    elif args.policy == "memory_805p":
        subset, base_805p_df = simulate_memory_805p(
            subset,
            cfg,
            export_dir=args.export_dir,
            window_arg=args.window,
            lot_min=lot_min,
        )
    elif args.policy == "entry_804_lock_ai":
        entry_feats = pd.read_parquet(args.entry_features)
        entry_feats["open_time"] = pd.to_datetime(entry_feats["open_time"])
        if ":" in args.window and len(args.window.split(":")) == 2:
            start, end = args.window.split(":", 1)
            ot = entry_feats["open_time"]
            entry_feats = entry_feats.loc[
                (ot >= pd.Timestamp(start)) & (ot <= pd.Timestamp(end) + pd.Timedelta(days=1))
            ].copy()
        elif "window" in entry_feats.columns:
            entry_feats = entry_feats[entry_feats["window"] == args.window].copy()

        entry_model = joblib.load(args.entry_model)
        meta_path = args.entry_model.with_suffix(".json")
        feature_cols = list(ENTRY_CONTEXT_FEATURES)
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            feature_cols = meta.get("features", feature_cols)

        lock_ai_base_df, base_805p_df = simulate_memory_805p(
            subset,
            cfg,
            export_dir=args.export_dir,
            window_arg=args.window,
            lot_min=lot_min,
        )
        subset, base_805p_df = simulate_entry_lock_ai(
            subset,
            cfg,
            export_dir=args.export_dir,
            window_arg=args.window,
            entry_feats=entry_feats,
            model=entry_model,
            feature_cols=feature_cols,
            lot_min=lot_min,
            lot_max=lot_max,
            block_floor=block_floor,
            block_conf=block_conf,
        )
    elif args.policy == "health":
        subset = simulate_health(
            subset,
            cfg,
            export_dir=args.export_dir,
            window_arg=args.window,
            mode=health_mode,
            checkpoint_sec=checkpoint_sec,
            flatten_float=flatten_float,
            stress_flatten_at=stress_flatten_at,
            hard_cap_enabled=hard_cap_enabled,
            hard_cap_usd=hard_cap_usd,
            hard_cap_l1_enabled=hard_cap_l1_enabled,
            hard_cap_l1_usd=hard_cap_l1_usd,
            hard_cap_l1_min_sec=hard_cap_l1_min_sec,
            legacy=args.legacy_health,
        )
    elif args.policy in ("regime", "regime_805p"):
        if not args.opens.is_file():
            raise SystemExit(f"Missing basket opens: {args.opens}")
        opens = pd.read_parquet(args.opens)
        if ":" in args.window and len(args.window.split(":")) == 2:
            start, end = args.window.split(":", 1)
            ot = pd.to_datetime(opens["open_time"])
            opens = opens.loc[
                (ot >= pd.Timestamp(start)) & (ot <= pd.Timestamp(end) + pd.Timedelta(days=1))
            ].copy()
        else:
            opens = opens[opens["window"] == args.window].copy()

        model = load_regime_model(args.model)
        meta_path = args.model.with_suffix(".json")
        feature_cols = REGIME_FEATURES
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            feature_cols = meta.get("features", REGIME_FEATURES)

        if args.policy == "regime":
            scored = score_regime_skips(subset, opens, model, skip_prob, feature_cols)
            subset = apply_regime_skip(scored, pnl_col="basket_pnl")
            subset = attach_open_labels(subset, opens)
        else:
            subset, base_805p_df = simulate_regime_stack(
                subset,
                cfg,
                export_dir=args.export_dir,
                window_arg=args.window,
                opens=opens,
                model=model,
                skip_prob=skip_prob,
                feature_cols=feature_cols,
            )
    else:
        print(f"  policy {args.policy!r} not implemented — using neutral")
        subset = subset.copy()
        subset["sim_pnl"] = subset["basket_pnl"]
        subset["lot_mult"] = 1.0

    if args.policy == "entry_804_lock_ai" and lock_ai_base_df is not None:
        base_m = equity_metrics(lock_ai_base_df["sim_pnl"], args.deposit)
        base_trades = int(len(lock_ai_base_df))
    elif args.policy in ("regime_805p", "memory_805p") and base_805p_df is not None:
        base_m = equity_metrics(base_805p_df["sim_pnl"], args.deposit)
        base_trades = int(len(base_805p_df))
    else:
        base_m = equity_metrics(subset["basket_pnl"], args.deposit)
        base_trades = int(base_m["trades"])
    sim_m = equity_metrics(subset["sim_pnl"], args.deposit)
    if "trade_taken" in subset.columns:
        sim_m["trades"] = int(subset["trade_taken"].sum())
        sim_m["skipped"] = int((~subset["trade_taken"]).sum())

    base_net = base_m["net"]
    sim_net = sim_m["net"]
    net_floor = base_net * (1.0 + gates["net_vs_production_pct"])
    trade_floor = int(base_m["trades"] * gates["min_trades_pct"])
    dd_improved = base_m["max_dd_pct"] - sim_m["max_dd_pct"]

    gate_net = sim_net >= net_floor
    gate_trades = sim_m["trades"] >= trade_floor
    gate_dd = dd_improved >= gates["dd_improve_pts"]
    gates_passed = gate_net and gate_trades and gate_dd

    skip_rate = float(subset.get("regime_skipped", pd.Series([False])).mean())
    regime_gate_details: dict | None = None
    if args.policy in ("regime", "regime_805p") and regime_gates:
        regime_gate_details = regime_gate_report(
            base_m,
            sim_m,
            baseline_trades=base_trades,
            sim_pnls=subset["sim_pnl"],
            skip_rate=skip_rate,
            gates=regime_gates,
        )
        gates_passed = gates_all_pass(regime_gate_details)

    report = {
        "policy": args.policy,
        "window": args.window,
        "baseline": base_m,
        "simulated": sim_m,
        "throttle_rate": float(subset.get("memory_throttled", pd.Series([False])).mean()),
        "gates": {
            "net_vs_production": gate_net,
            "net_floor": net_floor,
            "trades_volume": gate_trades,
            "trade_floor": trade_floor,
            "dd_improve_pts": gate_dd,
            "dd_delta": dd_improved,
        },
        "gates_passed": gates_passed,
        "baseline_pf_ref": baseline["production_pf_19mo"],
    }
    if regime_gate_details is not None:
        report["regime_gates"] = regime_gate_details
        report["regime_sim"] = {
            "skip_prob": skip_prob,
            "skip_rate": skip_rate,
            "skipped_baskets": int(subset.get("regime_skipped", pd.Series([False])).sum()),
            "skipped_bad_rate": float(
                subset.loc[subset["regime_skipped"], "label_bad_basket"].mean()
            )
            if "label_bad_basket" in subset.columns and subset["regime_skipped"].any()
            else None,
        }
    if args.policy == "health":
        report["health_sim"] = {
            "engine": "legacy_posthoc" if args.legacy_health else "event_replay",
            "mode": health_mode if not args.legacy_health else "legacy",
            "checkpoint_sec": checkpoint_sec,
            **intervention_summary(subset),
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.policy in ("memory", "health", "regime", "regime_805p", "805p"):
        subset.to_csv(args.csv, index=False)

    tag = "AI-806" if args.policy in ("regime", "regime_805p") else "AI-803"
    print(f"[{tag}] simulate_policy — {args.policy} on {args.window}")
    base_worst = float(base_805p_df["sim_pnl"].min()) if base_805p_df is not None else float(subset["basket_pnl"].min())
    print(f"  baseline: net=${base_m['net']:.2f} PF={base_m['pf']:.2f} "
          f"DD={base_m['max_dd_pct']:.1f}% trades={base_m['trades']} worst=${base_worst:.2f}")
    print(f"  simulated: net=${sim_m['net']:.2f} PF={sim_m['pf']:.2f} "
          f"DD={sim_m['max_dd_pct']:.1f}% trades={sim_m['trades']} "
          f"worst=${float(subset['sim_pnl'].min()):.2f}")
    if args.policy == "memory":
        print(f"  throttle rate: {report['throttle_rate']:.1%}")
    if args.policy == "health" and "health_sim" in report:
        hs = report["health_sim"]
        print(f"  health engine: {hs['engine']} mode={hs.get('mode')} checkpoint={hs['checkpoint_sec']}s")
        print(f"  interventions: {hs.get('intervention_counts', {})}")
        print(f"  baskets changed: {hs.get('baskets_changed', 0)} "
              f"(pnl delta ${hs.get('pnl_delta', 0):.2f})")
    if regime_gate_details is not None:
        rs = report.get("regime_sim", {})
        print(f"  regime skip: {rs.get('skip_rate', 0):.1%} ({rs.get('skipped_baskets', 0)} baskets)")
        if rs.get("skipped_bad_rate") is not None:
            print(f"  skipped bad-basket rate: {rs['skipped_bad_rate']:.1%}")
        rg = regime_gate_details
        print(
            f"  gates: net={'PASS' if rg['net_vs_805p'] else 'FAIL'} "
            f"trades={'PASS' if rg['trades_volume'] else 'FAIL'} "
            f"PF={'PASS' if rg['pf_floor'] else 'FAIL'} "
            f"tail={'PASS' if rg['tail_loss'] else 'FAIL'} "
            f"skip={'PASS' if rg['skip_rate_ok'] else 'FAIL'}"
        )
    else:
        print(f"  gates: net={'PASS' if gate_net else 'FAIL'} "
              f"trades={'PASS' if gate_trades else 'FAIL'} "
              f"DD={'PASS' if gate_dd else 'FAIL'} ({dd_improved:+.1f} pts)")
    print(f"  overall: {'PASS' if gates_passed else 'FAIL — review before MT5 wire'}")
    print(f"  report: {args.report}")

    return 0 if gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
