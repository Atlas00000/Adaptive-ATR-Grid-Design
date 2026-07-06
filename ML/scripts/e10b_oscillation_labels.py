#!/usr/bin/env python3
"""E10b: Oscillation score + leg labels for geometry enhancement (not blocking)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import ROOT, load_config
from analyze_expectancy import load_baskets
from basket_replay import load_window_legs
from build_features import regime_from_atr_pct, session_minute_in_window
from e9c_context_geometry import enrich_baskets
from e9d_physics_labels import l0_path_extremes

WINDOWS = ("w03_longest", "w02_ext19mo", "AI806_805p")
BASKET_PATHS = {
    "w03_longest": "features/baskets_w03_longest.parquet",
    "w02_ext19mo": "features/baskets_w02_ext19mo.parquet",
    "AI806_805p": "features/baskets_ai806.parquet",
}
STACK_TAIL_USD = -20.0  # offline leg-sum proxy (−$35 is MT5 wire; max basket ~−$27)
STACK_TAIL_SEVERE_USD = -25.0
# Soft validation — enhancement multipliers, not skip gates
MIN_AUC = 0.52


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def direction_chop(bias: pd.Series, window: int = 20) -> pd.Series:
    """Causal chop proxy: share of direction flips in prior baskets."""
    buy = (bias.str.upper() == "BUY").astype(float)

    def _flip_rate(x: np.ndarray) -> float:
        if len(x) < 2:
            return 0.5
        flips = np.sum(x[1:] != x[:-1])
        return flips / (len(x) - 1)

    return buy.shift(1).rolling(window, min_periods=5).apply(_flip_rate, raw=True)


def compute_open_features(group: pd.DataFrame) -> pd.DataFrame:
    """Causal entry-time features — no future basket PnL."""
    g = group.sort_values("open_time").copy()
    g["adx"] = g["entry_adx"].astype(float)
    g["atr"] = g["entry_atr"].astype(float)
    g["atr_pips"] = g["atr"] * 10_000.0

    atr_med = g["atr"].shift(1).rolling(100, min_periods=10).median()
    g["atr_pct_100"] = np.where(atr_med > 0, g["atr"] / atr_med, np.nan)

    g["adx_slope_3"] = g["adx"].diff().shift(1).rolling(3, min_periods=1).mean()
    g["minute_in_session"] = session_minute_in_window(g["open_time"])
    g["direction_chop_20"] = direction_chop(g["bias"], 20)
    g["regime_proxy"] = regime_from_atr_pct(g["atr_pct_100"])
    return g


def oscillation_score_open(row: pd.Series) -> float:
    """
    Continuous 0–100 rotation score for geometry multipliers.
    Low ADX, falling ADX, mid ATR band, high chop → higher score.
    No hard thresholds — smooth components blended for enhancement bands.
    """
    adx = float(row.get("adx", 20.0))
    adx_component = _clip01((22.0 - adx) / 10.0)

    slope = float(row.get("adx_slope_3", 0.0) or 0.0)
    slope_component = _clip01(0.35 + (-slope / 2.5)) if slope < 0 else 0.35

    atr_pct = float(row.get("atr_pct_100", 1.0) or 1.0)
    atr_component = _clip01(1.0 - abs(atr_pct - 1.0) / 0.35)

    chop = float(row.get("direction_chop_20", 0.5) or 0.5)
    chop_component = _clip01(chop)

    session_min = float(row.get("minute_in_session", 60) or 60)
    session_component = _clip01(1.0 - abs(session_min - 60.0) / 90.0)

    raw = (
        0.30 * adx_component
        + 0.15 * slope_component
        + 0.25 * atr_component
        + 0.20 * chop_component
        + 0.10 * session_component
    )
    return round(100.0 * raw, 2)


def oscillation_score_l0_close(l0: dict, entry_adx: float) -> float:
    """Score after L0 closes — path shape only (causal at L0 close)."""
    mae, mfe = l0_path_extremes(l0)
    hold_h = max((l0["close_time"] - l0["open_time"]).total_seconds() / 3600.0, 0.01)
    mae_usd = abs(min(mae, 0.0))
    mfe_usd = max(mfe, 0.0)

    # Quick TP with shallow MAE → rotation; deep MAE / long hold → trend push
    mfe_component = _clip01(mfe_usd / 12.0)
    mae_penalty = _clip01(mae_usd / 12.0)
    hold_component = _clip01(1.0 - hold_h / 4.0)
    adx_component = _clip01((22.0 - float(l0.get("adx", entry_adx))) / 10.0)

    raw = (
        0.30 * mfe_component
        + 0.25 * hold_component
        + 0.25 * adx_component
        + 0.20 * (1.0 - mae_penalty)
    )
    return round(100.0 * raw, 2)


def enhancement_band(score: float, p33: float, p67: float) -> str:
    """Data-driven tertiles — enhancement multipliers, not skip gates."""
    if score < p33:
        return "low"
    if score < p67:
        return "mid"
    return "high"


def build_leg_labels(
    baskets: pd.DataFrame,
    legs: pd.DataFrame,
    window: str,
) -> pd.DataFrame:
    g = compute_open_features(baskets)
    g = enrich_baskets(g)
    g["oscillation_score_open"] = g.apply(oscillation_score_open, axis=1)
    p33 = float(g["oscillation_score_open"].quantile(0.33))
    p67 = float(g["oscillation_score_open"].quantile(0.67))
    g["enhancement_band"] = g["oscillation_score_open"].apply(
        lambda s: enhancement_band(s, p33, p67)
    )
    g["band_p33"] = p33
    g["band_p67"] = p67

    leg_meta: dict[str, dict] = {}
    for basket_key, grp in legs.groupby("basket_key", sort=False):
        bk = str(basket_key)
        grp = grp.sort_values(["level", "open_time"])
        l0_rows = grp.loc[grp["level"] == 0]
        if l0_rows.empty:
            continue
        l0 = l0_rows.iloc[0].to_dict()
        l0["open_time"] = pd.to_datetime(l0["open_time"])
        l0["close_time"] = pd.to_datetime(l0["close_time"])
        l0_pnl = float(l0["profit"])
        full_pnl = float(grp["profit"].sum())
        max_filled = int(grp["level"].max()) + 1 if len(grp) else 1
        levels_filled = int(len(grp))

        leg_meta[bk] = {
            "l0_tp_hit": int(str(l0.get("exit_reason", "")).upper() == "TP"),
            "l0_sl_hit": int(str(l0.get("exit_reason", "")).upper() == "SL"),
            "oscillation_win": int(
                str(l0.get("exit_reason", "")).upper() == "TP" and levels_filled == 1
            ),
            "stack_tail": int(full_pnl <= STACK_TAIL_USD and levels_filled >= 2),
            "stack_tail_severe": int(
                full_pnl <= STACK_TAIL_SEVERE_USD and levels_filled >= 2
            ),
            "rotation_favorable": int(levels_filled >= 2 and l0_pnl > full_pnl),
            "l0_only_pnl": l0_pnl,
            "levels_filled": levels_filled,
            "oscillation_score_l0_close": oscillation_score_l0_close(
                l0, float(l0.get("adx", 0))
            ),
        }

    for col, default in (
        ("l0_tp_hit", 0),
        ("l0_sl_hit", 0),
        ("oscillation_win", 0),
        ("stack_tail", 0),
        ("stack_tail_severe", 0),
        ("rotation_favorable", 0),
        ("l0_only_pnl", np.nan),
        ("levels_filled", 1),
        ("oscillation_score_l0_close", np.nan),
    ):
        g[col] = g["basket_key"].astype(str).map(
            lambda k, c=col, d=default: leg_meta.get(k, {}).get(c, d)
        )

    g["window"] = window
    g["is_2024_h1"] = (g["open_time"] >= "2024-01-01") & (g["open_time"] < "2024-07-01")
    return g


def auc_safe(y: pd.Series, score: pd.Series) -> float | None:
    mask = y.notna() & score.notna()
    y = y.loc[mask].astype(int)
    score = score.loc[mask].astype(float)
    if y.nunique() < 2 or len(y) < 20:
        return None
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y, score))
    except Exception:
        return None


def rank_corr_safe(y: pd.Series, score: pd.Series) -> float | None:
    mask = y.notna() & score.notna()
    if mask.sum() < 20 or y.loc[mask].nunique() < 2:
        return None
    return float(y.loc[mask].astype(float).corr(score.loc[mask], method="spearman"))


def evaluate_window(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {"baskets": 0}

    h1 = df.loc[df["is_2024_h1"]]
    rest = df.loc[~df["is_2024_h1"]]

    def label_rates(sub: pd.DataFrame) -> dict:
        if sub.empty:
            return {}
        return {
            "l0_tp_pct": round(100.0 * sub["l0_tp_hit"].mean(), 1),
            "oscillation_win_pct": round(100.0 * sub["oscillation_win"].mean(), 1),
            "stack_tail_pct": round(100.0 * sub["stack_tail"].mean(), 1),
            "stack_tail_severe_pct": round(100.0 * sub["stack_tail_severe"].mean(), 1),
            "rotation_favorable_pct": round(100.0 * sub["rotation_favorable"].mean(), 1),
        }

    band_stats = []
    for band in ("low", "mid", "high"):
        sub = df.loc[df["enhancement_band"] == band]
        if sub.empty:
            continue
        band_stats.append(
            {
                "band": band,
                "baskets": len(sub),
                "pct": round(100.0 * len(sub) / n, 1),
                "mean_score": round(float(sub["oscillation_score_open"].mean()), 1),
                **label_rates(sub),
            }
        )

    auc = {
        "oscillation_win": auc_safe(df["oscillation_win"], df["oscillation_score_open"]),
        "stack_tail": auc_safe(df["stack_tail"], -df["oscillation_score_open"]),
        "stack_tail_severe": auc_safe(
            df["stack_tail_severe"], -df["oscillation_score_open"]
        ),
        "l0_tp_hit": auc_safe(df["l0_tp_hit"], df["oscillation_score_open"]),
        "rotation_favorable": auc_safe(
            df["rotation_favorable"], df["oscillation_score_l0_close"]
        ),
    }
    spearman = {
        "oscillation_win": rank_corr_safe(df["oscillation_win"], df["oscillation_score_open"]),
        "stack_tail": rank_corr_safe(df["stack_tail"], -df["oscillation_score_open"]),
    }

    auc_ok = [
        k
        for k, v in auc.items()
        if v is not None and ((k == "stack_tail" and v >= MIN_AUC) or (k != "stack_tail" and v >= MIN_AUC))
    ]
    gate_pass = len(auc_ok) >= 2

    return {
        "baskets": n,
        "score_open_mean": round(float(df["oscillation_score_open"].mean()), 1),
        "score_open_p33": round(float(df["oscillation_score_open"].quantile(0.33)), 1),
        "score_open_p67": round(float(df["oscillation_score_open"].quantile(0.67)), 1),
        "band_cutpoints": {
            "p33": round(float(df["oscillation_score_open"].quantile(0.33)), 1),
            "p67": round(float(df["oscillation_score_open"].quantile(0.67)), 1),
        },
        "label_rates": label_rates(df),
        "band_stats": band_stats,
        "auc": {k: round(v, 3) if v is not None else None for k, v in auc.items()},
        "spearman": {k: round(v, 3) if v is not None else None for k, v in spearman.items()},
        "h1_vs_rest": {
            "h1_score_mean": round(float(h1["oscillation_score_open"].mean()), 1) if len(h1) else None,
            "rest_score_mean": round(float(rest["oscillation_score_open"].mean()), 1)
            if len(rest)
            else None,
            "h1_stack_tail_pct": round(100.0 * h1["stack_tail"].mean(), 1) if len(h1) else None,
            "rest_stack_tail_pct": round(100.0 * rest["stack_tail"].mean(), 1)
            if len(rest)
            else None,
        },
        "gate_pass": gate_pass,
        "gate_note": f"soft AUC >= {MIN_AUC} on >=2 labels (enhancement, not blocking)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E10b oscillation score + leg labels")
    parser.add_argument(
        "--window",
        choices=[*WINDOWS, "all"],
        default="all",
    )
    parser.add_argument("--export-dir", type=Path, default=ROOT / "export")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "features" / "e10b_labels.parquet",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "features" / "e10b_report.json",
    )
    args = parser.parse_args()
    load_config()

    specs = WINDOWS if args.window == "all" else (args.window,)
    frames: list[pd.DataFrame] = []
    runs: list[dict] = []

    print("[E10b] Oscillation score + leg labels (enhancement bands, soft gates)")
    print("-" * 72)

    for window in specs:
        rel = BASKET_PATHS[window]
        path = ROOT / rel
        if not path.is_file():
            path = path.with_suffix(".csv")
        baskets = load_baskets(path, window, args.export_dir)
        legs = load_window_legs(args.export_dir, window)
        df = build_leg_labels(baskets, legs, window)
        frames.append(df)
        ev = evaluate_window(df)
        ev["window"] = window
        runs.append(ev)

        lr = ev.get("label_rates", {})
        print(
            f"  {window:14s} n={ev['baskets']:3d}  score={ev['score_open_mean']:.1f}  "
            f"L0_TP={lr.get('l0_tp_pct', 0):.0f}%  osc_win={lr.get('oscillation_win_pct', 0):.0f}%  "
            f"tail={lr.get('stack_tail_pct', 0):.1f}%  gate={'PASS' if ev['gate_pass'] else 'soft'}"
        )
        for band in ev.get("band_stats", []):
            print(
                f"    {band['band']:4s} ({band['pct']:4.0f}%)  "
                f"osc_win={band.get('oscillation_win_pct', 0):.0f}%  "
                f"tail={band.get('stack_tail_pct', 0):.1f}%"
            )

    combined = pd.concat(frames, ignore_index=True).sort_values("open_time")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(args.output, index=False)

    combo_ev = evaluate_window(combined)
    report = {
        "e10b": "oscillation_labels",
        "purpose": "enhancement multipliers — continuous score, tertile bands, no skip gates",
        "min_auc_soft": MIN_AUC,
        "enhancement_bands": {
            "low": "bottom tertile (p33) → tighter geometry (E10c)",
            "mid": "middle tertile → baseline multipliers",
            "high": "top tertile (p67+) → fuller depth / wider spacing (E10c–d)",
        },
        "stack_tail_note": "offline ≤−$20 multi-leg; −$35 is MT5 wire reference",
        "labels": {
            "l0_tp_hit": "L0 closed at TP",
            "oscillation_win": "L0 TP, no L1+",
            "stack_tail": f"basket PnL <= {STACK_TAIL_USD} with >=2 legs (offline)",
            "stack_tail_severe": f"basket PnL <= {STACK_TAIL_SEVERE_USD} with >=2 legs",
            "rotation_favorable": "L0-only PnL > full basket (adds hurt)",
        },
        "runs": runs,
        "combined": combo_ev,
        "output_parquet": str(args.output),
    }

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print("-" * 72)
    print(
        f"  combined: n={combo_ev['baskets']}  "
        f"AUC osc_win={combo_ev['auc'].get('oscillation_win')}  "
        f"AUC stack_tail={combo_ev['auc'].get('stack_tail')}  "
        f"gate={'PASS' if combo_ev['gate_pass'] else 'soft-ok'}"
    )
    print(f"  parquet: {args.output}")
    print(f"  report:  {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
