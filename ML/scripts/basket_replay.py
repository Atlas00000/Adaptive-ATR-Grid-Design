"""AI-810: Event-level basket replay for causal health policy simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Callable, Literal

import pandas as pd

HealthMode = Literal["flatten_only", "full"]
L0SlGateFn = Callable[[dict, float], bool]

TIGHTEN_THRESHOLD = 72.0
STRESS_FLATTEN_THRESHOLD = 75.0
TP_TIGHTEN_RATIO = 1.25 / 1.5  # 1.25×ATR vs baseline 1.5×ATR
TRIM_PROFIT_FLOOR = 8.0


def stress_health_score(floating_pl: float, open_count: int) -> float:
    """PnL stress only — no time/distance (matches EA flatten_only)."""
    h = 0.0
    if floating_pl < 0.0:
        h += min(45.0, abs(floating_pl) * 3.0)
    if open_count >= 2:
        h += 20.0
    if open_count >= 1 and floating_pl < -10.0:
        h += 15.0
    return min(100.0, h)


@dataclass
class ReplayResult:
    basket_key: str
    sim_pnl: float
    baseline_pnl: float
    max_health: float
    intervention: str
    blocked_levels: list[int] = field(default_factory=list)
    flatten_time: pd.Timestamp | None = None


def rule_health_score(
    floating_pl: float,
    open_count: int,
    seconds_open: float,
    dist_anchor_atr: float,
) -> float:
    """Match Include/AISupervisor.mqh RuleHealthScore."""
    h = 0.0
    if floating_pl < 0.0:
        h += min(45.0, abs(floating_pl) * 3.0)
    if open_count >= 2:
        h += 20.0
    if open_count >= 1 and floating_pl < -10.0:
        h += 15.0
    if seconds_open > 2400:
        h += 10.0
    if seconds_open > 5400:
        h += 15.0
    if dist_anchor_atr > 1.25:
        h += min(25.0, (dist_anchor_atr - 1.0) * 15.0)
    return min(100.0, h)


def leg_unrealized_at(leg: dict, t: pd.Timestamp) -> float:
    """Linear PnL path from open → close (causal estimate of floating)."""
    open_t = leg["open_time"]
    close_t = leg["close_time"]
    if t <= open_t:
        return 0.0
    if t >= close_t:
        return float(leg["profit"])
    duration = (close_t - open_t).total_seconds()
    if duration <= 0:
        return float(leg["profit"])
    frac = (t - open_t).total_seconds() / duration
    return float(leg["profit"]) * frac


def dist_anchor_atr_proxy(open_legs: list[dict], t: pd.Timestamp, entry_atr: float) -> float:
    """Proxy price-distance in ATR units from worst open-leg unrealized PnL."""
    if entry_atr <= 0 or not open_legs:
        return 0.0
    worst = 0.0
    for leg in open_legs:
        u = leg_unrealized_at(leg, t)
        if u < worst:
            worst = u
    if worst >= 0:
        return 0.0
    return abs(worst) / entry_atr


def basket_floating_at(
    open_legs: list[dict],
    realized: float,
    t: pd.Timestamp,
) -> float:
    if not open_legs:
        return realized
    unrealized = sum(leg_unrealized_at(leg, t) for leg in open_legs)
    return realized + unrealized


def should_hard_cap(
    open_count: int,
    floating_pl: float,
    seconds_open: float,
    *,
    hard_cap_enabled: bool,
    hard_cap_usd: float,
    hard_cap_l1_enabled: bool = True,
    hard_cap_l1_usd: float = -28.0,
    hard_cap_l1_min_sec: float = 30.0,
) -> tuple[bool, str]:
    if not hard_cap_enabled:
        return False, ""
    if open_count >= 2 and floating_pl < hard_cap_usd and seconds_open >= 120:
        return True, "hard_cap"
    if (
        hard_cap_l1_enabled
        and open_count >= 1
        and floating_pl < hard_cap_l1_usd
        and seconds_open >= hard_cap_l1_min_sec
    ):
        return True, "hard_cap_l1"
    return False, ""


def should_basket_cap(
    open_count: int,
    total_pnl: float,
    *,
    basket_cap_enabled: bool,
    basket_cap_usd: float,
    basket_cap_min_legs: int,
) -> bool:
    if not basket_cap_enabled:
        return False
    if open_count < basket_cap_min_legs:
        return False
    return total_pnl < basket_cap_usd


def should_sl_cascade(
    legs_before: int,
    deal_profit: float,
    open_after: int,
    *,
    sl_cascade_enabled: bool,
    sl_cascade_min_legs: int,
    sl_cascade_loss_usd: float,
    sl_cascade_any_partial: bool = False,
    sl_cascade_stack_usd: float = -28.0,
    sl_cascade_use_float: bool = False,
    sl_cascade_float_usd: float = -8.0,
    remaining_float: float = 0.0,
) -> bool:
    if not sl_cascade_enabled:
        return False
    if legs_before < sl_cascade_min_legs:
        return False
    if open_after <= 0 or open_after >= legs_before:
        return False
    if deal_profit >= 0.0:
        return False
    if sl_cascade_any_partial:
        return True
    if deal_profit <= sl_cascade_loss_usd:
        return True
    if sl_cascade_stack_usd < 0.0 and (deal_profit + remaining_float) < sl_cascade_stack_usd:
        return True
    if sl_cascade_use_float and remaining_float < sl_cascade_float_usd:
        return True
    return False


def apply_health_policy(
    health: float,
    open_count: int,
    floating_pl: float,
    seconds_open: float,
    *,
    mode: HealthMode,
    flatten_at: float,
    no_add_at: float,
    flatten_float: float = -18.0,
    stress_flatten_at: float = STRESS_FLATTEN_THRESHOLD,
    hard_cap_enabled: bool = True,
    hard_cap_usd: float = -25.0,
    hard_cap_l1_enabled: bool = True,
    hard_cap_l1_usd: float = -28.0,
    hard_cap_l1_min_sec: float = 30.0,
) -> tuple[str, bool]:
    """Return (action_label, should_flatten_now). Mirrors EA ApplyHealthPolicy guards."""
    cap_now, cap_action = should_hard_cap(
        open_count, floating_pl, seconds_open,
        hard_cap_enabled=hard_cap_enabled, hard_cap_usd=hard_cap_usd,
        hard_cap_l1_enabled=hard_cap_l1_enabled,
        hard_cap_l1_usd=hard_cap_l1_usd,
        hard_cap_l1_min_sec=hard_cap_l1_min_sec,
    )
    if cap_now:
        return cap_action, True

    if mode == "flatten_only":
        stress_h = stress_health_score(floating_pl, open_count)
        if (
            stress_h > stress_flatten_at
            and open_count >= 2
            and floating_pl < flatten_float
            and seconds_open >= 120
        ):
            return "flatten", True
        return "ok", False

    if (
        health > flatten_at
        and open_count >= 2
        and floating_pl < flatten_float
        and seconds_open >= 120
    ):
        return "flatten", True

    if health > TIGHTEN_THRESHOLD and open_count >= 2:
        return "tighten", False
    if health > no_add_at and open_count >= 1:
        return "no_add", False
    return "ok", False


def load_window_legs(export_dir: Path, window: str) -> pd.DataFrame:
    """Load leg-level trades CSV for a diagnostics window prefix."""
    pattern = f"{window}_trades_*.csv"
    files = sorted(export_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No trade files for window {window!r} in {export_dir}")
    frames = []
    for path in files:
        df = pd.read_csv(path)
        df["window"] = window
        df["basket_key"] = window + "_" + df["basket_id"].astype(str)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["open_time"] = pd.to_datetime(out["open_time"])
    out["close_time"] = pd.to_datetime(out["close_time"])
    out["profit"] = out["profit"].astype(float)
    out["level"] = out["level"].astype(int)
    return out.sort_values(["basket_key", "open_time", "level"]).reset_index(drop=True)


def _event_sort_key(item: tuple) -> tuple:
    t, kind, _ = item
    kind_order = {"open": 0, "checkpoint": 1, "close": 2}
    return (t, kind_order[kind])


def replay_basket(
    legs: pd.DataFrame,
    *,
    mode: HealthMode = "flatten_only",
    max_grid_levels: int | None = None,
    spacing_mult: float = 1.0,
    spacing_min_gap_sec: float = 300.0,
    no_add_after_l0_sl: bool = False,
    l0_sl_gate_fn: L0SlGateFn | None = None,
    flatten_at: float = 88.0,
    no_add_at: float = 55.0,
    checkpoint_sec: int = 60,
    flatten_float: float = -18.0,
    stress_flatten_at: float = STRESS_FLATTEN_THRESHOLD,
    hard_cap_enabled: bool = True,
    hard_cap_usd: float = -25.0,
    hard_cap_l1_enabled: bool = True,
    hard_cap_l1_usd: float = -28.0,
    hard_cap_l1_min_sec: float = 30.0,
    basket_cap_enabled: bool = True,
    basket_cap_usd: float = -32.0,
    basket_cap_min_legs: int = 1,
    sl_cascade_enabled: bool = True,
    sl_cascade_min_legs: int = 2,
    sl_cascade_any_partial: bool = False,
    sl_cascade_loss_usd: float = -9.0,
    sl_cascade_stack_usd: float = -28.0,
    sl_cascade_use_float: bool = False,
    sl_cascade_float_usd: float = -8.0,
) -> ReplayResult:
    """Replay one basket with causal health interventions at open/close/checkpoints."""
    legs = legs.sort_values(["level", "open_time"]).reset_index(drop=True)
    basket_key = str(legs.iloc[0]["basket_key"])
    baseline_pnl = float(legs["profit"].sum())
    entry_atr = float(legs.loc[legs["level"] == 0, "atr"].iloc[0])

    leg_rows = [row.to_dict() for _, row in legs.iterrows()]
    basket_start = min(r["open_time"] for r in leg_rows)
    basket_end = max(r["close_time"] for r in leg_rows)

    events: list[tuple] = []
    for leg in leg_rows:
        events.append((leg["open_time"], "open", leg))
        events.append((leg["close_time"], "close", leg))

    t = basket_start
    while t <= basket_end:
        events.append((t, "checkpoint", None))
        t += timedelta(seconds=checkpoint_sec)
    events.sort(key=_event_sort_key)

    open_legs: list[dict] = []
    blocked_levels: set[int] = set()
    realized = 0.0
    tighten_active = False
    trim_done = False
    max_health = 0.0
    intervention = "none"
    flatten_time: pd.Timestamp | None = None
    sim_pnl: float | None = None

    def levels_blocked_from(level: int) -> None:
        for leg in leg_rows:
            if int(leg["level"]) >= level:
                blocked_levels.add(int(leg["level"]))

    def spacing_blocks_level(leg: dict) -> bool:
        """Wider spacing proxy: block add if inter-level gap shorter than scaled minimum."""
        if spacing_mult <= 1.0 or int(leg["level"]) == 0:
            return False
        lvl = int(leg["level"])
        prev_opens = [r["open_time"] for r in leg_rows if int(r["level"]) == lvl - 1]
        if not prev_opens:
            prev_t = basket_start
        else:
            prev_t = min(prev_opens)
        gap_sec = (leg["open_time"] - prev_t).total_seconds()
        required = spacing_min_gap_sec * spacing_mult * lvl
        return gap_sec < required

    if max_grid_levels is not None:
        levels_blocked_from(max_grid_levels)

    for evt_time, kind, leg in events:
        if sim_pnl is not None:
            break

        if kind == "open":
            lvl = int(leg["level"])
            if lvl in blocked_levels:
                continue
            if spacing_blocks_level(leg):
                blocked_levels.add(lvl)
                continue

            if lvl > 0 and mode == "full":
                floating = basket_floating_at(open_legs, realized, evt_time)
                seconds_open = (evt_time - basket_start).total_seconds()
                dist = dist_anchor_atr_proxy(open_legs, evt_time, entry_atr)
                health = rule_health_score(
                    floating, len(open_legs), seconds_open, dist
                )
                max_health = max(max_health, health)
                action, flatten_now = apply_health_policy(
                    health,
                    len(open_legs),
                    floating,
                    seconds_open,
                    mode=mode,
                    flatten_at=flatten_at,
                    no_add_at=no_add_at,
                    flatten_float=flatten_float,
                    stress_flatten_at=stress_flatten_at,
                    hard_cap_enabled=hard_cap_enabled,
                    hard_cap_usd=hard_cap_usd,
                    hard_cap_l1_enabled=hard_cap_l1_enabled,
                    hard_cap_l1_usd=hard_cap_l1_usd,
                    hard_cap_l1_min_sec=hard_cap_l1_min_sec,
                )
                if flatten_now:
                    sim_pnl = floating
                    intervention = action
                    flatten_time = evt_time
                    break
                if action == "no_add":
                    levels_blocked_from(lvl)
                    intervention = "no_add"
                    continue

            leg_copy = dict(leg)
            if mode == "full" and tighten_active:
                leg_copy["_tighten"] = True
            open_legs.append(leg_copy)
            continue

        if kind in ("checkpoint", "close") and open_legs:
            floating = basket_floating_at(open_legs, realized, evt_time)
            seconds_open = (evt_time - basket_start).total_seconds()
            dist = dist_anchor_atr_proxy(open_legs, evt_time, entry_atr)

            if should_basket_cap(
                len(open_legs),
                floating,
                basket_cap_enabled=basket_cap_enabled,
                basket_cap_usd=basket_cap_usd,
                basket_cap_min_legs=basket_cap_min_legs,
            ):
                sim_pnl = floating
                intervention = "basket_cap"
                flatten_time = evt_time
                break

            if mode == "flatten_only":
                health = stress_health_score(floating, len(open_legs))
            else:
                health = rule_health_score(
                    floating, len(open_legs), seconds_open, dist
                )
            max_health = max(max_health, health)

            action, flatten_now = apply_health_policy(
                health,
                len(open_legs),
                floating,
                seconds_open,
                mode=mode,
                flatten_at=flatten_at,
                no_add_at=no_add_at,
                flatten_float=flatten_float,
                stress_flatten_at=stress_flatten_at,
                hard_cap_enabled=hard_cap_enabled,
                hard_cap_usd=hard_cap_usd,
                hard_cap_l1_enabled=hard_cap_l1_enabled,
                hard_cap_l1_usd=hard_cap_l1_usd,
                hard_cap_l1_min_sec=hard_cap_l1_min_sec,
            )

            if flatten_now:
                sim_pnl = floating
                intervention = action
                flatten_time = evt_time
                break

            if mode == "full":
                if action == "tighten":
                    tighten_active = True
                    if intervention == "none":
                        intervention = "tighten"
                if (
                    not trim_done
                    and TIGHTEN_THRESHOLD < health <= flatten_at
                    and len(open_legs) >= 2
                    and floating > TRIM_PROFIT_FLOOR
                ):
                    best_idx = max(
                        range(len(open_legs)),
                        key=lambda i: leg_unrealized_at(open_legs[i], evt_time),
                    )
                    best_u = leg_unrealized_at(open_legs[best_idx], evt_time)
                    if best_u > TRIM_PROFIT_FLOOR:
                        realized += best_u
                        open_legs.pop(best_idx)
                        trim_done = True
                        intervention = "trim"
                        if not open_legs:
                            sim_pnl = realized
                            break

        if kind == "close":
            lvl = int(leg["level"])
            if lvl in blocked_levels:
                continue
            open_idx = next(
                (i for i, o in enumerate(open_legs) if int(o["ticket"]) == int(leg["ticket"])),
                None,
            )
            if open_idx is None:
                continue

            legs_before = len(open_legs)
            deal_profit = float(leg["profit"])
            open_after = legs_before - 1
            remaining_float = 0.0
            if open_after > 0:
                remaining_float = sum(
                    leg_unrealized_at(o, evt_time)
                    for i, o in enumerate(open_legs)
                    if i != open_idx
                )
            if should_sl_cascade(
                legs_before,
                deal_profit,
                open_after,
                sl_cascade_enabled=sl_cascade_enabled,
                sl_cascade_min_legs=sl_cascade_min_legs,
                sl_cascade_loss_usd=sl_cascade_loss_usd,
                sl_cascade_any_partial=sl_cascade_any_partial,
                sl_cascade_stack_usd=sl_cascade_stack_usd,
                sl_cascade_use_float=sl_cascade_use_float,
                sl_cascade_float_usd=sl_cascade_float_usd,
                remaining_float=remaining_float,
            ):
                for i, o in enumerate(open_legs):
                    if i == open_idx:
                        realized += deal_profit
                    else:
                        realized += leg_unrealized_at(o, evt_time)
                sim_pnl = realized
                intervention = "sl_cascade"
                flatten_time = evt_time
                break

            closed = open_legs.pop(open_idx)
            profit = float(closed["profit"])
            if closed.get("_tighten"):
                profit *= TP_TIGHTEN_RATIO
            realized += profit

            if lvl == 0 and str(leg.get("exit_reason", "")).upper() == "SL":
                should_block = no_add_after_l0_sl
                if l0_sl_gate_fn is not None:
                    should_block = bool(l0_sl_gate_fn(leg, realized))
                elif not no_add_after_l0_sl:
                    should_block = False
                if should_block:
                    levels_blocked_from(1)
                    if intervention == "none":
                        intervention = "physics_l0_sl_gate" if l0_sl_gate_fn else "no_add_after_l0_sl"

            if not open_legs:
                sim_pnl = realized

    if sim_pnl is None:
        active = [r for r in leg_rows if int(r["level"]) not in blocked_levels]
        sim_pnl = float(sum(r["profit"] for r in active))

    return ReplayResult(
        basket_key=basket_key,
        sim_pnl=sim_pnl,
        baseline_pnl=baseline_pnl,
        max_health=max_health,
        intervention=intervention,
        blocked_levels=sorted(blocked_levels),
        flatten_time=flatten_time,
    )


def simulate_health_replay(
    baskets: pd.DataFrame,
    legs: pd.DataFrame,
    *,
    mode: HealthMode = "flatten_only",
    flatten_at: float = 88.0,
    no_add_at: float = 55.0,
    checkpoint_sec: int = 60,
    flatten_float: float = -18.0,
    stress_flatten_at: float = STRESS_FLATTEN_THRESHOLD,
    hard_cap_enabled: bool = True,
    hard_cap_usd: float = -25.0,
    hard_cap_l1_enabled: bool = True,
    hard_cap_l1_usd: float = -28.0,
    hard_cap_l1_min_sec: float = 30.0,
    basket_cap_enabled: bool = True,
    basket_cap_usd: float = -32.0,
    basket_cap_min_legs: int = 1,
    sl_cascade_enabled: bool = True,
    sl_cascade_min_legs: int = 2,
    sl_cascade_any_partial: bool = False,
    sl_cascade_loss_usd: float = -9.0,
    sl_cascade_stack_usd: float = -28.0,
    sl_cascade_use_float: bool = False,
    sl_cascade_float_usd: float = -8.0,
) -> pd.DataFrame:
    """Run event replay for all baskets; return baskets frame with sim columns."""
    out = baskets.sort_values("open_time").copy()
    results: dict[str, ReplayResult] = {}

    for basket_key, grp in legs.groupby("basket_key", sort=False):
        results[basket_key] = replay_basket(
            grp,
            mode=mode,
            flatten_at=flatten_at,
            no_add_at=no_add_at,
            checkpoint_sec=checkpoint_sec,
            flatten_float=flatten_float,
            stress_flatten_at=stress_flatten_at,
            hard_cap_enabled=hard_cap_enabled,
            hard_cap_usd=hard_cap_usd,
            hard_cap_l1_enabled=hard_cap_l1_enabled,
            hard_cap_l1_usd=hard_cap_l1_usd,
            hard_cap_l1_min_sec=hard_cap_l1_min_sec,
            basket_cap_enabled=basket_cap_enabled,
            basket_cap_usd=basket_cap_usd,
            basket_cap_min_legs=basket_cap_min_legs,
            sl_cascade_enabled=sl_cascade_enabled,
            sl_cascade_min_legs=sl_cascade_min_legs,
            sl_cascade_any_partial=sl_cascade_any_partial,
            sl_cascade_loss_usd=sl_cascade_loss_usd,
            sl_cascade_stack_usd=sl_cascade_stack_usd,
            sl_cascade_use_float=sl_cascade_use_float,
            sl_cascade_float_usd=sl_cascade_float_usd,
        )

    out["sim_pnl"] = [
        results[k].sim_pnl if k in results else float(pnl)
        for k, pnl in zip(out["basket_key"], out["basket_pnl"])
    ]
    out["health_score"] = [
        results[k].max_health if k in results else 0.0 for k in out["basket_key"]
    ]
    out["health_intervention"] = [
        results[k].intervention if k in results else "none" for k in out["basket_key"]
    ]
    out["health_blocked_levels"] = [
        results[k].blocked_levels if k in results else [] for k in out["basket_key"]
    ]
    return out


def simulate_health_legacy(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Deprecated post-hoc PnL cap (hindsight). Kept for regression comparison."""
    out = df.sort_values("open_time").copy()
    no_add = cfg["thresholds"]["health_no_add"]
    flatten = cfg["thresholds"]["health_flatten"]
    sim_pnls = []
    scores = []

    for _, row in out.iterrows():
        floating = float(min(0.0, row.get("worst_leg", 0.0)))
        open_count = int(row.get("max_level", 1))
        seconds_open = float(row.get("hold_sec", 0))
        atr = float(row.get("entry_atr", 0.0001) or 0.0001)
        dist = float(abs(row.get("worst_leg", 0.0)) / atr)

        h = rule_health_score(floating, open_count, seconds_open, dist)
        pnl = float(row["basket_pnl"])
        if int(row.get("max_level", 1)) >= 2:
            if h > flatten and pnl < 0:
                pnl = max(pnl, -20.0)
            elif h > no_add and bool(row.get("tail_loss", False)):
                pnl = float(min(0.0, row.get("worst_leg", pnl)))
        sim_pnls.append(pnl)
        scores.append(h)

    out["sim_pnl"] = sim_pnls
    out["health_score"] = scores
    out["health_intervention"] = "legacy"
    return out
