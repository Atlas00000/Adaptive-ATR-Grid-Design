# AAG System Profile

*Adaptive ATR Grid — EURUSD M5 — production stack LOCK-202*

**Last updated:** 2026-07-05  
**EA version:** 1.08  
**Canonical preset:** `AAG_EURUSD_M5_production.set` (= `EDGE-LOCK-202_15-17-rsi`)  
**Status:** Discovery + enhancement **complete**; production **stable** in favourable regime; **not live-ready** on full history without E7 validation.

---

## Executive summary

AAG is a **mean-reversion grid EA** that exploits short-term rotational price action during the US–London overlap, gated by low trend strength (ADX) and mild EMA structure. The locked production stack trades **only hours 15–17** server time with an **RSI rotation filter**, using **ATR-adaptive grid spacing** and **per-leg SL/TP** (not basket-driven exits).

The system is **profitable and stable** over Jan 2025 – Jul 2026 (PF 1.46, equity DD 23%) but **degrades on the longest available history** (PF 0.95, equity DD 98%). Enhancement phases E3–E6 tested 20+ variants; **none beat production**. The edge is real, narrow, and **regime-dependent** — not a universal grid.

---

## 1. System profile

### 1.1 Identity

| Field | Value |
|---|---|
| Name | AAG (Adaptive ATR Grid) |
| Platform | MetaTrader 5 |
| Symbol / TF | **EURUSD M5** (single-chart, single-symbol) |
| Style | Intraday mean-reversion grid |
| Direction | One basket at a time (all buy or all sell) |
| Magic | `20260705` |

### 1.2 Architecture (v1.08)

```
AAG.mq5
├── StateMachine.mqh      IDLE → ARMED → GRID_ACTIVE → MANAGING → EXITING → COOLDOWN
├── ATREngine.mqh         ATR(14), EMA(50), ADX(14); frozen grid distance on basket open
├── SignalEngine.mqh      EMA slope + ADX gate + E2 RSI filter
├── GridEngine.mqh        Anchor, level prices, add triggers
├── BasketManager.mqh     Basket TP, E5 exits, E4 MAE exit, recovery
├── RiskManager.mqh       Session, spread, cooldown, sizing, E4 depth/lot caps
├── TradeManager.mqh      CTrade execution, SL/TP attach, retry
├── RegimeGate.mqh        E3 gates (off in production)
├── StructureGate.mqh     E6 structure filters (off in production)
├── Diagnostics.mqh       Optional CSV journal (off in production)
└── Utils.mqh             All inputs and types
```

**Tick flow:** trade management every tick → grid adds every tick → signals on **new closed bar only**.

### 1.3 Production stack — LOCK-202

| Layer | Setting | Notes |
|---|---|---|
| **Session (E1)** | Hours **15–17** | Overlap core; do not widen |
| **Entry (E2)** | RSI rotation — buy ≤48, sell ≥45 | Winner over BB, HTF EMA, EMA distance |
| **Signal base** | EMA(50) slope/flat + ADX(14) < 20 | Rotation, not trend |
| **Grid** | Max **6** levels, spacing = ATR × **1.5** | Full depth validated; max1 rejected |
| **Sizing** | Fixed **0.10** lot | |
| **SL / TP** | **2.0×ATR** / **1.5×ATR** per leg | WR-driven; avg loss > avg win |
| **Basket TP** | **$50** money target | **Never fires** in practice; per-leg closes first |
| **Cooldown** | **20** min after basket close | |
| **Spread cap** | **2.0** pips | |
| **E3 regime** | All **off** | Tested; no promotion |
| **E4 grid/risk** | All **off** | Tested; no promotion |
| **E5 exits** | All **off** | Tested; no promotion |
| **E6 structure** | All **off** | Tested; no promotion |

### 1.4 State machine

| State | Behaviour |
|---|---|
| **IDLE** | Wait for signal on new bar |
| **ARMED** | Signal fired; pending first entry |
| **GRID_ACTIVE** | Level 0 open; monitoring adds L1–L5 |
| **MANAGING** | Max levels filled or no more triggers |
| **EXITING** | Basket close in progress |
| **COOLDOWN** | Timer blocks new baskets |

Restart recovery rebuilds open basket from positions (magic + symbol).

---

## 2. Edge profile

### 2.1 Hypothesis

The edge lives in **quiet rotational microstructure**: moderate ATR, flat or mildly sloped EMA, ADX below threshold, two-way auction during the **15–17 overlap**. Profit comes from **high win rate** on shallow grid legs, not favourable R:R.

The system **bleeds** during session transitions, volatility expansion, deep grid stacking into trends, and regimes where short-side WR collapses.

### 2.2 Validated pocket (do not re-test)

| Dimension | Finding |
|---|---|
| **When** | **15–17** server time only |
| **Entry** | RSI rotation (not extremes ≤35/≥65) |
| **Grid depth** | 6 levels; conditional max1 rejected |
| **Direction** | Short-heavy (~80% volume); longs minority but profitable with RSI |
| **Exits** | Per-leg SL/TP; basket TP $50 inert |
| **Filters rejected** | BB, HTF EMA, EMA distance, all E3–E6 enhancements |

### 2.3 Regime map

| Regime | Performance | Mechanism |
|---|---|---|
| **Jan–May** | Strongest | High activity (~35–40 trades/mo), best gross profit |
| **Jun–Dec** | Weaker | Activity flattens; H2 net softens |
| **15–17 hours** | All entries | Preset window + bar-close timing → 15–18 cluster |
| **Expansion / transitions** | Bleed | Hours 9, 16, 18–22 historically toxic (pre-LOCK) |
| **Long history** | Fails | Fat tails (−$66 largest loss); short WR 72% → 55% |

### 2.4 Horizon decay

| Window | PF | WR | Equity DD | Trades | Net ($200) |
|---|---|---|---|---|---|
| **Jan–Jul 2025** (7 mo) | **1.93** | **72%** | **12.4%** | **96** | **+$273** |
| **Jan 2025 – Jul 2026** (19 mo) | **1.46** | **66%** | **23.0%** | **324** | **+$623** |
| **Longest available** | **0.95** | **56%** | **98%** | **581** | **−$192** |

Edge is **stationary within favourable regimes** but **not robust** across full history without tail control.

### 2.5 Enhancement outcome (E3–E6)

All tested layers **failed to beat production** on net + equity DD while preserving trade volume:

| Phase | Tests | Outcome |
|---|---|---|
| **E5** exits | Trail, MR EMA, adaptive TP, time stop, R:R flip | Rejected (clips winners or kills edge) |
| **E4** grid/risk | DD cap, MAE exit, adaptive depth, scaled lots | Rejected (blunt caps hurt net) |
| **E3** regime | ATR pause, ADX slope, seasonal, chop, combo | Rejected (inert or over-filters) |
| **E6** structure | PD H/L, session H/L, liq sweep, range-mid anchor | Rejected (over-filter or DD blowout) |

**Reserve candidate:** EDGE-501 (R:R flip) — better per-trade economics (+$10.88 / −$8.18) but lower headline PF; not adopted.

---

## 3. Trade profile

### 3.1 Winner profile (LOCK-202)

| Characteristic | Evidence |
|---|---|
| **Rotation within ATR band** | MFE correlation **0.84–0.88** — price moves favourably before TP |
| **Low trend pressure** | ADX < 20 at entry; EMA flat or mild slope |
| **Shallow grid** | 1–2 levels filled; TP hit before deep stack |
| **Session** | Entries cluster **15:00–17:00** |
| **Weekdays** | Tue / Wed / Fri relatively stronger |
| **Months** | Jan–May strongest in 19-mo run |
| **Direction** | Shorts dominate volume with **higher WR** (~67–74%) |
| **Hold time** | Avg **~1h 45m–1h 50m** (production window) |

### 3.2 Loser profile (LOCK-202)

| Characteristic | Evidence |
|---|---|
| **Adverse excursion then SL** | MAE correlation **0.79–0.83**; little recovery past ~4 ATR units |
| **Deep grid stack** | Multiple legs stop out in one directional push |
| **Inverted R:R** | Avg loss **>** avg win at all horizons |
| **Fat tails (longest test)** | Largest loss **−$66**; avg loss −$14.76 vs avg win +$10.88 |
| **Short WR collapse** | 72% (7 mo) → **55%** (longest) — more bad regimes in sample |
| **Consecutive losses** | Max **6** (−$75.60) on 19-mo; **6** on longest |
| **Basket TP** | **0** historical basket TP exits — deep baskets die by per-leg SL |

### 3.3 Direction split (production)

| Horizon | Short trades | Short WR | Long trades | Long WR |
|---|---|---|---|---|
| Jan–Jul 2025 | ~82 (85%) | **72%** | ~14 (15%) | **71%** |
| Jan 25 – Jul 26 | ~261 (81%) | **~67%** | ~63 (19%) | **~60%** |
| Longest | ~520 (90%) | **55%** | ~61 (10%) | **69%** |

Shorts carry volume and edge; longs are fewer but RSI filter made them viable. Extended history erodes **short WR**, not long WR.

### 3.4 Exit anatomy

| Exit type | Role |
|---|---|
| **Per-leg TP** (1.5×ATR) | Primary win path |
| **Per-leg SL** (2.0×ATR) | Primary loss path; larger than TP |
| **Basket TP** ($50) | Configured but **never reached** before legs close |
| **E5 coded exits** | Tested; all rejected vs production |

### 3.5 Grid depth

| Depth | Pattern |
|---|---|
| **L0–L1** | Majority of winners; fast rotation |
| **L2–L5** | Tail risk — stacked SLs wipe many small wins |
| **Max1 (rejected)** | 314 singles at 52% WR — worse than full grid in session |

---

## 4. Current performance

*Production preset, variable spread, $200 initial deposit. **Equity drawdown only** (balance ignored).*

### 4.1 Headline metrics — three horizons

| Metric | Jan–Jul 2025 | Jan 25 – Jul 2026 | Longest test |
|---|---|---|---|
| **Net profit** | +$273 | **+$623** | −$192 |
| **Profit factor** | **1.93** | **1.46** | 0.95 |
| **Win rate** | **72%** | **66%** | 56% |
| **Total trades** | 96 | **324** | 581 |
| **Equity DD (max)** | **12.4%** | **23.0%** | **98%** |
| **Avg win / avg loss** | +$8.22 / −$10.90 | +$9.30 / −$12.42 | +$10.88 / −$14.76 |
| **Largest loss** | ~−$12 | ~−$16 | **−$66** |
| **Max consec losses** | 3 | 6 | 6 |
| **Expectancy / trade** | +$2.84 | +$1.92 | −$0.33 |
| **Avg hold** | ~1h 49m | ~1h 45m | — |

### 4.2 Quality ratios (19-month reference)

| Ratio | Value | Interpretation |
|---|---|---|
| **Profit factor** | 1.46 | Gross profit / gross loss — positive |
| **Recovery factor** | ~3.9 (typical run) | Net / max equity DD — moderate |
| **Sharpe** | ~7–8 (typical run) | High on favourable windows; misleading on longest |
| **Corr(profit, MFE)** | **0.86** | Winners capture favorable excursion |
| **Corr(profit, MAE)** | **0.79–0.83** | Losers show adverse excursion before SL |

### 4.3 Monthly rhythm (19-month)

| Period | Pattern |
|---|---|
| **Jan–May** | Peak activity and net contribution |
| **Jun–Sep** | Softer; still net-positive in production (seasonal skip rejected) |
| **Oct–Dec** | Lower activity; mixed months |

### 4.4 Stability assessment

| Aspect | Assessment |
|---|---|
| **Short window (7 mo)** | **Strong** — PF 1.93, DD 12% |
| **Medium window (19 mo)** | **Stable profitable** — PF 1.46, DD 23% |
| **Full history** | **Unstable** — PF < 1, DD catastrophic |
| **Parameter sensitivity** | Session + RSI locked; widening filters consistently hurts |
| **Code maturity** | v1.08; E3/E4/E5/E6 wired but disabled in production |

---

## 5. Key metrics dashboard

*Single reference card for LOCK-202 / production.*

```
┌─────────────────────────────────────────────────────────────┐
│  AAG LOCK-202 — EURUSD M5 — Production                      │
├─────────────────────────────────────────────────────────────┤
│  Session        15–17 server  │  Grid        6 × ATR×1.5    │
│  Entry          RSI ≤48 / ≥45 │  Lot         0.10 fixed     │
│  SL / TP        2.0 / 1.5 ATR│  Basket TP   $50 (inactive)  │
├─────────────────────────────────────────────────────────────┤
│  19-MONTH (Jan 25 – Jul 26)                                 │
│  Net +$623  │  PF 1.46  │  WR 66%  │  Trades 324            │
│  Equity DD 23%  │  Avg W/L +$9.30 / −$12.42                 │
├─────────────────────────────────────────────────────────────┤
│  7-MONTH (Jan–Jul 2025)                                     │
│  Net +$273  │  PF 1.93  │  WR 72%  │  Trades 96             │
│  Equity DD 12.4%                                            │
├─────────────────────────────────────────────────────────────┤
│  LONGEST STRESS                                             │
│  Net −$192  │  PF 0.95  │  WR 56%  │  Equity DD 98%         │
│  Largest loss −$66  │  Short WR 55%                           │
├─────────────────────────────────────────────────────────────┤
│  LIVE GATE (not met)                                        │
│  Longest PF ≥ 1.1  │  19-mo DD < 25%  │  Walk-forward E7    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Risk profile

| Risk | Severity | Mitigation status |
|---|---|---|
| **Inverted per-leg R:R** | High | E5 tested — no fix adopted |
| **Deep grid tail** | High | E4 tested — caps hurt net |
| **Regime decay** | High | E3 tested — filters over-prune |
| **Short WR collapse** | Medium | Locked session helps; degrades on long history |
| **Basket TP unreachable** | Medium | Known; all closes per-leg |
| **Spread / slippage** | Low | 2 pip cap; variable spread in tests |
| **Single symbol** | Medium | By design Phase 1 |

---

## 7. Live readiness

| Gate | Target | Current (19 mo) | Longest |
|---|---|---|---|
| Profit factor | ≥ 1.1 | **1.46** ✓ | **0.95** ✗ |
| Equity DD | < 25% | **23%** ✓ | **98%** ✗ |
| Net profit | Positive | **+$623** ✓ | **−$192** ✗ |
| Walk-forward | ≥ 3/4 windows | **Not run** | — |
| Enhancement stack | Promoted winner | **None** — LOCK-202 only | |

**Verdict:** Suitable for **continued paper / segmented validation** (E7). **Not approved for live** until longest-window PF ≥ 1.1 and tail losses capped.

---

## 8. File reference

| File | Purpose |
|---|---|
| `AAG.mq5` | Expert advisor (v1.08) |
| `Presets/AAG_EURUSD_M5_production.set` | Canonical production inputs |
| `Edge Discovery.md` | Full test log and enhancement history |
| `concept.md` | Original strategy thesis |
| `roadmap.md` | Phase 1 implementation roadmap |
| `Presets/README.md` | Preset index and test order |

---

*This document is the consolidated system profile. Update after E7 walk-forward or any production stack change.*
