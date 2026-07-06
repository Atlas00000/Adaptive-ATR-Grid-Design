# AAG System Profile

*Adaptive ATR Grid — EURUSD M5 — LOCK-202 non-AI · LOCK-809 AI canonical*

**Last updated:** 2026-07-06  
**EA version:** 1.33  
**Non-AI preset:** `AAG_EURUSD_M5_production.set` (**LOCK-202**)  
**AI preset:** `AAG_EURUSD_M5_AI-809_physics-p45.set` (**LOCK-809**)  
**Defensive AI:** `AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**)  
**Status:** **LOCK-809 MT5 wire winner on $200 ext22**; E7′ WF FAIL — not live.

---

## Executive summary

AAG is a **mean-reversion grid EA** that exploits short-term rotational price action during the US–London overlap (15–17), gated by low trend strength (ADX) and mild EMA structure plus **RSI rotation**.

**Two deployment stacks (post wire validation):**

| Stack | Preset | Role | Best window | Notes |
|---|---|---|---|---|
| **LOCK-202** | `production.set` | **Non-AI reference** | Jan 2025–Jul 2026 (+$623, DD 23%) | Longest stress needed **$500** dep historically |
| **LOCK-809** | `AI-809_physics-p45.set` | **Canonical AI** | Jan 2022–Jul 2026 (+$509, PF 1.11, **$200**) | Beats LOCK-202 w03 (−$50) on same deposit |
| **LOCK-AI** | `AI-803_memory-805p.set` | Defensive tail cap | 2025+ wire | Tail −$27 ✓; more complex than 809 |

LOCK-202 remains **max-net on the wire window**. LOCK-809 is the **AI winner for $200 accounts across all windows** — one geometry toggle, no 803/805 stack. LOCK-AI still useful when **tail cap** matters more than simplicity.

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

### 1.2 Architecture (v1.32)

```
AAG.mq5
├── StateMachine.mqh      IDLE → ARMED → GRID_ACTIVE → MANAGING → EXITING → COOLDOWN
├── ATREngine.mqh         ATR(14), EMA(50), ADX(14); frozen grid distance on basket open
├── SignalEngine.mqh      EMA slope + ADX gate + E2 RSI filter
├── GridEngine.mqh        Anchor, level prices, add triggers
├── BasketManager.mqh     Basket TP, E5 exits, E4 MAE, SL cascade, recovery
├── RiskManager.mqh       Session, spread, cooldown, sizing, E4 depth/lot caps
├── TradeManager.mqh      CTrade execution, SL/TP attach, retry
├── RegimeGate.mqh        E3 gates (off in production / LOCK-AI)
├── StructureGate.mqh     E6 structure filters (off)
├── Diagnostics.mqh       Optional CSV journal
├── AISupervisor.mqh      E8 — memory, health, entry, regime policy
├── AIModelRuntime.mqh    E8 — version gate, ONNX load, LOCK-202 fallback
├── AIModelBundle.mqh     E8 — LOCK-AI / 20260706_808 bundle tags
├── AIHealthModel.mqh     Embedded LR (805)
├── AIEntryContextModel.mqh  Embedded LR (804, off in LOCK-AI)
├── AIRegimeModel.mqh     Embedded LR (806, off in LOCK-AI)
└── Utils.mqh             All inputs and types
```

**Tick flow:**

| Path | Frequency | Components |
|---|---|---|
| Trade management | Every tick | Basket TP, MAE, **AI health caps**, SL cascade, sync |
| Grid levels | Every tick | Add L1–L5; **AI lot / depth / no-add** |
| Signals | **Closed bar only** | Signal → E3/E6 → **AISupervisor** → Risk → Open L0 |

**E8 inference:** Entry/regime at M5 bar close; basket health at **60s checkpoints** + tick-level hard caps (−$25/−$28 float, basket cap −$32, SL cascade).

### 1.3 Production stack — LOCK-202

| Layer | Setting | Notes |
|---|---|---|
| **Session (E1)** | Hours **15–17** | Overlap core; do not widen |
| **Entry (E2)** | RSI rotation — buy ≤48, sell ≥45 | Winner over BB, HTF EMA, EMA distance |
| **Signal base** | EMA(50) slope/flat + ADX(14) < 20 | Rotation, not trend |
| **Grid** | Max **6** levels, spacing = ATR × **1.5** | Full depth validated |
| **Sizing** | Fixed **0.10** lot | |
| **SL / TP** | **2.0×ATR** / **1.5×ATR** per leg | WR-driven; avg loss > avg win |
| **Basket TP** | **$50** money target | **Never fires**; per-leg closes first |
| **Cooldown** | **20** min after basket close | |
| **Spread cap** | **2.0** pips | |
| **E3–E6** | All **off** | Tested; no promotion |
| **E8 AI** | **`InpAIEnabled=false`** | Pure LOCK-202 |

### 1.4 AI stack — LOCK-AI (v1.32)

| Layer | Setting | Notes |
|---|---|---|
| **Base** | Same as LOCK-202 | Signal engine unchanged |
| **AI-803 memory** | `InpAIMemoryEnabled=true` | Lot ×0.80 after bad rolling PF; recovery ramp |
| **AI-805p health** | `InpAIBasketHealthEnabled=true` | `flatten_only`; SL cascade −$9 / stack −$28 |
| **Hard cap** | L1 −$28 / L2 −$25 float | Tick + checkpoint |
| **804 entry** | **off** | Deferred — tail fail long window |
| **806 regime** | **off** | Deferred — no MT5 benefit |
| **808 runtime** | Embedded LR default | `InpAIModelVersion=20260706_808` |
| **ONNX** | `InpAIUseOnnx=false` | Optional `Files/AI/*.onnx` |

### 1.5 State machine

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

The edge lives in **quiet rotational microstructure** during **15–17 overlap**. Profit comes from **high win rate** on shallow grid legs, not favourable R:R. The system **bleeds** in volatility expansion, deep grid stacks, and pre-2025 regimes.

### 2.2 Validated pocket

| Dimension | Finding |
|---|---|
| **When** | **15–17** server time only |
| **Entry** | RSI rotation (≤48 / ≥45) |
| **Grid depth** | 6 levels |
| **Exits** | Per-leg SL/TP; basket TP $50 inert |
| **AI tail fix** | 805p cascade caps at **−$27.40** on 2025+ only |

### 2.3 Horizon decay — LOCK-202 vs LOCK-AI

| Window | LOCK-202 PF | LOCK-202 DD | LOCK-AI PF | LOCK-AI DD | LOCK-AI tail |
|---|---|---|---|---|---|
| **Jan–Jul 2025** | 1.93 | 12% | **1.94** | **13%** | ~−$12 |
| **Jan 25 – Jul 26** | **1.46** | **23%** | 1.33 | 74% | **−$27** ✓ |
| **From Jan 2022** | 0.95 | 98% | 1.12 | 64% | **−$64** ✗ |

**Discovery:** PF decay is **WR collapse** (72% → 56% → 52%), not winner clipping. LOCK-AI improves tail on wire window; **pre-2025 history** still produces fat baskets.

### 2.4 Enhancement outcome

| Phase | Outcome |
|---|---|
| **E5–E6** | All rejected vs LOCK-202 |
| **E8 803+805p** | **LOCK-AI** — tail ✓, net −34% vs prod on 19 mo |
| **E8 804/806/807** | **Deferred** |

---

## 3. Trade profile

### 3.1 Winner profile

Rotation within ATR band, 1–2 levels, 15–17 session, MFE correlation **0.74–0.86**, avg hold ~1h.

### 3.2 Loser profile

Deep grid stack, inverted R:R, fat tails on long history. LOCK-202 largest loss **−$66**; LOCK-AI caps at **−$27** on 2025+ wire window.

### 3.3 Direction split (LOCK-202, 19 mo)

Shorts ~81% volume, WR ~67%; longs ~19%, WR ~60%. Extended history erodes **short WR**.

---

## 4. Current performance

*$200 deposit, variable spread, equity DD.*

### 4.1 LOCK-202 — three horizons

| Metric | Jan–Jul 2025 | Jan 25 – Jul 26 | Longest |
|---|---|---|---|
| **Net** | +$273 | **+$623** | −$192 |
| **PF** | **1.93** | **1.46** | 0.95 |
| **WR** | **72%** | **66%** | 56% |
| **Trades** | 96 | **324** | 581 |
| **Eq DD** | **12%** | **23%** | 98% |
| **Largest loss** | ~−$12 | ~−$63 | **−$66** |

### 4.2 LOCK-AI — v1.32 window sweep

| Metric | Jan–Jul 2025 | Jan 25 – Jul 26 | From Jan 2022 |
|---|---|---|---|
| **Net** | +$246 | +$409 | +$508 |
| **PF** | **1.94** | **1.33** | 1.12 |
| **WR** | 65% | 56% | 52% |
| **Trades** | 99 | 334 | 978 |
| **Eq DD** | 13% | 74% | 64% |
| **Largest loss** | ~−$12 | **−$27.40** | **−$64.10** |
| **Avg W / L** | $7.93 / −$7.49 | $8.84 / −$8.34 | $9.24 / −$9.07 |

### 4.3 Stability assessment

| Stack | Short (7 mo) | Wire (19 mo) | Extended |
|---|---|---|---|
| **LOCK-202** | Strong | **Stable** | Fails |
| **LOCK-AI** | Strong | **Profitable, high DD** | Tail breaks |

---

## 5. Key metrics dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  AAG — EURUSD M5 — July 2026                                │
├─────────────────────────────────────────────────────────────┤
│  PRODUCTION (LOCK-202)          AI STACK (LOCK-AI v1.32)    │
│  Session 15–17                  803 memory + 805p health    │
│  RSI ≤48 / ≥45                  Tail −$27 on 2025+ wire     │
├─────────────────────────────────────────────────────────────┤
│  19-MONTH (Jan 25 – Jul 26)                                 │
│  LOCK-202:  Net +$623 │ PF 1.46 │ DD 23% │ tail −$63       │
│  LOCK-AI:   Net +$409 │ PF 1.33 │ DD 74% │ tail −$27 ✓     │
├─────────────────────────────────────────────────────────────┤
│  SHORT (Jan–Jul 2025)                                       │
│  LOCK-202:  PF 1.93 │ DD 12%                                │
│  LOCK-AI:   PF 1.94 │ DD 13%                                │
├─────────────────────────────────────────────────────────────┤
│  EXTENDED (from Jan 2022, $200)                             │
│  LOCK-AI:   PF 1.12 │ DD 64% │ tail −$64 ✗                  │
├─────────────────────────────────────────────────────────────┤
│  LIVE GATE (not met)                                        │
│  E7 walk-forward │ longest PF ≥ 1.1 │ LOCK-AI ext tail    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Execution & ML infrastructure

| Component | Path | Role |
|---|---|---|
| EA orchestrator | `AAG.mq5` v1.32 | OnTick routing |
| AI supervisor | `Include/AISupervisor.mqh` | Policy: lot, depth, health, skip |
| Model runtime | `Include/AIModelRuntime.mqh` | Version gate, ONNX, fallback |
| Offline pipeline | `ML/scripts/` | build, train, simulate, export |
| Causal replay | `ML/scripts/basket_replay.py` | AI-810 health/exit sim |
| Model registry | `ML/models/registry.json` | LOCK-AI promoted bundle |
| Diagnostics | `ML/export/*_trades_*.csv` | Leg-level tester export |

```bash
cd ML
python scripts/export_models.py --bundle LOCK-AI
python scripts/simulate_policy.py --policy memory_805p --window AI806_805p
```

---

## 7. Live readiness

| Gate | LOCK-202 (wire) | LOCK-809 (MT5 wire) | LOCK-AI (wire) |
|---|---|---|---|
| PF ≥ 1.1 | **1.46** ✓ | **1.11** ext22 ✓ / 1.42 wire | **1.33** ✓ |
| Eq DD < 25% | **23%** ✓ | 70–95%* ✗ | 74% ✗ |
| Tail < −$35 | ✗ (−$63) | ✗ (−$64) | **✓** (−$27) |
| $200 ext22 net | −$50 (w03) | **+$509** ✓ | +$508 |
| Walk-forward | **FAIL** | **FAIL** (E7′) | **FAIL** |

\*DD % on $200; absolute drawdowns comparable to LOCK-AI ext22.

**Verdict:** **LOCK-202** non-AI max-net paper. **LOCK-809** canonical AI on **$200** forward test. **LOCK-AI** when tail cap matters. **No live** — E7′ WF < 75%.

---

## 8. File reference

| File | Purpose |
|---|---|
| `AAG.mq5` | Expert advisor (v1.33) |
| `Presets/AAG_EURUSD_M5_production.set` | **LOCK-202** non-AI reference |
| `Presets/AAG_EURUSD_M5_AI-809_physics-p45.set` | **LOCK-809** canonical AI |
| `Presets/AAG_EURUSD_M5_AI-803_memory-805p.set` | **LOCK-AI** defensive overlay |
| `Presets/AAG_EURUSD_M5_LOCK-AI+809_physics-p45.set` | **LOCK-AI+809** stacked validation |
| `ai_enhance.md` | E8 programme, wire log, metrics |
| `compo-report.md` | Composition report |
| `Edge Discovery.md` | E0–E6 test log |
| `ML/README.md` | Offline pipeline guide |

---

*Update after E7′ re-pass or deployment stack change.*
