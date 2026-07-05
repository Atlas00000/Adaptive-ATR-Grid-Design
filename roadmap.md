# AAG Phase 1 — Execution Engine Roadmap

Single-symbol, single-timeframe, single-chart EA. Phase 1 delivers a **working automated execution engine** for the ATR Grid — not strategy perfection, not Phase 2 features.

**System profile:** [`system-profile.md`](system-profile.md) — architecture, edge, trade profile, performance.

**You own testing.** This roadmap covers implementation only. Compile once at the end of Week 4, then run your test campaign.

---

## Phase 1 Definition (Locked)

| In scope | Out of scope |
|---|---|
| ATR grid (6 levels max, one direction at a time) | Bollinger, RSI, tick volume, VWAP, HTF EMA |
| ATR(14), EMA(50), ADX(14) | Session filters, AI regime, structure/liquidity |
| State machine: IDLE → ARMED → GRID_ACTIVE → MANAGING → EXITING → COOLDOWN | Basket trailing, mean-reversion exit, partial closes |
| Market orders, individual SL/TP, basket TP | Pending orders, portfolio / multi-symbol |
| Fixed lot + %-risk sizing (equity-based) | Progressive grid sizing, equity scaling |
| Spread, slippage, cooldown, magic number, equity floor | Adaptive optimisation, CSV logging (optional later) |
| Restart recovery (rebuild basket from open positions) | Cross-chart communication |

---

## Architecture

```
AAG.mq5                    ← thin orchestrator (OnInit / OnTick / OnDeinit)
    │
    ├── StateMachine.mqh   ← grid lifecycle states
    ├── ATREngine.mqh      ← indicator handles + frozen grid distance
    ├── SignalEngine.mqh   ← EMA slope + ADX gate (closed bars only)
    ├── GridEngine.mqh     ← anchor, level math, next-level trigger
    ├── BasketManager.mqh  ← basket TP, position grouping, recovery
    ├── RiskManager.mqh    ← spread, cooldown, limits, sizing
    ├── TradeManager.mqh   ← CTrade, validation, retry, SL/TP attach
    ├── Logger.mqh         ← reason codes + tester/live verbosity
    └── Utils.mqh          ← inputs, types, new-bar detection, lot normalize
```

### OnTick flow (final wiring — Week 4)

```
OnTick
  ├─ Trade management every tick     (SL/TP / basket TP check)
  ├─ if not new closed bar → return
  ├─ RiskManager.CanTrade()          (spread, cooldown, equity, max levels)
  ├─ StateMachine.Update()
  ├─ SignalEngine.Evaluate()         (only in IDLE / ARMED)
  ├─ GridEngine.NextLevelHit()?      (only in GRID_ACTIVE)
  └─ TradeManager.OpenLevel()        (validate → size → send)
```

---

## Folder structure

```text
AAG/
├── AAG.mq5
├── AAG.mqproj
├── Include/
│   ├── Utils.mqh           ← inputs, enums, structs, helpers (create Week 1)
│   ├── Logger.mqh
│   ├── ATREngine.mqh
│   ├── SignalEngine.mqh
│   ├── GridEngine.mqh
│   ├── BasketManager.mqh
│   ├── RiskManager.mqh
│   ├── TradeManager.mqh
│   └── StateMachine.mqh
├── Presets/                ← .set files after build (optional)
└── Docs/
    └── concept.md
```

No separate file per indicator. No provider abstraction layers. No `Tests/` harness in Phase 1.

---

## Compile-once workflow

Development is split into four weekly build blocks. **Do not compile or run the Strategy Tester until Week 4 is complete.**

| Rule | Why |
|---|---|
| Write all four weeks before compiling | One compile → one test campaign |
| Each week ends with valid MQL5 syntax | Avoids a long debug-compile loop at the end |
| Unused modules return safe defaults until wired | e.g. `SignalEngine::Evaluate()` returns `SIGNAL_NONE` in Weeks 1–2 |
| `#include` every `.mqh` from `AAG.mq5` in Week 1 | Single include tree; no `.mqproj` churn later |
| Register all `.mqh` files in `AAG.mqproj` in Week 1 | MetaEditor project stays in sync |

If you must sanity-check mid-build, compile only to confirm zero errors — do not backtest until the pipeline is fully wired.

---

## Weekly implementation

### Week 1 — Scaffolding and configuration

**Goal:** Full project skeleton. Every module exists, compiles in principle, does nothing harmful.

**Deliverables**

- [ ] Create `Include/` and all nine `.mqh` files (empty class/namespace stubs with documented public methods)
- [ ] `Utils.mqh` — all `input` parameters, enums (`GridState`, `TradeBias`, `SizingMode`, `SLTPMode`), structs (`SignalResult`, `GridContext`, `BasketState`)
- [ ] `Logger.mqh` — `LogDebug`, `LogInfo`, `LogError` gated by `InpTesterVerbose`
- [ ] `AAG.mq5` — include all headers; `OnInit` / `OnDeinit` / `OnTick` shells calling stub methods
- [ ] `AAG.mqproj` — list `AAG.mq5` + every `.mqh`
- [ ] Default inputs from concept: ATR 14, multiplier 1.5, EMA 50, ADX 14 / threshold 20, max levels 6, spread 2.0 pips, cooldown 15–30 min

**Stub contract (keep compile-safe)**

```cpp
// Example — every engine exposes Init / Deinit / Reset; no trading logic yet
bool CATREngine::Init() { return true; }
void CATREngine::OnTick() { }
```

**Explicitly skip:** indicator handles, `CTrade`, grid math, signal rules.

---

### Week 2 — Indicators, signals, and grid math

**Goal:** Read market data and compute grid geometry. Still **no orders**.

**Deliverables**

- [ ] `ATREngine.mqh` — create/release ATR, EMA, ADX handles; `CopyBuffer` on closed bar; `GetATR()`, `GetEMA()`, `GetADX()`; `CalcGridDistance()` = ATR × multiplier; freeze distance when basket opens
- [ ] `Utils.mqh` — `IsNewClosedBar()` (compare `iTime` bar 1 vs stored value)
- [ ] `SignalEngine.mqh` — on new bar only:
  - EMA slope: flat if \|slope\| < 0.10 × ATR over 5 bars; bullish if EMA rising ≥ 3 closed candles (mirror for bearish)
  - ADX(14) < 20
  - Output: `BIAS_BUY`, `BIAS_SELL`, or `BIAS_NONE`
- [ ] `GridEngine.mqh` — anchor = first entry price; level price = anchor ± (n × frozen distance); `GetLevelPrice(n)`, `GetNextLevelIndex()`, `IsPriceAtLevel()` with symbol point tolerance
- [ ] `StateMachine.mqh` — enum transitions only: `IDLE → ARMED` when signal fires; stub `GRID_ACTIVE` / `MANAGING` (no entries yet)
- [ ] `AAG.mq5` — on new bar: update indicators → evaluate signal → log decision via `Logger`

**Explicitly skip:** `CTrade`, position sizing, basket TP, persistence, risk gates beyond stubs.

---

### Week 3 — Risk, execution, and grid entries

**Goal:** Open and manage individual grid positions. Basket exit comes in Week 4.

**Deliverables**

- [ ] `RiskManager.mqh`
  - Spread check (points → pips helper)
  - Max open trades (= max grid levels)
  - Global time cooldown after basket close
  - Equity / balance floor (% configurable)
  - Buy-only / sell-only / both permission
  - `PositionSizer` — fixed lot OR `lot = (equity × risk%) / (SL distance × tick value)` normalized to `SYMBOL_VOLUME_STEP`, clamped min/max
- [ ] `TradeManager.mqh`
  - `CTrade` setup: magic, deviation, filling mode
  - `OrderValidator` — spread, stops distance, lot bounds before send
  - `OpenBuy` / `OpenSell` with SL/TP: default 2 × ATR / 1.5 × ATR (or fixed-pip mode)
  - Retry 2–3× on requote / busy / off quotes; log every `TRADE_RETCODE_*`; abort on fatal
- [ ] Wire state machine:
  - `ARMED` → first market entry → set anchor, freeze ATR distance → `GRID_ACTIVE`
  - `GRID_ACTIVE` → price hits next level → add position (same direction, same SL/TP rules)
  - One direction only; reject opposite bias while basket open
  - `MANAGING` when all planned levels filled or no more level triggers
- [ ] `BasketManager.mqh` — track tickets, level index, anchor, frozen distance, open count (no basket TP yet)

**Explicitly skip:** basket TP, restart recovery, COOLDOWN timer (stub → Week 4).

---

### Week 4 — Basket exit, recovery, and completion

**Goal:** Finish the execution loop. **Compile once. Hand off to your testing.**

**Deliverables**

- [ ] `BasketManager.mqh`
  - Combined floating P/L basket TP (money or % of equity — input)
  - On hit: close all basket positions → `EXITING` → `COOLDOWN`
  - Individual SL/TP already on each ticket (managed by broker + tick check)
- [ ] `StateMachine.mqh` — complete transitions:
  - `MANAGING` → monitor basket TP
  - `EXITING` → confirm flat → `COOLDOWN` → timer → `IDLE`
- [ ] Restart / persistence in `OnInit`:
  - Scan open positions (magic + symbol)
  - If found: rebuild anchor (first entry price), frozen distance, level map, state = `GRID_ACTIVE` or `MANAGING`
  - Never discard active basket on reload
- [ ] `AAG.mq5` — final `OnTick` pipeline (diagram above); trade management every tick, signals on closed bar only
- [ ] `Logger.mqh` — tester: signal, grid level, basket stats; live: entries, exits, errors, risk rejects
- [ ] Preset file `Presets/AAG_EURUSD_M5.set` with Phase 1 defaults (optional, for your test setup)

**Compile checkpoint**

1. Open `AAG.mqproj` in MetaEditor  
2. Compile once (F7) — target: **0 errors, 0 warnings**  
3. Attach to EURUSD M5 chart (or Strategy Tester) and begin your test campaign  

**Explicitly skip:** BB, RSI, trailing basket, mean-reversion exit, session filter, AI, multi-symbol, CSV export.

---

## Module responsibility matrix

| Module | Owns | Must not own |
|---|---|---|
| `Utils.mqh` | Inputs, types, new-bar, pip/point math, lot normalize | Trading decisions |
| `ATREngine.mqh` | Indicator lifecycle, ATR/EMA/ADX values, frozen grid distance | Order send |
| `SignalEngine.mqh` | EMA slope + ADX entry gate | Grid levels, sizing |
| `GridEngine.mqh` | Anchor, level prices, level index | Risk checks, orders |
| `StateMachine.mqh` | State enum + legal transitions | Indicator reads |
| `BasketManager.mqh` | Basket grouping, basket TP, recovery data | Signal logic |
| `RiskManager.mqh` | Spread, cooldown, limits, sizing | Signal or grid math |
| `TradeManager.mqh` | Validation, retry, `CTrade` send | State transitions |
| `Logger.mqh` | Formatted output | Business logic |
| `AAG.mq5` | Orchestration only | Logic beyond glue code |

---

## Anti–feature-creep checklist

Before adding any code, ask:

1. Is it required to open, layer, or close a grid trade automatically? **If no → defer.**
2. Does it need a new `.mqh` file? **If yes → probably over-engineering; use an existing module.**
3. Does it run on every tick but only needs closed-bar data? **Move it to new-bar path.**
4. Is it a Phase 2 filter (BB, RSI, session, structure, AI)? **Stop.**
5. Does it support multi-symbol? **Stop — single chart only.**

---

## Completion criteria (implementation done)

Phase 1 implementation is **complete** when:

- [ ] EA compiles with 0 errors from `AAG.mqproj`
- [ ] On a clean chart: signal → first entry → layers up to 6 levels on ATR spacing
- [ ] One direction at a time; opposite grid blocked
- [ ] Each position has SL/TP; basket TP closes all when target hit
- [ ] Cooldown blocks new baskets after close
- [ ] Removing and re-adding EA recovers open basket state
- [ ] Risk rejects (spread, max levels, equity floor) log a reason and skip entry
- [ ] All behaviour driven by inputs (no hard-coded strategy constants outside defaults)

Strategy performance (profit factor, drawdown, etc.) is validated in **your** test phase — not a developer gate for this roadmap.

---

## After Phase 1 (do not build now)

| Phase 2 candidate | Depends on |
|---|---|
| Bollinger / RSI confirmation | Stable signal pipeline |
| Mean-reversion + trailing basket exit | `BasketManager` |
| Session grid (London / NY) | `RiskManager` time gate |
| Volatility pause (max ATR) | `ATREngine` |
| HTF EMA trend-aware grid | `SignalEngine` |
| AI regime filter | Logging + labelled bar data from Phase 1 runs |

---

## Timeline summary

| Week | Focus | Orders live? |
|---|---|---|
| 1 | Scaffolding, inputs, stubs, project file | No |
| 2 | Indicators, signals, grid math, state stubs | No |
| 3 | Risk, trade execution, grid layering | Yes (no basket TP) |
| 4 | Basket TP, recovery, full wiring → **compile once** | Yes (complete) |

**Estimated effort:** 4 weeks part-time implementation → one compile → your backtest / forward test cycle.
