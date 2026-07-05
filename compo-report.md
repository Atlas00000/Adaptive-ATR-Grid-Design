# AAG Composition Report

**Adaptive ATR Grid — Design, Build & Validation**

| | |
|---|---|
| **Project** | AAG (Adaptive ATR Grid) |
| **Platform** | MetaTrader 5 |
| **Instrument** | EURUSD M5 |
| **EA version** | 1.08 |
| **Report date** | 2026-07-05 |
| **Repository** | [Adaptive-ATR-Grid-Design](https://github.com/Atlas00000/Adaptive-ATR-Grid-Design) |
| **Production preset** | `Presets/AAG_EURUSD_M5_production.set` (LOCK-202) |

---

## 1. Executive summary

We set out to build an automated **mean-reversion grid** EA that adapts spacing to volatility (ATR), then **discover** where it has edge, **lock** a production stack, and **enhance** it systematically without breaking what works.

**What we built:**

- A modular MQL5 execution engine (**11 include modules**, state machine, basket recovery)
- A disciplined **edge-discovery pipeline** (E0–E2) that turned a −$180 / PF 0.67 baseline into a **+$623 / PF 1.46** production stack over 19 months
- **Four enhancement layers** (E3 regime, E4 grid/risk, E5 exits, E6 structure) — all coded, preset-tested, and **rejected** vs production
- **40+ Strategy Tester presets**, diagnostics CSV tooling, and full documentation trail

**Bottom line:** The edge is **real but narrow** — 15–17 server time, RSI rotation, full 6-level grid. Stable in favourable regimes; **not live-ready** on full history until E7 walk-forward validation. Production stack unchanged.

---

## 2. Origin & concept

The strategy thesis ([`concept.md`](concept.md)) is an evolution of classic grid trading:

- **Grid spacing** = ATR × multiplier (not fixed pips)
- **Edge hypothesis:** short-term rotation around temporary equilibrium during low-trend regimes
- **Not directional prediction** — profit from oscillation between ATR-spaced levels

Phase 1 scope ([`roadmap.md`](roadmap.md)) was execution-only: indicators, grid math, risk gates, basket TP, restart recovery. Discovery and enhancement came after the engine worked.

---

## 3. What we built — software composition

### 3.1 Repository layout

```text
AAG/
├── AAG.mq5                 Expert advisor orchestrator (v1.08)
├── AAG.mqproj              MetaEditor project file
├── Include/
│   ├── Utils.mqh           All inputs, enums, structs, helpers
│   ├── Logger.mqh          Structured logging
│   ├── ATREngine.mqh       ATR / EMA / ADX handles, frozen grid distance
│   ├── SignalEngine.mqh    EMA slope + ADX gate + E2 entry filters
│   ├── GridEngine.mqh      Anchor, level prices, add triggers
│   ├── StateMachine.mqh    Basket lifecycle states
│   ├── BasketManager.mqh   Basket TP, E5 exits, E4 MAE, recovery
│   ├── RiskManager.mqh     Session, spread, cooldown, sizing, E4 caps
│   ├── TradeManager.mqh    CTrade execution, SL/TP, retry
│   ├── RegimeGate.mqh      Phase E3 regime gates
│   ├── StructureGate.mqh   Phase E6 structure filters
│   └── Diagnostics.mqh     CSV trade journal (E0)
├── Presets/                40+ .set files (production + test matrix)
├── Docs/
│   └── E0-run-guide.md     Diagnostics run guide
├── concept.md              Strategy thesis
├── roadmap.md              Phase 1 implementation roadmap
├── Edge Discovery.md       Full discovery + enhancement log
├── system-profile.md       Consolidated system / edge / trade profile
└── compo-report.md         This document
```

### 3.2 Architecture

```
OnTick
  ├─ ProcessTradeManagement()     every tick — basket TP, E5/E4 exits, sync
  ├─ ProcessGridLevels()          every tick — add L1–L5 when price hits level
  └─ ProcessSignals()             new closed bar only
       ├─ SignalEngine.Evaluate()     EMA + ADX + RSI filter
       ├─ RegimeGate.AllowNewBasket() E3 (off in production)
       ├─ StructureGate.AllowNewBasket() E6 (off in production)
       ├─ RiskManager gates
       └─ TradeManager.OpenFirstLevel()
```

**State machine:** `IDLE → ARMED → GRID_ACTIVE → MANAGING → EXITING → COOLDOWN`

**Design principles:**

- Signals on **closed bars only**; trade management every tick
- **One direction** per basket; opposite bias blocked while basket open
- **Frozen ATR distance** on basket open — grid spacing locked for basket lifetime
- **Restart recovery** — rebuilds basket from open positions on EA reload
- **Modular enhancement** — each phase adds inputs + one `.mqh`; production has all features **off**

### 3.3 Version history

| Version | Phase | Added |
|---|---|---|
| v1.00–1.02 | Phase 1 | Core execution engine |
| v1.03 | E2 | Entry filter enum + SignalEngine filters |
| v1.04 | E2 | RSI rotation thresholds (≤48 / ≥45) |
| v1.05 | E5 | Basket trail, MR EMA exit, adaptive TP, time stop |
| v1.06 | E4 | Basket DD cap, MAE exit, adaptive depth, scaled lots |
| v1.07 | E3 | Regime gates (ATR pause, ADX slope, seasonal, chop, combo) |
| v1.08 | E6 | Structure gates (PD H/L, session H/L, liq sweep, range-mid anchor) |

---

## 4. Discovery journey (E0–E2)

### 4.1 Starting point — EDGE-000 baseline

| Metric | Value |
|---|---|
| Net | −$180 |
| PF | 0.67 |
| WR | 47.6% |
| Equity DD | 90% |
| Trades | 250 |

**Diagnosis:** The EA found rotational moves (MFE corr 0.84) but entries were too permissive, grid stacked into trends, R:R inverted (SL 2×ATR > TP 1.5×ATR), and 24h trading included toxic session hours.

### 4.2 Phase E0 — Diagnostics

- Built CSV trade journal (`Diagnostics.mqh`)
- Tagged closes by reason (SL, TP, basket)
- Enabled D1/D2 depth analysis — proved **D2 grid adds were 93% of losses** on unfiltered runs

### 4.3 Phase E1 — Session search

Tested London core, hour blacklist, overlap windows, day filters.

**Winner:** **EDGE-104-402** — hours **15–17 only**

| Metric | 15–17 | Full session |
|---|---|---|
| Net | +$174 | −$112 |
| PF | 1.23 | < 1.0 |
| Equity DD | 25% | 71% |

Session refinement — not grid depth reduction — flipped the strategy profitable.

### 4.4 Phase E2 — Entry filters

| ID | Filter | Result |
|---|---|---|
| EDGE-201 | BB rejection | PF 2.61 but only 22 trades — over-filtered |
| **EDGE-202** | **RSI rotation** | **PF 1.93, +$273, 96 trades — WINNER** |
| EDGE-203 | BB + RSI combo | 18 trades — rejected |
| EDGE-204 | HTF EMA align | Long WR still 51% — rejected |
| EDGE-205 | EMA distance | 0 trades — rejected |

**Locked stack v2 — LOCK-202:**

| Layer | Setting |
|---|---|
| Session | 15–17 |
| Entry | RSI buy ≤48, sell ≥45 |
| Grid | 6 levels, ATR × 1.5 |
| SL / TP | 2.0× / 1.5× ATR |
| Lot | 0.10 fixed |

---

## 5. Enhancement programme (E3–E6)

All enhancements inherit LOCK-202 and change **one layer**. Tested on Jan–Jul 2025, Jan 2025–Jul 2026, and longest window. **None promoted.**

### 5.1 Phase E5 — Exit & trade management

| ID | Change | Extended result | Verdict |
|---|---|---|---|
| EDGE-501 | R:R flip SL 1.5 / TP 2 | Better avg W/L; PF below prod | Reserve only |
| EDGE-502 | Basket TP $12–$25 | = production | Rejected |
| EDGE-504 | Trail basket 50% @ $12 | −$234 net vs prod | Rejected |
| EDGE-505 | MR exit at EMA | Catastrophic (−$180, 90% DD) | Hard reject |
| EDGE-506 | Adaptive basket TP | −$400 net | Rejected |
| EDGE-507 | Time stop 90 min | 62% DD | Rejected |

**Lesson:** Basket-level exits clip winners or fight the entry logic. Per-leg SL/TP remains production exit path. Basket TP $50 **never fires**.

### 5.2 Phase E4 — Grid & risk containment

| ID | Change | Extended result | Verdict |
|---|---|---|---|
| EDGE-402 | Adaptive depth ADX≥25 | = production (never fires) | No effect |
| EDGE-403 | Basket DD cap 2% | −$279 net | Rejected |
| EDGE-404 | Scaled lots 0.85^level | −$58 net | Rejected |
| EDGE-405 | MAE exit 4×ATR | PF 1.0, 79% DD | Hard reject |

**Lesson:** Deep grid is part of the edge in 15–17. Blunt caps remove profitable recovery trades.

### 5.3 Phase E3 — Regime gates

| ID | Change | Extended result | Verdict |
|---|---|---|---|
| EDGE-302 | ATR pause 1.8× | = production | Inert |
| EDGE-301 | ADX slope 3 bars | −$28 net, DD worse | Rejected |
| EDGE-303 | ATR 80th percentile | −$316 net, 36% DD | Rejected |
| EDGE-304 | Chop 3+ EMA crosses | −$373 net, 4 longs | Rejected |
| EDGE-305 | Combo 301+302 | = EDGE-301 | Rejected |
| EDGE-306 | Skip Jun–Sep | −$264 net, 41% DD | Hard reject |

**Lesson:** Over-filtering destroys volume. Seasonal skip removed profitable summer pocket.

### 5.4 Phase E6 — Structure & liquidity

| ID | Change | Extended result | Verdict |
|---|---|---|---|
| EDGE-601 | Prior day H/L | 38 trades, −$463 net, 49% DD | Hard reject |
| EDGE-602 | Session H/L | 32 trades, −$469 net, 46% DD | Hard reject |
| EDGE-603 | Liquidity sweep | 7 trades, −$543 net | Hard reject |
| EDGE-604 | Range-mid anchor | 369 trades, −$101 net, 42% DD | Rejected |

**Lesson:** Structural boundary filters are too strict at 15–17 entry. Anchor shift misaligns grid geometry without lifting net.

---

## 6. Production performance

*Preset: `AAG_EURUSD_M5_production.set` · $200 deposit · variable spread · **equity DD only***

### 6.1 Multi-horizon summary

| Window | Net | PF | WR | Trades | Equity DD | Avg win / loss |
|---|---|---|---|---|---|---|
| **Jan–Jul 2025** | +$273 | **1.93** | **72%** | 96 | **12.4%** | +$8.22 / −$10.90 |
| **Jan 2025 – Jul 2026** | **+$623** | **1.46** | **66%** | **324** | **23.0%** | +$9.30 / −$12.42 |
| **Longest available** | −$192 | 0.95 | 56% | 581 | **98%** | +$10.88 / −$14.76 |

### 6.2 Trade profile

**Winners:** rotation within ATR band, 1–2 grid levels, 15–17 session, shorts ~80% of volume (WR 67–74%), MFE correlation **0.86**, avg hold ~1h 45m.

**Losers:** deep grid stack into trend, inverted R:R (avg loss > avg win), fat tails on longest test (largest loss **−$66**), short WR collapse 72% → 55%, max 6 consecutive losses.

### 6.3 Stability assessment

| Horizon | Assessment |
|---|---|
| 7 months | **Strong** — discovery sweet spot |
| 19 months | **Stable profitable** — medium regime |
| Full history | **Fails** — tail risk dominates |

See [`system-profile.md`](system-profile.md) for full system, edge, and risk profiles.

---

## 7. Preset inventory

| Category | Count | Examples |
|---|---|---|
| **Production** | 1 | `AAG_EURUSD_M5_production.set` |
| **Discovery E0–E2** | ~15 | EDGE-000, EDGE-001, EDGE-104-402, EDGE-202 |
| **Enhancement E3** | 6 | EDGE-301–306 |
| **Enhancement E4** | 5 | EDGE-401–405 |
| **Enhancement E5** | 10 | EDGE-501–507, basket TP variants |
| **Enhancement E6** | 4 | EDGE-601–604 |

Presets live in `Presets/`; copies for Strategy Tester in `MQL5/Profiles/Tester/`. See [`Presets/README.md`](Presets/README.md).

---

## 8. Documentation deliverables

| Document | Purpose |
|---|---|
| [`concept.md`](concept.md) | Original AAG strategy thesis |
| [`roadmap.md`](roadmap.md) | Phase 1 build roadmap and module matrix |
| [`Edge Discovery.md`](Edge Discovery.md) | Complete test log, metrics, verdicts |
| [`system-profile.md`](system-profile.md) | Consolidated live system reference |
| [`compo-report.md`](compo-report.md) | This composition report |
| [`Docs/E0-run-guide.md`](Docs/E0-run-guide.md) | Diagnostics CSV guide |
| [`Presets/README.md`](Presets/README.md) | Preset index and test order |

---

## 9. Key lessons learned

1. **Session is the highest-leverage filter** — more impact than any coded exit or structure layer.
2. **RSI rotation, not extremes** — mild thresholds (≤48/≥45) preserve volume; strict filters zero trades.
3. **Full grid depth works** in the right window — max1 and depth caps hurt more than they help.
4. **WR-driven economics** — profitability depends on win rate, not R:R; avg loss > avg win is structural.
5. **Basket TP is decorative** at $50 — all real exits are per-leg SL/TP.
6. **Enhancement discipline pays off** — 20+ variants tested systematically; none beat production, avoiding regression.
7. **Regime stationarity is limited** — PF decays 1.93 → 1.46 → 0.95 as sample lengthens.
8. **Over-filtering is the recurring failure mode** — E3, E6, and strict E2 filters all die by trade starvation.

---

## 10. What remains — Phase E7

| Task | ID | Gate |
|---|---|---|
| Walk-forward (3m train / 1m test) | EDGE-702 | ≥ 3/4 windows pass |
| Monte Carlo trade shuffle | EDGE-703 | DD tail risk |
| Longest-window stress | — | PF ≥ **1.1** |
| Live gate | — | 19-mo equity DD < **25%** |

**Production stack is locked.** No further enhancement coding until E7 defines whether the edge survives out-of-sample.

---

## 11. How to use this repository

### Compile & run

1. Open `AAG.mqproj` in MetaEditor
2. Compile **AAG.mq5** (target: v1.08, 0 errors)
3. Strategy Tester → load `AAG_EURUSD_M5_production.set` from `Profiles/Tester/`
4. EURUSD M5, variable spread, $200 deposit

### Enhance (if resuming)

1. Copy `production.set`, change **one input group**
2. Compare vs production on Jan–Jul 2025 + Jan 2025–Jul 2026 + longest
3. Log results in `Edge Discovery.md`

### Deploy (not yet)

Live deployment **not approved** until E7 gates pass. Paper trade production preset only.

---

## 12. Composition scorecard

| Area | Status |
|---|---|
| Execution engine | **Complete** (v1.08) |
| Edge discovery | **Complete** (LOCK-202) |
| Enhancement matrix | **Complete** (E3–E6, all rejected) |
| Documentation | **Complete** |
| Validation (E7) | **Pending** |
| Live readiness | **Not met** |

---

*AAG — Adaptive ATR Grid Design · Built and validated July 2026*
