# AAG Composition Report

**Adaptive ATR Grid — Design, Build & Validation**

| | |
|---|---|
| **Project** | AAG (Adaptive ATR Grid) |
| **Platform** | MetaTrader 5 |
| **Instrument** | EURUSD M5 |
| **EA version** | 1.33 (LOCK-202 non-AI · LOCK-809 AI canonical) |
| **Report date** | 2026-07-06 |
| **Repository** | [Adaptive-ATR-Grid-Design](https://github.com/Atlas00000/Adaptive-ATR-Grid-Design) |
| **Non-AI preset** | `Presets/AAG_EURUSD_M5_production.set` (**LOCK-202**) |
| **AI preset** | `Presets/AAG_EURUSD_M5_AI-809_physics-p45.set` (**LOCK-809**) |
| **Defensive AI** | `Presets/AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**) |

---

## 1. Executive summary

We set out to build an automated **mean-reversion grid** EA that adapts spacing to volatility (ATR), then **discover** where it has edge, **lock** a production stack, and **enhance** it systematically without breaking what works.

**What we built:**

- A modular MQL5 execution engine (**11 include modules**, state machine, basket recovery)
- A disciplined **edge-discovery pipeline** (E0–E2) that turned a −$180 / PF 0.67 baseline into a **+$623 / PF 1.46** production stack over 19 months
- **Four enhancement layers** (E3 regime, E4 grid/risk, E5 exits, E6 structure) — all coded, preset-tested, and **rejected** vs production
- **Phase E8 AI supervisor** (LOCK-AI) — 803 memory + 805p basket health; tail capped **−$27.40** on 2025+ wire window; **804/806/807 deferred**
- **Phase E9 adaptive geometry** (LOCK-809) — L0-SL physics gate (`physics_lr_p45`); **MT5 wire winner on $200** across all windows
- **40+ Strategy Tester presets**, ML offline pipeline (`ML/`), diagnostics CSV tooling, and full documentation trail

**Bottom line:** The edge is **real but narrow** — 15–17 server time, RSI rotation, full 6-level grid. **LOCK-202** remains **non-AI max-net** reference (PF 1.46, 23% DD over 19 mo on wire window; **$500** deposit historically needed for longest stress). **LOCK-809** is the **canonical AI preset** — profitable Jan 2022–Jul 2026 on **$200** (+$509, PF 1.11) where LOCK-202 longest bleeds (−$50). **LOCK-AI** remains optional defensive overlay (tail cap). **Not live-ready** — E7′ WF < 75%.

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
├── AAG.mq5                 Expert advisor orchestrator (v1.32)
├── AAG.mqproj              MetaEditor project file
├── Include/
│   ├── Utils.mqh           All inputs, enums, structs, helpers
│   ├── Logger.mqh          Structured logging
│   ├── ATREngine.mqh       ATR / EMA / ADX handles, frozen grid distance
│   ├── SignalEngine.mqh    EMA slope + ADX gate + E2 entry filters
│   ├── GridEngine.mqh      Anchor, level prices, add triggers
│   ├── StateMachine.mqh    Basket lifecycle states
│   ├── BasketManager.mqh   Basket TP, E5 exits, E4 MAE, SL cascade, recovery
│   ├── RiskManager.mqh     Session, spread, cooldown, sizing, E4 caps
│   ├── TradeManager.mqh    CTrade execution, SL/TP, retry
│   ├── RegimeGate.mqh      Phase E3 regime gates
│   ├── StructureGate.mqh   Phase E6 structure filters
│   ├── Diagnostics.mqh     CSV trade journal (E0)
│   ├── AISupervisor.mqh    E8 AI supervisor (803/804/805/806 policy)
│   ├── AIModelRuntime.mqh  E8 model load, version gate, ONNX path
│   ├── AIModelBundle.mqh   E8 bundle manifest (LOCK-AI tags)
│   ├── AIHealthModel.mqh   Exported LR weights (805)
│   ├── AIEntryContextModel.mqh  Exported LR weights (804, off)
│   └── AIRegimeModel.mqh   Exported LR weights (806, off)
├── ML/                     E8 offline pipeline (Python)
│   ├── scripts/            build, train, simulate, export
│   ├── models/             registry.json, joblib, optional ONNX
│   ├── export/             Strategy Tester diagnostics CSV
│   └── features/           parquet feature tables
├── Presets/                40+ .set files (production + AI + test matrix)
├── Docs/
│   └── E0-run-guide.md     Diagnostics run guide
├── concept.md              Strategy thesis
├── roadmap.md              Phase 1 implementation roadmap
├── Edge Discovery.md       Full discovery + enhancement log
├── ai_enhance.md           Phase E8 AI programme + results log
├── edgeopt.md              Edge optimisation notes
├── system-profile.md       Consolidated system / edge / trade profile
└── compo-report.md         This document
```

### 3.2 Architecture

```
OnTick
  ├─ ProcessTradeManagement()     every tick — basket TP, E5/E4 exits, AI health caps, sync
  ├─ ProcessGridLevels()          every tick — add L1–L5; AI lot/depth/health gates
  └─ ProcessSignals()             new closed bar only
       ├─ SignalEngine.Evaluate()     EMA + ADX + RSI filter
       ├─ RegimeGate.AllowNewBasket() E3 (off in production)
       ├─ StructureGate.AllowNewBasket() E6 (off in production)
       ├─ AISupervisor.AllowNewBasket() E8 memory + optional 804/806 (LOCK-AI: 803+805)
       ├─ RiskManager gates
       └─ TradeManager.OpenFirstLevel()
```

**E8 AI path (when `InpAIEnabled=true`):** `AISupervisor` scores entry at bar close, health at 60s checkpoints + tick hard caps; embedded LR by default; optional ONNX via `Files/AI/*.onnx`; version mismatch → **LOCK-202 fallback**.

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
| v1.09–v1.27 | E8 | AI-800 stub → AI-803 memory → AI-805 health iterations |
| v1.28–v1.31 | E8 | AI-804 entry context, AI-806 regime (deferred wire) |
| **v1.32** | **E8** | **AI-808 runtime** — `AIModelRuntime`, bundle manifest, ONNX infra |

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

## 6. Production performance (LOCK-202)

*Preset: `AAG_EURUSD_M5_production.set` · $200 deposit · variable spread · **equity DD only***

### 6.1 Multi-horizon summary — LOCK-202

| Window | Net | PF | WR | Trades | Equity DD | Avg win / loss |
|---|---|---|---|---|---|---|
| **Jan–Jul 2025** | +$273 | **1.93** | **72%** | 96 | **12.4%** | +$8.22 / −$10.90 |
| **Jan 2025 – Jul 2026** | **+$623** | **1.46** | **66%** | **324** | **23.0%** | +$9.30 / −$12.42 |
| **Longest available** | −$192 | 0.95 | 56% | 581 | **98%** | +$10.88 / −$14.76 |

### 6.2 AI stack performance (LOCK-AI) — v1.32, $200

*Preset: `AAG_EURUSD_M5_AI-803_memory-805p.set` · 803 memory + 805p health · see [`ai_enhance.md`](ai_enhance.md) §9.8*

| Window | Net | PF | WR | Trades | Eq DD | Largest loss | Verdict |
|---|---|---|---|---|---|---|---|
| **Jan–Jul 2025** | +$246 | **1.94** | 65% | 99 | **13%** | ~−$12 | Short sweet spot |
| **Jan 2025 – Jul 2026** | +$409 | **1.33** | 56% | 334 | 74% | **−$27.40** ✓ | **Wire window OK** |
| **From Jan 2022** | +$508 | **1.12** | 52% | 978 | 64% | **−$64.10** ✗ | Pre-2025 tail fail |

**Trade-off vs LOCK-202 (19 mo):** LOCK-AI sacrifices ~34% net (+$409 vs +$623) and higher DD (74% vs 23%) for **tail cut** (−$27 vs −$63). On 2022+ history, tail cap **breaks** — stack tuned on 2025+ regimes.

### 6.3 Trade profile

**Winners:** rotation within ATR band, 1–2 grid levels, 15–17 session, shorts ~80% of volume (WR 67–74%), MFE correlation **0.86**, avg hold ~1h 45m.

**Losers:** deep grid stack into trend, inverted R:R (avg loss > avg win), fat tails on longest test (largest loss **−$66**), short WR collapse 72% → 55%, max 6 consecutive losses.

### 6.4 Stability assessment

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
| **Production** | 1 | `AAG_EURUSD_M5_production.set` (LOCK-202) |
| **AI stack** | 3+ | `AI-803_memory-805p.set` (**LOCK-AI**), `AI-805_basket-health.set`, `AI-804_lock-ai.set` |
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
| [`ai_enhance.md`](ai_enhance.md) | Phase E8 AI programme, wire log, LOCK-AI metrics |
| [`edgeopt.md`](edgeopt.md) | Edge optimisation notes |
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
9. **AI tail guard works on 2025+** — 805p SL cascade caps largest loss at −$27.40; pre-2025 regimes still produce −$64 baskets.
10. **Exit / entry AI layers deferred** — 804, 806, 807 failed offline or MT5 gates; memory + health only in LOCK-AI.
11. **Geometry beats depth on $200** — LOCK-809 physics gate turns ext22 from −$50 (LOCK-202) to **+$509** on same deposit; simpler than full LOCK-AI stack.

---

## 10. Phase E8 — AI supervisor (summary)

| Layer | ID | Status | Role |
|---|---|---|---|
| Infrastructure | AI-800/808 | **Shipped** v1.33 | Runtime, bundle, embedded LR, optional ONNX |
| Performance memory | AI-803 | **Wired** | Lot throttle after bad rolling PF |
| Basket health | AI-805p | **Wired** | SL cascade, hard cap, stress flatten — tail −$27 |
| **Physics geometry** | **AI-809** | **Wired** v1.33 | L0-SL stack-risk gate — **canonical AI preset** |
| Entry context | AI-804 | **Deferred** | Tail fail on long window |
| Regime skip | AI-806 | **Deferred** | LR never fires at 0.85; net worse at 0.62 |
| Exit policy | AI-807 | **Research** | Early TP clips winners — defer |
| Offline sim | AI-810 | **Shipped** | Causal basket replay in `ML/scripts/` |

**Canonical AI preset:** `AAG_EURUSD_M5_AI-809_physics-p45.set` (**LOCK-809**). Defensive overlay: `AI-803_memory-805p.set` (**LOCK-AI**). Full detail: [`ai_enhance.md`](ai_enhance.md) §9.15.

---

## 11. E7 / E9 validation — COMPLETE (FAIL) · LOCK-809 wire PASS

| Task | ID | Gate | Result (2026-07-06) |
|---|---|---|---|
| Walk-forward (3m / 1m) | EDGE-702 | ≥75% folds | **FAIL** — LOCK-202: 11/16 w02; physics_p45: 62%/54% |
| Monte Carlo shuffle | EDGE-703 | DD tail | **PASS** — actual DD ≤ MC p95 on wire windows |
| Longest-window stress | — | PF ≥ 1.1 | **FAIL** offline; **LOCK-809 MT5 ext22 PF 1.11** ✓ |
| LOCK-AI / LOCK-809 ext22 tail | — | < −$35 | **FAIL** — MT5 −$64.10 |

### MT5 wire — LOCK-809 ($200, v1.33)

| Window | Net | PF | Eq DD | Largest loss |
|--------|-----|-----|-------|--------------|
| Jan–Jul 2026 | +$318 | 2.28 | 14% | −$15.60 |
| Jan 2025–Jul 2026 | +$566 | 1.42 | 70% | −$63.50 |
| **Jan 2022–Jul 2026** | **+$509** | **1.11** | 95%* | −$64.10 |

\*DD % on $200 deposit; LOCK-202 w03 at $200 was **−$50 / PF 0.99** on comparable stress.

**Script:** `ML/scripts/e7_validate.py` · See [`ai_enhance.md`](ai_enhance.md) §9.9–§9.15.

**No live trading.** **LOCK-202** non-AI paper · **LOCK-809** AI forward test on $200 · E7′ WF still FAIL.

---

## 12. How to use this repository

### Compile & run

1. Open `AAG.mqproj` in MetaEditor
2. Compile **AAG.mq5** (target: v1.33, 0 errors)
3. Strategy Tester → load preset from `Profiles/Tester/`:
   - **Non-AI reference:** `AAG_EURUSD_M5_production.set` (**LOCK-202**)
   - **AI forward test:** `AAG_EURUSD_M5_AI-809_physics-p45.set` (**LOCK-809**)
   - **Defensive overlay:** `AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**)
4. EURUSD M5, variable spread, **$200 deposit** (LOCK-809 validated across windows)

### Enhance (if resuming)

1. Copy `production.set`, change **one input group**
2. Compare vs production on Jan–Jul 2025 + Jan 2025–Jul 2026 + longest
3. Log results in `Edge Discovery.md`

### Deploy (not yet)

Live deployment **not approved** until E7′ WF ≥ 75%. Paper: **LOCK-202** (non-AI wire reference) or **LOCK-809** (AI on $200).

---

## 13. Composition scorecard

| Area | Status |
|---|---|
| Execution engine | **Complete** (v1.33) |
| Edge discovery | **Complete** (LOCK-202) |
| Enhancement matrix | **Complete** (E3–E6, all rejected) |
| AI geometry (E9/809) | **Wired** — LOCK-809 canonical AI preset |
| AI supervisor (E8) | **LOCK-AI** optional (803+805p); 804/806/807 deferred |
| ML offline pipeline | **Complete** (E9a–E9d, E7′, AI-810) |
| Documentation | **Complete** |
| Validation (E7′) | **WF FAIL**; MT5 wire **PASS** (LOCK-809 $200 ext22) |
| Live readiness | **Not met** |

---

*AAG — Adaptive ATR Grid Design · July 2026 · LOCK-202 non-AI · LOCK-809 AI canonical · EA v1.33*
