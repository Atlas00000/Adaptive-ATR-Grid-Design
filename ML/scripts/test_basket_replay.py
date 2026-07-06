#!/usr/bin/env python3
"""Smoke tests for causal basket health replay."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from basket_replay import replay_basket, rule_health_score


def _leg(ticket: int, level: int, profit: float, open_t: str, close_t: str) -> dict:
    return {
        "ticket": ticket,
        "level": level,
        "profit": profit,
        "atr": 0.0006,
        "open_time": pd.Timestamp(open_t),
        "close_time": pd.Timestamp(close_t),
        "basket_key": "test_1",
    }


def test_l0_unchanged() -> None:
    legs = pd.DataFrame([_leg(1, 0, 9.0, "2025-01-02 10:00", "2025-01-02 11:00")])
    r = replay_basket(legs, mode="flatten_only")
    assert r.sim_pnl == 9.0
    assert r.intervention == "none"


def test_flatten_stops_deep_loss() -> None:
    legs = pd.DataFrame(
        [
            _leg(1, 0, -12.0, "2025-01-02 10:00", "2025-01-02 14:00"),
            _leg(2, 1, -30.0, "2025-01-02 10:30", "2025-01-02 14:00"),
        ]
    )
    r = replay_basket(legs, mode="flatten_only", checkpoint_sec=30)
    assert r.intervention == "flatten"
    assert r.sim_pnl > -30.0


def test_rule_health_matches_ea_l0() -> None:
    h = rule_health_score(floating_pl=-1.0, open_count=1, seconds_open=30, dist_anchor_atr=0.5)
    assert h < 55.0


if __name__ == "__main__":
    test_l0_unchanged()
    test_flatten_stops_deep_loss()
    test_rule_health_matches_ea_l0()
    print("test_basket_replay: OK")
