"""AI-807: Causal exit-policy replay on top of 805p health stack."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal

import pandas as pd

from basket_replay import (
    ReplayResult,
    _event_sort_key,
    apply_health_policy,
    basket_floating_at,
    dist_anchor_atr_proxy,
    leg_unrealized_at,
    rule_health_score,
    should_basket_cap,
    should_sl_cascade,
    stress_health_score,
    TIGHTEN_THRESHOLD,
    TRIM_PROFIT_FLOOR,
    TP_TIGHTEN_RATIO,
)

ExitPolicyName = Literal["none", "partial_l0_1r", "dynamic_tp", "runner_lock", "combined"]


@dataclass
class ExitPolicyConfig:
    name: ExitPolicyName = "none"
    partial_health_threshold: float = 40.0
    partial_fraction: float = 0.50
    min_one_r_usd: float = 6.0
    base_tp_atr: float = 1.5
    edge_tp_scale: float = 0.5
    weak_edge_cutoff: float = 0.50
    early_capture_r: float = 0.90
    runner_activate_usd: float = 10.0
    runner_lock_usd: float = 8.0


def estimate_one_r(l0_leg: dict, *, min_one_r_usd: float = 6.0) -> float:
    """Proxy 1R in USD from final leg outcome (TP≈1.5R, SL≈2R)."""
    final = float(l0_leg["profit"])
    mag = abs(final)
    if mag <= 0:
        return min_one_r_usd
    if final > 0:
        return max(min_one_r_usd, mag / 1.5)
    return max(min_one_r_usd, mag / 2.0)


def entry_edge_score(l0_leg: dict) -> float:
    """Leak-free open proxy: ADX strength scaled 0–1 (matches 807 research spec)."""
    adx = float(l0_leg.get("adx", 20.0))
    return min(1.0, max(0.0, adx / 35.0))


def apply_exit_at_checkpoint(
    *,
    policy: ExitPolicyConfig,
    open_legs: list[dict],
    realized: float,
    evt_time: pd.Timestamp,
    entry_atr: float,
    health: float,
    mode: str,
    seconds_open: float,
) -> tuple[float, str | None, float | None]:
    """Return (realized, intervention, sim_pnl_if_flatten)."""
    if not open_legs or policy.name == "none":
        return realized, None, None

    floating = basket_floating_at(open_legs, realized, evt_time)
    l0_rows = [l for l in open_legs if int(l["level"]) == 0]
    l0 = l0_rows[0] if l0_rows else open_legs[0]
    one_r = estimate_one_r(l0, min_one_r_usd=policy.min_one_r_usd)
    edge = entry_edge_score(l0)
    active = policy.name

    if active in ("partial_l0_1r", "combined"):
        if len(open_legs) == 1 and int(open_legs[0]["level"]) == 0:
            if health < policy.partial_health_threshold:
                l0_u = leg_unrealized_at(open_legs[0], evt_time)
                if l0_u >= one_r and not open_legs[0].get("_partial_done"):
                    take = l0_u * policy.partial_fraction
                    realized += take
                    open_legs[0]["_partial_done"] = True
                    open_legs[0]["_profit_scale"] = 1.0 - policy.partial_fraction
                    return realized, "partial_l0_1r", None

    if active in ("dynamic_tp", "combined"):
        if floating > 0 and edge < policy.weak_edge_cutoff:
            tp_mult = policy.base_tp_atr + policy.edge_tp_scale * edge
            capture_r = policy.early_capture_r * (tp_mult / policy.base_tp_atr)
            if floating >= one_r * capture_r:
                return realized, "dynamic_tp", floating

    if active in ("runner_lock", "combined"):
        peak = float(l0.get("_peak_float", 0.0))
        if floating >= policy.runner_activate_usd:
            l0["_peak_float"] = max(peak, floating)
            l0["_runner_armed"] = True
        elif l0.get("_runner_armed") and floating < policy.runner_lock_usd:
            return realized, "runner_lock", floating

    return realized, None, None


def replay_basket_exit(
    legs: pd.DataFrame,
    *,
    exit_policy: ExitPolicyConfig,
    mode: str = "flatten_only",
    flatten_at: float = 88.0,
    no_add_at: float = 55.0,
    checkpoint_sec: int = 60,
    flatten_float: float = -18.0,
    stress_flatten_at: float = 75.0,
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
    """805p health replay + optional AI-807 exit overlays at checkpoints."""
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
    exit_intervention = "none"
    flatten_time: pd.Timestamp | None = None
    sim_pnl: float | None = None

    def levels_blocked_from(level: int) -> None:
        for leg in leg_rows:
            if int(leg["level"]) >= level:
                blocked_levels.add(int(leg["level"]))

    for evt_time, kind, leg in events:
        if sim_pnl is not None:
            break

        if kind == "open":
            lvl = int(leg["level"])
            if lvl in blocked_levels:
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

            if kind == "checkpoint" and exit_policy.name != "none":
                realized, exit_act, exit_pnl = apply_exit_at_checkpoint(
                    policy=exit_policy,
                    open_legs=open_legs,
                    realized=realized,
                    evt_time=evt_time,
                    entry_atr=entry_atr,
                    health=health,
                    mode=mode,
                    seconds_open=seconds_open,
                )
                if exit_act:
                    exit_intervention = exit_act
                if exit_pnl is not None:
                    sim_pnl = exit_pnl
                    intervention = exit_intervention
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
            scale = float(closed.get("_profit_scale", 1.0))
            realized += profit * scale
            if not open_legs:
                sim_pnl = realized

    if sim_pnl is None:
        active = [r for r in leg_rows if int(r["level"]) not in blocked_levels]
        sim_pnl = float(sum(r["profit"] for r in active))

    label = intervention if exit_intervention == "none" else exit_intervention
    return ReplayResult(
        basket_key=basket_key,
        sim_pnl=sim_pnl,
        baseline_pnl=baseline_pnl,
        max_health=max_health,
        intervention=label,
        blocked_levels=sorted(blocked_levels),
        flatten_time=flatten_time,
    )


def simulate_exit_replay(
    baskets: pd.DataFrame,
    legs: pd.DataFrame,
    *,
    exit_policy: ExitPolicyConfig,
    **health_kwargs,
) -> pd.DataFrame:
    out = baskets.sort_values("open_time").copy()
    results: dict[str, ReplayResult] = {}

    for basket_key, grp in legs.groupby("basket_key", sort=False):
        results[basket_key] = replay_basket_exit(
            grp,
            exit_policy=exit_policy,
            **health_kwargs,
        )

    out["sim_pnl"] = out["basket_key"].astype(str).map(lambda k: results[k].sim_pnl)
    out["baseline_pnl"] = out["basket_key"].astype(str).map(lambda k: results[k].baseline_pnl)
    out["exit_intervention"] = out["basket_key"].astype(str).map(
        lambda k: results[k].intervention
    )
    out["lot_mult"] = 1.0
    out["trade_taken"] = True
    return out


def exit_policy_from_cfg(cfg: dict, name: ExitPolicyName) -> ExitPolicyConfig:
    ep = cfg.get("exit_policy", {})
    p = ep.get("partial_l0_1r", {})
    d = ep.get("dynamic_tp", {})
    r = ep.get("runner_lock", {})
    return ExitPolicyConfig(
        name=name,
        partial_health_threshold=float(p.get("health_threshold", 40.0)),
        partial_fraction=float(p.get("partial_fraction", 0.50)),
        min_one_r_usd=float(p.get("min_one_r_usd", 6.0)),
        base_tp_atr=float(d.get("base_tp_atr", 1.5)),
        edge_tp_scale=float(d.get("edge_tp_scale", 0.5)),
        weak_edge_cutoff=float(d.get("weak_edge_cutoff", 0.50)),
        early_capture_r=float(d.get("early_capture_r", 0.90)),
        runner_activate_usd=float(r.get("activate_float_usd", 10.0)),
        runner_lock_usd=float(r.get("lock_float_usd", 8.0)),
    )
