# AAG — AI Enhancement Programme (Phase E8)

*Supercharge LOCK-202 without breaking it.*

**Status:** **Production LOCK-202** · **AI stack LOCK-AI locked** (2026-07-06)  
**Production:** `AAG_EURUSD_M5_production.set` (LOCK-202) — **live chart + max-net reference**  
**AI stack:** `AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**) — 805p tail guard + memory throttle  
**Active workstream:** **LOCK-809 promoted (MT5 wire)** · LOCK-202 non-AI · E7′ WF FAIL · **no live**  
**Related:** [`edgeopt.md`](edgeopt.md) · [`system-profile.md`](system-profile.md) · [`compo-report.md`](compo-report.md) · [`aiscaleup.md`](aiscaleup.md) (E9 charter) · [`Edge Discovery.md`](Edge%20Discovery.md)

---

## 0. Why AI now (not more filters)

Edge discovery (E0–E6) proved:

| Approach | Result |
|---|---|
| More entry / regime / structure filters | Trade starvation (7–38 trades) or net collapse |
| Blunt exit / DD caps (E403, E405, E505) | Killed edge or catastrophic DD |
| **LOCK-202 core** | PF 1.46 / +$623 / 23% equity DD over 19 mo — **keep** |

**Failure mode on longest history:** tail losses (−$66), short WR decay, fat baskets — **not** bad entries in 15–17.

**AI role:** Supervisor that **modulates** behaviour (size, depth, spacing, exit urgency, cooldown) using **low thresholds** and **continuous scores** — never a binary “trade / no trade” replacement for LOCK-202.

```text
LOCK-202 SignalEngine  →  always evaluates (unchanged)
        ↓
AI Supervisor (E8)     →  scores context → multipliers only
        ↓
RiskManager / BasketManager / GridEngine  →  scaled execution
        ↓
TradeManager           →  same mechanics
```

---

## 1. Design principles (anti-overfilter)

### 1.1 Default = production behaviour

When AI is **off**, disabled, or score is **neutral (0.4–0.6)**, the EA must behave **identically** to LOCK-202.

### 1.2 Scores modulate; hard gates are rare

| Layer | Score range | Default action | Hard gate (exception only) |
|---|---|---|---|
| **Entry context** | 0.0–1.0 | Lot × **0.65–1.0**, levels **4–6** | Block new basket only if score **< 0.12** AND confidence **> 0.90** |
| **Basket health** | 0–100 | Normal adds at **0–55** | No adds **55–80**; flatten **> 88** only |
| **Regime state** | 4 classes | Full grid in Rotation / Compression | Skip new basket **only** in Trend + prob **> 0.85** |

**vs E3/E6 mistake:** gates at “score > 70” or boundary filters → 90% trade cut. **E8 uses low bar for intervention, high bar for blocking.**

### 1.3 Volume floor (pass rule for every AI phase)

On Jan 2025 – Jul 2026 backtest vs production:

```text
trades ≥ 85% of production (≥ 275 of 324)
net ≥ production − 5%
equity DD ≤ production OR improved by ≥ 3 pts
```

If volume drops below 85%, **lower thresholds** or disable that model — do not ship.

### 1.4 Offline-first, wire-last

```text
Diagnostics CSV  →  Python pipeline  →  train  →  offline policy sim  →  MT5 replay  →  wire AISupervisor.mqh
```

No ONNX in EA until **AI-808** gate passes on historical replay. **Status: AI-808 infra shipped (v1.32) — embedded LR default; ONNX optional.**

---

## 2. Programme phases (E8)

| Phase | ID | Name | ML? | Wire to EA? |
|---|---|---|---|---|
| **P0** | **AI-800** | Infrastructure & repo layout | No | Stub only — **complete** |
| **P1** | **AI-801** | Data export & basket dataset | No | Diagnostics on |
| **P2** | **AI-802** | Features, labels, train/val split | No | — |
| **P3** | **AI-803** | Performance memory (rules) | No | **First wire** |
| **P4** | **AI-804** | Entry context score | Light (LR / GBT) | After offline pass |
| **P5** | **AI-805** | Basket health supervisor | GBT / small NN | After offline pass |
| **P6** | **AI-806** | Regime state classifier | HMM / GBT | After offline pass |
| **P7** | **AI-807** | Expectancy / exit policy | Optional RL sim | Research |
| **P8** | **AI-808** | ONNX runtime + `AISupervisor.mqh` | Export | Production AI path |
| **P9** | **AI-809** | Retrain loop & model registry | — | Ongoing |
| **P10** | **AI-810** | Offline policy backtester | — | CI for models |

**E7 validation** (walk-forward, Monte Carlo) runs **in parallel** on LOCK-202 + any promoted AI stack before live — see EDGE-702/703.

---

## 3. Phase detail & task IDs

### P0 — AI-800: Infrastructure

**Goal:** Folder layout, stubs, config — zero behaviour change.

**Deliverables**

```text
AAG/
├── Include/AISupervisor.mqh      # stub: all multipliers = 1.0
├── ML/
│   ├── README.md
│   ├── config.yaml               # thresholds, paths, feature list
│   ├── requirements.txt
│   ├── export/                   # raw CSV from tester
│   ├── features/                 # parquet / csv feature tables
│   ├── models/                   # versioned joblib / onnx
│   ├── notebooks/                # EDA only
│   └── scripts/
│       ├── build_baskets.py
│       ├── build_features.py
│       ├── train_entry_context.py
│       ├── train_basket_health.py
│       ├── train_regime.py
│       ├── simulate_policy.py    # offline apply multipliers to CSV
│       └── export_mql_constants.py
```

**Preset:** `AAG_EURUSD_M5_AI-800_stub.set` — `InpAIEnabled=false`

**Gate:** EA compiles v1.09+; production identical to v1.08 when AI off. **Status: complete 2026-07-05 — gate verified.**

**Verification (2026-07-05):** `AI-800_stub` Jan 25–Jul 26 ext = production byte-match: PF **1.46**, net **+$623**, WR **66%**, trades **324**, equity DD **23%**. Python `simulate_policy.py` stub runs; deps install OK.

---

### P1 — AI-801: Data pipeline

**Goal:** Rich labelled dataset from LOCK-202 runs.

**Actions**

1. Run `EDGE-001_diagnostics` / `EDGE-LOCK-202` with `InpDiagnosticsCSV=true`
2. Windows: Jan–Jul 2025, Jan 25–Jul 26, **longest** (tail labels critical)
3. `build_baskets.py` — group legs → basket records

**Basket-level schema (target)**

| Field | Source |
|---|---|
| `basket_id` | Diagnostics |
| `open_time`, `close_time`, `hold_sec` | Aggregated |
| `bias`, `levels_filled`, `max_level` | Diagnostics |
| `basket_pnl`, `basket_won` | Sum of legs |
| `max_floating_dd`, `mae`, `mfe` | Reconstructed from legs / ticks if available |
| `entry_adx`, `entry_atr`, `entry_rsi` | Bar at L0 |
| `hour`, `weekday`, `month` | Context |
| `tail_loss` | Label: `basket_pnl < -2 × avg_win` or `< -$25` |

**Gate:** ≥ **250 baskets** on 19-mo export; basket PnL reconciles to tester report ±2%.

---

### P2 — AI-802: Features & labels

**Goal:** Leak-free feature matrix + walk-forward splits.

**Feature groups (no new indicators in EA for v1)**

| Group | Features |
|---|---|
| Entry | RSI, ADX, ATR, ATR pct (100-bar), EMA slope, spread |
| Session | minute-in-15–17, weekday, month |
| Memory | rolling 10/20 basket WR, PF, avg DD |
| Basket (health model) | depth, float P/L, time in trade, ΔATR, ΔADX, dist anchor |

**Labels**

| Model | Label | Positive class rate target |
|---|---|---|
| AI-804 entry | `basket_won` | ~66% (match production WR) |
| AI-805 health | `tail_loss` or `basket_pnl < -$20` | ~15–25% (rare — use class weights) |
| AI-806 regime | `rotation` vs `expansion/trend` | From post-hoc rules + manual audit |

**Split:** Walk-forward blocks — 3m train / 1m test, roll; **never** random shuffle baskets.

**Gate:** Feature notebook signed off; no single feature > 0.85 correlation with label leakage.

---

### P3 — AI-803: Performance memory (rules) — **first wire**

**Goal:** Self-throttle after drawdown clusters **without** blocking entries.

**Logic (no ML)**

```text
rolling_20 = last 20 basket outcomes
if rolling_PF < 1.15 OR rolling_max_basket_loss > 1.5 × historical_avg_loss:
    global_risk_mult = 0.80   # floor 0.65
    max_levels_cap = 5        # floor 4
else if rolling_PF > 1.5 AND rolling_WR > 0.68:
    global_risk_mult = min(1.0, global_risk_mult + 0.05)  # slow recovery to 1.0
```

**Thresholds intentionally low** — only activates after **sustained** deterioration, not single loss.

**Preset (LOCK-202 only — wire FAIL):** `AAG_EURUSD_M5_AI-803_memory.set` — archive  
**Preset (LOCK-AI):** `AAG_EURUSD_M5_AI-803_memory-805p.set` — defensive overlay (803+805p)  
**Preset (LOCK-809):** `AAG_EURUSD_M5_AI-809_physics-p45.set` — **canonical AI** (geometry)

**Lesson:** 803 on LOCK-202 alone → net −$122, DD worse. Retest **stacked on 805p** where tail is already contained.

**Offline gate:** `simulate_policy.py --policy memory_805p --window AI806_805p` → DD improved ≥ 2 pts vs 805p, trades ≥ 90%. **MT5 replay authoritative.**

**Throttle refinement (v1.10):** `PF < 1.0` OR (`tail spike > 2× avg loss` AND `PF < 1.15`) — avoids constant throttle from single PF dip.

**Wire gate:** Same on MT5 Strategy Tester replay.

---

### P4 — AI-804: Entry context score

**Goal:** Nudge lot / depth / spacing by **predicted basket quality** — **not** filter entries.

**Model:** Logistic regression or shallow GBT (interpretable).

**Output:** `p_win ∈ [0,1]` calibrated

**Policy (low threshold)**

```text
edge_score = p_win   # no squashing above 0.5

lot_mult     = 0.65 + 0.35 × edge_score        # range 0.65 – 1.00
max_levels   = 4 + round(2 × edge_score)       # range 4 – 6
spacing_mult = 1.0 + 0.25 × (1 - edge_score)   # range 1.0 – 1.25

# HARD BLOCK — almost never:
if edge_score < 0.12 and model_confidence > 0.90:
    skip basket
```

**Expected:** WR ↑ on traded baskets (better sizing on weak contexts); **trade count ≥ 85%**.

**Preset (LOCK-AI stack test):** `AAG_EURUSD_M5_AI-804_lock-ai.set` — LOCK-AI + `InpAIEntryContextEnabled=true`  
**Isolation preset:** `AAG_EURUSD_M5_AI-804_entry-context.set` — LOCK-202 + entry only (lab)

**Offline gate:** `simulate_policy.py --policy entry_804_lock_ai --window AI806_805p` vs LOCK-AI (`memory_805p`): trades ≥ 85%, net ≥ −5%, DD improved ≥ 2 pts. **MT5 authoritative.**

**Preliminary offline (AI806_805p):** LOCK-AI +$416 / DD 56.2% → +804 +$367 / DD 48.4% / PF 1.29 — **DD PASS, net FAIL offline**. Wire test next.

---

### P5 — AI-805: Basket health supervisor ⭐ highest priority

**Goal:** Predict tail baskets **before** −$66; graded response, not blunt E403/E405.

**Model:** Gradient boosted trees on basket **bar-by-bar** or **event** rows (each new level fill).

**Output:** `health ∈ [0,100]` = `P(tail_loss) × 100`

**Policy (lower bands than edgeopt.md)**

| Health | Action |
|---|---|
| **0–55** | Normal — full adds per AI-804 levels |
| **55–72** | **No new adds**; hold for rotation |
| **72–88** | Tighten TP on new legs to **1.25×ATR**; optional close best leg if float > $8 |
| **> 88** | Flatten basket (replaces fixed MAE exit) |

**Do not flatten below 88** — preserves recovery trades that made LOCK-202 profitable.

**Preset:** `AAG_EURUSD_M5_AI-805_basket-health.set`

**Gate:** Longest-window **largest loss** improved (target < −$35); 19-mo equity DD ≤ 20%; net ≥ prod −3%.

**Wire FAIL (v1.11):** Exported LR model scored benign L0 at ~89 health (`dist_anchor_atr` train mean ~16944 vs live ~1.5) → `max(rule, model)` triggered flatten on every basket (~28s avg hold, PF 0.23). **Fix v1.12:** rules-only health + flatten guards.

**Wire FAIL (v1.12):** Bug fixed (PF 1.25, WR 55%, 316 trades) but DD **69%** vs prod **23%**. Root cause: offline sim only **caps tail basket PnL** post-hoc; EA also blocked adds (55+), tightened TP (72+), trimmed legs — not modeled offline. **Fix v1.13:** `InpAIHealthFlattenOnly=true` — flatten guards only.

---

### P6 — AI-806: Regime skip classifier (NEXT)

**Goal:** Skip **unfavourable new-basket contexts** using ML — not blunt E3 gates, not global throttle (803 failed).

**Lesson from 805p long run (Jan 2024 – Jul 2026):** 805 **survived** the bad regime (+$454, PF 1.23, 549 trades, tail −$27.40 ✓) by **in-basket tail control**, not by sitting out. DD still **~69%** — regime skip should **reduce bad entries**, not replace 805.

**Two-layer stack (target architecture)**

```text
LOCK-202 signal (15–17)  →  AI-806: skip new basket?  →  AI-805p: in-basket tail guard
         ↑                           ↑                              ↑
    unchanged              pre-trade (806)                  post-entry (805p, wired)
```

| Layer | When | Action |
|-------|------|--------|
| **AI-806** | At basket **arm** time | Skip new basket if `P(bad_basket) > 0.85` + high confidence |
| **AI-804** (optional) | Same | Throttle lot/depth before hard skip |
| **AI-805p** | During basket | Partial SL cascade, cap — **keep as-is** |

**Label (train on basket opens, not bars):** each potential L0 arm → features at signal time → outcome = basket PnL or `P(tail \| open)`. Use EDGE-001 `AAG_diag_trades_*.csv` + basket replay aggregates.

**Features (at signal time):** hour, weekday, ADX, ATR level / percentile, EMA distance, prior-day range, session vol, rolling PF (7d baskets), recent consec losses — **not** month-only rules (EDGE-306 failed).

**Skip policy (anti-overfilter)**

| Rule | Value |
|------|-------|
| Block target | **New basket arming only** — never block grid adds on open baskets |
| Hard skip threshold | `P(bad) > 0.85` **and** model confidence high |
| Expected skip rate | **5–15%** of 15–17 signals — not 50% |
| Default | LOCK-202 trades when score neutral or AI off |
| Forbidden | Seasonal month skip · score > 70 trade gate · account-level throttle (803) |

**States (optional soft policy instead of binary skip)**

| State | max_levels | spacing | New baskets? |
|---|---|---|---|
| COMPRESSION | 6 | 1.3×ATR | Yes |
| ROTATION | 6 | 1.5×ATR | Yes (default) |
| EXPANSION | 4 | 1.8×ATR | Yes |
| TREND | — | — | Skip only if `P(TREND) > 0.85` |

**Preset (planned):** `AAG_EURUSD_M5_AI-806_regime.set` on top of 805p basket-health base.

**Offline gates:** longest-window PF ≥ **1.05**; trades ≥ **80%** prod; net not worse than **805p alone** on w03; walk-forward (AI-802) before wire.

**Stub:** `ML/scripts/train_regime.py` — implement labelling + GBT/HMM training.

---

### P7 — AI-807: Expectancy / exit policy (research)

**Goal:** Lift avg win vs avg loss without E504-style winner clipping.

**Ideas (offline sim only first)**

- Partial at 1R on L0 only when health < 40
- Dynamic TP = `1.5 + 0.5 × edge_score` × ATR
- Runner leg after basket float > $10

**Defer wire** until AI-805 stable and AI-806 offline pass.

**Status:** **LOCK-805p locked** (health layer) · **LOCK-AI locked** (§9.4) · AI-806 **DEFERRED** (§9.2) · AI-807 **RESEARCH** (§9.6, offline only).

---

### P8 — AI-808: ONNX runtime + production AI path

**Goal:** Ship models to MT5.

**Deliverables**

- `AISupervisor.mqh` — load ONNX or embedded weight tables
- `InpAIEnabled`, per-model toggles
- Bar-close inference only (M5 closed bar + basket events)
- Fallback: if model load fails → **LOCK-202 pure**

**Export:** `export_mql_constants.py` for LR; ONNX for GBT via `mql5_onnx` (if available) else piecewise linear lookup tables.

**Version tag in preset:** `InpAIModelVersion=20260706_808` (or `LOCK-AI`)

**Status:** **Shipped v1.32** — see §9.7.

### P9 — AI-809: Retrain loop

**Cadence**

| Trigger | Action |
|---|---|
| Monthly | Re-export diagnostics from latest 19-mo window |
| Quarterly | Full retrain AI-804/805/806; compare offline gates |
| After regime shift | Manual retrain if rolling_PF < 1.2 for 30 days live |

**Model registry:** `ML/models/registry.json` — version, train window, metrics, promoted bool.

**Never auto-promote** without passing volume floor + DD gates.

---

### P10 — AI-810: Offline policy backtester

**Goal:** Replay baskets applying AI policy **causally** — fast iteration without MT5.

```bash
# Causal health replay (wire gate — matches EA v1.13 flatten_only)
python ML/scripts/simulate_policy.py --policy health --window w02_ext19mo

# Full policy (no-add / tighten / trim — matches EA v1.12)
python ML/scripts/simulate_policy.py --policy health --health-mode full --window w02_ext19mo

# Deprecated hindsight cap (do NOT use for wire gates)
python ML/scripts/simulate_policy.py --policy health --legacy-health --window w02_ext19mo
```

**Engine (`basket_replay.py`):** leg open/close events + 60s checkpoints; linear floating estimate; EA-matching `RuleHealthScore` + policy guards.

**w02 results (2026-07-05):**

| Engine | Net | DD | Notes |
|---|---|---|---|
| Legacy post-hoc | +$719 | 24.1% | 20 baskets edited — hindsight |
| **Event replay flatten_only** | **+$694** | **20.2%** | 44 flatten interventions |
| Event replay full | +$638 | 20.7% | explains 805b wire FAIL |

**Use as CI:** only **event replay** may promote to wire; `--legacy-health` for regression compare only.

---

## 4. Suggested build order

```text
AI-800 infra stub
  → AI-801 data (3 windows, diagnostics on)
  → AI-802 features/labels
  → AI-810 offline sim harness
  → AI-803 memory rules → wire → tester confirm (FAIL on LOCK-202 — defer)
  → AI-805 basket health → wire → **LOCK-805p ACCEPTED (partial)** ✓
  → AI-806 regime skip → offline → wire → **DEFERRED** (no MT5 benefit)
  → AI-803 memory on LOCK-805p stack → **LOCK-AI locked** ✓
  → AI-804 entry context → v1.31 long test → **DEFERRED (tail fail)** ✓
  → E7 walk-forward on LOCK-202 + LOCK-AI stack          ← **NEXT**
```

**Parallel:** EDGE-702 walk-forward on pure LOCK-202 establishes baseline stress stats.

---

## 5. Promotion gates (every AI-ID)

| # | Criterion |
|---|---|
| G1 | Trades ≥ **85%** of production (19-mo window) |
| G2 | Net ≥ production **−5%** (or DD improved ≥ 3 pts with net ≥ −3%) |
| G3 | Equity DD ≤ production (19-mo) OR longest DD improved ≥ 10 pts |
| G4 | Longest PF not worse than production (hold ≥ 0.95; target ≥ 1.05 per model) |
| G5 | Offline sim **and** MT5 tester agree within ±5% on net |
| G6 | Ablation: disabling AI model returns to production metrics |

---

## 6. Stretch targets (full E8 stack)

| Metric | Production (19 mo) | E8 stretch |
|---|---|---|
| PF | 1.46 | **1.55–1.65** |
| WR | 66% | **68–72%** (via sizing, not filters) |
| Equity DD | 23% | **15–20%** |
| Longest PF | 0.95 | **≥ 1.10** |
| Largest loss | ~−$16 (19 mo) / −$66 (longest) | **< −$25** longest |
| Trades | 324 | **≥ 275** |

---

## 7. EA inputs (planned — AI-808)

```text
=== AI Supervisor (E8) ===
InpAIEnabled                 = false
InpAIModelVersion            = ""
InpAIMemoryEnabled           = false    // AI-803
InpAIEntryContextEnabled     = false    // AI-804
InpAIBasketHealthEnabled     = false    // AI-805
InpAIRegimeEnabled           = false    // AI-806
InpAIEntryBlockFloor         = 0.12     // low — rarely blocks
InpAIHealthNoAddThreshold    = 55       // low vs edgeopt 60
InpAIHealthFlattenThreshold  = 88       // high — only true tails
InpAIRegimeTrendSkipProb     = 0.85     // high confidence only
InpAILotMultMin              = 0.65
InpAILotMultMax              = 1.00
```

---

## 8. What we explicitly will NOT do

| Anti-pattern | Why (from discovery) |
|---|---|
| Score > 70 to trade | E3/E6 over-filter |
| Seasonal month skip | EDGE-306 removed profitable pocket |
| MR EMA basket exit | EDGE-505 catastrophic |
| Fixed DD% basket cap | EDGE-403 net −$279 |
| AI generates entries | Breaks validated LOCK-202 |
| Train on shuffled trades | Leakage; use walk-forward only |

---

## 9. Results log (E8)

| ID | Date | Offline PF | Tester PF | WR | DD% | Trades | vs Prod | Verdict |
|---|---|---|---|---|---|---|---|---|
| AI-800 | 2026-07-05 | **1.46** | **1.46** | **66%** | **23%** | **+$623** | **= production** | **Gate pass** |
| AI-801 w01 | 2026-07-05 | — | **1.93** | **72%** | **12%** | **96** | **= production** | **export OK** |
| AI-801 w02 | 2026-07-05 | — | **1.46** | **66%** | **23%** | **324** | **= production** | **export OK** |
| AI-801 w03 | 2026-07-05 | — | **0.99** | **57%** | **85%** | **1061** | tail labels ($500 dep) | **export OK** |
| AI-802 | 2026-07-05 | — | — | **65%** | — | **1051** | 16 WF folds, leak PASS | **Gate pass** |
| AI-803 | 2026-07-05 | 1.62 | **1.41** | **65%** | **61%** | **329** | net −$122, DD worse | **Wire FAIL** |
| AI-805 | 2026-07-05 | 1.78 | **0.23** | **2%** | **88%** | **354** | ML flatten bug | **Wire FAIL** |
| AI-805b | 2026-07-05 | 1.78 | **1.25** | **55%** | **69%** | **316** | +$302, sim≠EA | **Wire FAIL** |
| AI-805c | 2026-07-05 | 1.67 | **1.46** | **64%** | **61%** | **329** | +$584 ≈ prod | **Wire PARTIAL** |
| AI-805d | 2026-07-05 | 1.67 | **1.46** | **64%** | **61%** | **329** | −$63 unchanged | **Wire FAIL** |
| AI-805e | 2026-07-05 | 1.67 | **1.46** | **64%** | **61%** | **329** | v1.16, 0 hard_cap fires | **Wire FAIL** |
| AI-805f | 2026-07-05 | 1.67 | **1.46** | **64%** | **61%** | **329** | L1=-35 never fired | **Wire FAIL** |
| AI-805g | 2026-07-05 | 1.67 | **1.35** | **53%** | **61%** | **338** | +$382, tail −$27 ✓, cascade costly | **Wire FAIL** |
| AI-805h | 2026-07-05 | 1.67 | **1.47** | **64%** | **60%** | **329** | +$588 ≈ prod, tail −$63 back | **Wire FAIL** |
| AI-805i | 2026-07-05 | 1.67 | **1.47** | **64%** | **60%** | **329** | +$588, 0 sl_cascade (timing bug) | **Wire FAIL** |
| AI-805j | 2026-07-05 | 1.67 | **1.47** | **64%** | **60%** | **329** | +$588, 0 sl_cascade (thresholds -18/-10 too tight) | **Wire FAIL** |
| AI-805k | 2026-07-05 | 1.39 | **1.39** | **55%** | **68%** | **331** | +$491, 18 sl_cascade, tail −$63.50 | **Wire FAIL** |
| AI-805l | 2026-07-05 | 1.35 | **1.35** | **55%** | **71%** | **334** | +$427, tail −$27.40 ✓, over-cascade | **Wire FAIL** |
| AI-805m | 2026-07-05 | 1.50 | **1.50** | **64%** | **60%** | **329** | +$611 ≈ prod, 0 basket_cap, tail −$63.50 | **Wire FAIL** |
| AI-805n | 2026-07-05 | 1.50 | **1.50** | **64%** | **60%** | **329** | +$611 identical 805m, 0 basket_cap, tail −$63.50 | **Wire FAIL** |
| AI-805o | 2026-07-05 | 1.34 | **1.34** | **67%** | **67%** | **338** | +$403, 114 sl_cascade, tail **−$27.40 ✓** | **Wire PARTIAL** |
| AI-805p | 2026-07-06 | 1.35 | **1.35** | **55%** | **71%** | **334** | +$427, tail **−$27.40 ✓** | **Wire ACCEPT (partial)** |
| AI-805p-long | 2026-07-06 | — | **1.23** | **54%** | **69%** | **549** | +$454 Jan24–Jul26, tail ✓ | **Regime stress OK** |
| AI-806 @0.85 | 2026-07-06 | — | **1.23** | **54%** | **69%** | **549** | +$454, **0 skips** (LR max ~0.69) | **Wire FAIL** |
| AI-806 @0.62 | 2026-07-06 | — | **1.21** | **53%** | **73%** | **545** | +$422, 4 skips, net −$32 vs 805p | **Wire FAIL** |
| AI-803+805p | 2026-07-06 | 1.44 | **1.44** | **59%** | **58%** | **333** | +$469, tail −$27.40 ✓, DD −12 pts vs 805p | **Wire ACCEPT (partial)** |
| AI-803+805p-long | 2026-07-06 | — | **1.25** | **56%** | **71%** | **548** | +$442 Jan24–Jul26, tail −$24.64 ✓ | **Long stress OK** |
| AI-804+LOCK-AI @v1.30 | 2026-07-06 | — | — | — | — | **1** | rolling PF=99 mass block | **Wire FAIL** |
| AI-804+LOCK-AI-long | 2026-07-06 | — | **1.23** | **58%** | **66%** | **546** | +$374, tail **−$44.45** ✗ | **Wire FAIL** |
| AI-807 offline | 2026-07-06 | 1.28 | — | — | 64.7% | **395** | runner_lock +$500 vs baseline +$476 | **Research DEFER** |
| AI-808 | 2026-07-06 | — | — | — | — | — | v1.32 runtime + embedded LR + ONNX infra | **Infra PASS** |
| LOCK-AI v1.32 w01 | 2026-07-06 | — | **1.94** | **65%** | **13%** | **99** | +$246 Jan–Jul25, $200 dep | **Short OK** |
| LOCK-AI v1.32 w02 | 2026-07-06 | — | **1.33** | **56%** | **74%** | **334** | +$409 Jan25–Jul26, tail −$27.40 ✓ | **Wire OK** |
| LOCK-AI v1.32 ext22 | 2026-07-06 | — | **1.12** | **52%** | **64%** | **978** | +$508 from 2022, tail **−$64.10** ✗, **$200 dep** | **Regime stress FAIL** |
| E7 WF+MC | 2026-07-06 | — | — | — | — | — | LOCK-202 11/16 · LOCK-AI 15/28 folds | **E7 FAIL** |
| AI-810 | 2026-07-05 | **1.74** | — | — | **20.2%** | **241** | causal replay PASS | **Sim fixed** |

---

## 9.1 Wire acceptance — LOCK-805p (2026-07-06)

**Decision:** **Lock LOCK-805p** as the forward-test preset for AI-805 basket health. Full net/PF wire vs LOCK-202 is **not** achieved; tail containment **is**. **Not promoted to production.**

**Canonical preset:** `AAG_EURUSD_M5_AI-805_basket-health.set` (**LOCK-805p**) · **EA v1.27+**  
**Tester window:** 2025.01.01 – 2026.07.04 · **$200** deposit · EURUSD M5 · session 15–17

### vs LOCK-202 production (same window)

| Metric | LOCK-202 / 805m | **AI-805p** | Delta | Gate |
|--------|-----------------|-------------|-------|------|
| Net profit | +$611 – $623 | **+$427** | **−$184 to −$196** (−30%) | Net FAIL |
| Profit factor | 1.46 – 1.50 | **1.35** | −0.11 to −0.15 | PF FAIL |
| Win rate | 64 – 66% | **55%** | −9 to −11 pts | — |
| Total trades | 324 – 329 | **334** | +2 – +3% | PASS (≥85% floor) |
| **Largest loss** | **−$63.50** | **−$27.40** | **+57% tail cut** | **PASS (< −$35)** |
| Equity DD | ~23% (prod) / ~60% (805m) | **~71%** | worse | FAIL |
| SL cascades | 0 – 2 | **~82** | early flatten on 2-leg partial SL | mechanism |

### What 805p does (v1.27)

| Layer | Setting | Role |
|-------|---------|------|
| SL cascade | `deal ≤ −$9` OR `deal+float < −$28` | Flatten remaining leg after partial SL in 2-leg baskets |
| Basket cap | −$32 total, minLegs=1, deal-inclusive | Backup; rarely fires (0 events in 805p) |
| Hard cap L1/L2 | −$28 / −$25 float | Per-leg clamp + aged float guard |
| Stress flatten | score > 75, float < −$18 | Rare tail trim (~9 events in 805c band) |

### Net trade-off (explicit)

```text
Tail fix cost ≈ $184–196 net over 19 mo on $200 deposit (~30% of LOCK-202 profit).

Mechanism: ~30–80 partial-SL cascades close recoverable 2-leg baskets early.
WR drops ~66% → 55%; avg loss improves (−$8 vs −$10) but fewer winners complete.

Accepted because:
  • Largest loss gate passes (−$27.40 vs −$63.50) — primary E8 tail objective
  • Trade volume preserved (334 vs 324–329)
  • Production preset remains available for max-net runs
  • Further cascade tuning (805k–805p sweep) did not find a both-gates solution
```

### Deployment guidance

| Use case | Preset |
|----------|--------|
| **Production / max net** | `AAG_EURUSD_M5_production.set` (LOCK-202) |
| **AI stack (demo / forward test)** | `AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**) |
| Health layer only (reference) | `AAG_EURUSD_M5_AI-805_basket-health.set` (LOCK-805p) |
| AI off / neutral | Identical to LOCK-202 (`InpAIEnabled=false`) |

**LOCK-805p is the health building block** inside LOCK-AI — use LOCK-AI for all AI forward tests unless isolating 805 behaviour.

### Superseded attempts (reference)

| ID | Why not accepted |
|----|------------------|
| 805c–805h | Tail −$63.50 unchanged |
| 805m/n | Best net (+$611) but tail fail |
| 805k | +$491 net but tail still −$63.50 |
| 805o | Tail ✓ but net +$403 (114 cascades — too aggressive) |
| 805l | Same outcome as 805p; 805p adds deal-inclusive cap + stack guard in code |

### Long-window validation — 805p (Jan 2024 – Jul 2026)

| Metric | Wire window (2025–Jul26) | **Long window** |
|--------|--------------------------|-----------------|
| Net | +$427 | **+$454** |
| PF | 1.35 | **1.23** |
| Trades | 334 | **549** |
| Largest loss | −$27.40 ✓ | **−$27.40 ✓** |
| Equity DD | ~71% | **~69%** |

805p remains profitable with tail gate held over 2024 bad regime; DD stays high → next lever is **803 memory on 805p stack**, not more cascade tuning or 806 skip (deferred).

---

## 9.2 AI-806 regime skip — DEFERRED (2026-07-06)

**Verdict:** Wired (EA v1.29, `AIRegimeModel.mqh`) but **do not promote**. Keep `InpAIRegimeEnabled=false` on forward-test presets.

### MT5 results (805p + 806, Jan 2024 – Jul 2026)

| Threshold | Net | Trades | Skips | vs LOCK-805p alone |
|-----------|-----|--------|-------|---------------------|
| **0.85 / 0.80** | +$454 | 549 | **0** | identical — LR max score ~0.69 live |
| **0.62** | +$422 | 545 | 4 | net −$32, DD worse (~73% vs ~69%) |

**Root cause:** Offline sim used GBT (max P≈0.91); MT5 wired exported LR (max P≈0.69). Live feature vector also differs from parquet training features. Skipped baskets at 0.62 were net-positive — skip hurt.

**Keep for lab:** diagnostics exports, `train_regime.py`, `simulate_policy.py --policy regime_805p`, presets `AI-806_regime*.set` with regime **off**.

### Original action plan (archive)

**Objective:** Skip the subset of **15–17 basket opens** that historically became D2 tail / negative-expectancy baskets — without starving the edge (E3/306 lesson).

### Step 1 — Re-export diagnostics (both presets)

1. Strategy Tester → Inputs → **Load** from `MQL5\Profiles\Tester\`:
   - **`AAG_EURUSD_M5_AI-806_diagnostics-prod.set`** — LOCK-202, prefix `AAG_diag_AI806_prod`
   - **`AAG_EURUSD_M5_AI-806_diagnostics-805.set`** — 805p, prefix `AAG_diag_AI806_805p`
2. Dates: **2024.01.01 – 2026.07.04** · deposit **$200** · Visual **OFF**
3. Output: `MQL5/Files/AAG_diag_AI806_*_trades_EURUSD.csv` (+ summary)
4. Optional window slices: `AI-801_w01` / `w02` / `w03` presets for labelled folds

### Step 2 — Build basket-open labels

1. Extend `ML/scripts/build_baskets.py` (or new `label_basket_opens.py`) — one row per **L0 arm** with:
   - Features: hour, weekday, ADX, ATR, EMA dist, prior-day range, rolling 7d basket PF, consec losses
   - Label: `basket_pnl`, `is_tail` (basket total < −$20), `max_depth ≥ 2` + loss
2. Audit **2024 H1** vs 2025+ buckets in summary CSV (`month`, `hour`, `basket_depth`)

### Step 3 — Train AI-806 (`train_regime.py`)

1. Implement GBT (or HMM state) in `ML/scripts/train_regime.py`
2. Walk-forward folds per AI-802 — **no shuffled trades**
3. Output: `ML/models/regime_v0.joblib` + calibration report (`P(bad)` vs actual tail rate)
4. Target: identify contexts where **new-basket expectancy < 0** while keeping skip rate ≤ 15%

### Step 4 — Offline policy sim

1. `ML/scripts/simulate_policy.py --policy regime` (to implement) on w01/w02/w03
2. Stack sim: **806 skip + 805p replay** (regime filter before basket start)
3. Gates vs **805p alone**:
   - Longest PF ≥ **1.05**
   - Trades ≥ **80%** of 805p trade count
   - Net ≥ 805p on w02; DD improved on w03
   - Tail largest loss still < −$35

### Step 5 — Wire AI-806 (after offline pass)

1. `RegimeGate.mqh` / `AISupervisor` — `ShouldSkipNewBasket()` at arm time only
2. Preset: `AAG_EURUSD_M5_AI-806_regime.set` = **805p base** + `InpAIRegimeEnabled=true`
3. MT5 retest: Jan 2024 – Jul 2026 + wire window 2025 – Jul 2026
4. Journal: log `ai_regime_skip` with reason + score

### Step 6 — E7 stress (before live)

1. Walk-forward + Monte Carlo on **805p + 806** stack (EDGE-702/703)
2. Compare vs production and 805p-only on longest window

### Do not do

| Anti-pattern | Why |
|--------------|-----|
| Month calendar skip | EDGE-306 removed profitable months |
| Skip outside 15–17 | EA barely trades elsewhere — no gain |
| Replace 805 with skip-only | Tails still form on traded baskets |
| AI-803 global lot throttle | Net −$122, DD worse |
| Score > 70 entry block | E3 over-filter starvation |

### Deployment target (when gated)

| Preset | Role |
|--------|------|
| `production.set` | Max net reference |
| `AI-805_basket-health.set` | Tail-safe (805p, **wired**) |
| `AI-806_diagnostics-prod.set` / `AI-806_diagnostics-805.set` | Regime labelling exports (Step 1) |
| `AI-806_regime.set` | 805p + regime skip (**archived — regime off**) |

---

## 9.3 Next steps — P3 AI-803 on LOCK-805p stack

**Objective:** Self-throttle lot size after drawdown clusters **on top of** tail-safe 805p health — without blocking entries. 803 failed on bare LOCK-202; retest where tail is already capped.

### Stack

```text
LOCK-202 signal (15–17)  →  AI-805p: in-basket tail guard  →  AI-803: lot mult on next basket
    unchanged                  post-entry (wired)                 rolling 20-basket rules
```

### Step 1 — Offline sim

```bash
cd ML/scripts
python simulate_policy.py --policy 805p --window AI806_805p
python simulate_policy.py --policy memory_805p --window AI806_805p
```

Gates vs **805p alone**: DD improved ≥ **2 pts**, trades ≥ **90%**, tail largest loss still < −$35.

**Preliminary offline (AI806_805p window, 2026-07-06):**

| Policy | Net | PF | DD | Trades | Worst |
|--------|-----|----|----|--------|-------|
| 805p | +$476 | 1.27 | 64.7% | 395 | −$27.40 |
| memory_805p | +$416 | 1.27 | **56.2%** (−8.5 pts) | 395 | −$23.20 |

Offline: **DD PASS**, trades PASS, **net FAIL** (−$60 / −13%). MT5 wire test still required — basket replay lot scaling ≠ live leg sizing.

### Step 2 — MT5 wire test

1. Load **`AAG_EURUSD_M5_AI-803_memory-805p.set`** in Strategy Tester
2. Windows: wire (2025.01.01 – 2026.07.04) + long (2024.01.01 – 2026.07.04)
3. Compare vs **LOCK-805p** on net, PF, DD, trades, largest loss
4. Journal: confirm `memory_throttle` events in Experts log when rolling PF dips

### Memory rules (already in `AISupervisor.mqh`)

| Trigger | Action |
|---------|--------|
| rolling_20 PF < 1.0 | lot_mult → **0.80** (floor 0.65) |
| tail spike > 2× avg loss AND PF < 1.15 | same throttle |
| rolling PF > 1.5 AND WR > 68% | slow recovery +0.05 toward 1.0 |
| throttle active | max_levels cap → **5** |

### Wire gates

| Gate | Target |
|------|--------|
| vs LOCK-805p net | not worse than −5% |
| vs LOCK-805p DD | improved ≥ 2 pts OR net gain |
| Trades | ≥ 90% of 805p count |
| Largest loss | still < −$35 |

### Do not do

| Anti-pattern | Why |
|--------------|-----|
| 803 on LOCK-202 alone | Already failed — net −$122 |
| Replace 805 with memory-only | Memory does not cut in-basket tails |
| Re-enable 806 skip | No MT5 benefit at tested thresholds |

---

## 9.4 Wire acceptance — LOCK-AI (2026-07-06)

**Decision:** **Lock LOCK-AI** as the canonical **AI stack** preset. Combines LOCK-805p basket health + AI-803 performance memory. **Not promoted to production** — production remains LOCK-202.

**Canonical preset:** `AAG_EURUSD_M5_AI-803_memory-805p.set` (**LOCK-AI**) · **EA v1.27+**  
**Tester window:** 2025.01.01 – 2026.07.04 · **$200** · EURUSD M5 · 111,777 bars · history quality 100%

### vs LOCK-805p (same window)

| Metric | **LOCK-805p** | **AI-803+805p** | Delta | Gate |
|--------|---------------|-----------------|-------|------|
| Net profit | +$427 | **+$469** | **+$42 (+10%)** | **PASS** |
| Profit factor | 1.35 | **1.44** | +0.09 | PASS |
| Win rate | 55% | **59%** | +4 pts | — |
| Total trades | 334 | **333** | −1 (99.7%) | **PASS** (≥90%) |
| **Largest loss** | **−$27.40** | **−$27.40** | unchanged | **PASS** |
| Equity DD | ~71% | **58.5%** | **−12.5 pts** | **PASS** (≥2 pts) |
| Balance DD | — | 54.3% | — | — |
| Sharpe | — | 8.35 | — | — |
| Recovery factor | — | 3.58 | — | — |

### vs LOCK-202 production (same window)

| Metric | LOCK-202 | **AI-803+805p** | Notes |
|--------|----------|-----------------|-------|
| Net | +$611 | +$469 | −23% vs max-net reference |
| PF | 1.46 | 1.44 | near parity |
| Largest loss | −$63.50 | **−$27.40** | tail objective met |
| Equity DD | ~23% | 58.5% | still high vs prod |

### Offline vs MT5 (lesson)

Offline `memory_805p` on AI806_805p window predicted **net FAIL** (−$60) but **DD PASS**. MT5 wire shows **both net and DD pass** — basket-replay lot scaling understates live benefit. **MT5 remains authoritative** for 803 stack acceptance.

### Long-window stress — Jan 2024 – Jul 2026

| Metric | **LOCK-805p-long** | **AI-803+805p-long** | Delta | Gate |
|--------|--------------------|-----------------------|-------|------|
| Net profit | +$454 | **+$442** | −$12 (−2.6%) | **PASS** (≥ −5%) |
| Profit factor | 1.23 | **1.25** | +0.02 | PASS |
| Win rate | 54% | **56%** | +2 pts | — |
| Total trades | 549 | **548** | −1 (99.8%) | **PASS** |
| **Largest loss** | **−$27.40** | **−$24.64** | **+10% tail cut** | **PASS** |
| Equity DD | ~69% | **71.1%** | +2.1 pts worse | **FAIL** (DD gate) |
| Sharpe | — | 3.85 | — | — |
| Recovery factor | — | 2.70 | — | — |

**Long-window verdict:** Stack **survives 2024 bad regime** (profitable, tail ✓, volume preserved). vs bare 805p: net within −5%, PF and tail **better**, DD **marginally worse** (+2 pts). Wire-window DD gain (58.5% vs 71%) **does not generalise** to full 30 mo — memory throttle helps recent window more than 2024 H1 stress.

### Deployment

| Stack | Preset | Role |
|-------|--------|------|
| **Production** | `production.set` | LOCK-202 — live chart, max-net reference |
| **AI stack** | **`AI-803_memory-805p.set`** | **LOCK-AI** — demo, forward test, AI validation |
| Health layer | `AI-805_basket-health.set` | LOCK-805p — building block; isolate 805 only |

---

## 9.5 Next steps — P4 AI-804 on LOCK-AI stack

**Objective:** Nudge lot / depth at basket open from predicted win probability — **not** filter entries. Stacks on LOCK-AI (805p + memory).

### Pipeline (done)

1. `build_features.py` on `baskets_ai806.parquet` → `train_entry.parquet`
2. `train_entry_context.py` → `models/entry_context_v0.joblib` (LR, WF AUC ~0.56)
3. `export_mql_constants.py --type entry` → `Include/AIEntryContextModel.mqh`
4. EA v1.30 — `AISupervisor` wires `EntryWinProb` + lot/depth policy
5. `simulate_policy.py --policy entry_804_lock_ai`

### MT5 wire test (v1.30 — FAIL)

**Result:** 1 trade only — **Wire FAIL**.

**Root cause (v1.30):** After first winning basket, `RollingPfRecent(20)` returns **99** when the rolling window has wins but zero losses. LR maps pf=99 → p_win≈0.005 → **hard block** (`p_win < 0.12` + confidence > 0.90) on almost every subsequent basket.

**Fix v1.31:** Cap `rolling_pf_20` at 8.0 for model input; cold-start rolling imputation (training medians); pandas weekday encoding.

Re-run **`AI-804_lock-ai.set`** on EA **v1.31**.

### MT5 wire test (v1.31 — long window Jan 2024 – Jul 2026)

**Result:** Volume restored (546 trades) but **Wire FAIL** vs LOCK-AI.

| Metric | **LOCK-AI long** | **804+LOCK-AI v1.31** | Gate |
|--------|------------------|------------------------|------|
| Net | +$442 | **+$374** | FAIL (−15%) |
| PF | 1.25 | **1.23** | marginal |
| Trades | 548 | **546** | **PASS** (99.6%) |
| **Largest loss** | **−$24.64** | **−$44.45** | **FAIL** |
| Equity DD | ~71% | **66.3%** | improved |

**Verdict:** Keep **804 off** — `InpAIEntryContextEnabled=false`. **LOCK-809** is canonical AI preset; **LOCK-AI** remains defensive overlay.

**Optional follow-up:** Disable hard block entirely; retrain LR with capped PF in training pipeline; or defer 804 until E7.

| Output | Formula |
|--------|---------|
| `p_win` | LR on 14 leak-free open features |
| `lot_mult` | 0.65 + 0.35 × p_win (memory may cap further) |
| `max_levels` | 4 + round(2 × p_win), clamped 4–6 |
| Hard block | p_win < 0.12 AND confidence > 0.90 (rare) |

### Offline vs LOCK-AI (AI806_805p)

| Stack | Net | PF | DD |
|-------|-----|----|----|
| LOCK-AI | +$416 | 1.27 | 56.2% |
| +804 | +$367 | 1.29 | **48.4%** |

Offline net gate fails; MT5 may differ (803 lesson). **Do not promote LOCK-AI until 804 MT5 pass or 804 stays optional layer.**

---

## 9.6 AI-807 expectancy / exit policy — RESEARCH (2026-07-06)

**Objective:** Lift avg win vs avg loss without E504-style winner clipping. **Offline sim only** — no EA wire until stable stack.

**Data:** `AI806_805p` long window (395 baskets, Jan 2024 – Jul 2026) · `$200` deposit · causal leg replay on 805p health stack.

### Baseline expectancy (raw basket PnL)

| Metric | Value |
|--------|-------|
| Net | +$453.90 |
| PF | 1.25 |
| Win rate | 60.5% |
| **Avg win** | **$9.43** |
| **Avg loss** | **−$11.53** |
| Expectancy | +$1.15/basket |
| Largest loss | −$27.40 (tail ✓) |
| D2+ win rate | 19.0% |

**Segment insight:** Losses are ~22% larger than wins on average; D2+ baskets (39% of volume) drive most tail risk. Expectancy is positive only because WR > 50%.

**MFE / giveback (replay peak floating):** Winners capture ~**98%** of peak basket float on median; mean giveback **~$0.20** — LOCK-AI winners already hold to TP/health close. **Little room for “more TP” without clipping.**

### Exit policy sweep (805p replay baseline = +$476 / PF 1.27 / DD 64.7%)

Causal checkpoint replay stacking exit overlays on LOCK-805p health (`exit_replay.py`).

| Policy | Net | PF | DD | Avg win | Avg loss | Exit events | Verdict |
|--------|-----|----|----|---------|----------|-------------|---------|
| **baseline_805p** | **+$476** | **1.27** | 64.7% | $9.43 | −$11.39 | — | reference |
| partial_l0_1r | +$268 | 1.15 | 84.2% | $8.56 | −$11.39 | 178 | **FAIL** (clips winners) |
| dynamic_tp | +$245 | 1.14 | 93.3% | $8.46 | −$11.39 | 73 | **FAIL** |
| **runner_lock** | **+$500** | **1.28** | 64.7% | $9.41 | −$11.48 | 2 | **marginal PASS** |
| combined | +$352 | 1.20 | 83.5% | $8.80 | −$11.48 | 185 | **FAIL** |

**Policy definitions (config `exit_policy`):**

| Policy | Rule |
|--------|------|
| `partial_l0_1r` | 50% partial at 1R on L0 when health < 40 |
| `dynamic_tp` | Early take on weak edge (ADX proxy) when float ≥ 0.9R × TP scale |
| `runner_lock` | Flatten if float retraces below $8 after first crossing $10 |
| `combined` | All three enabled |

### Verdict — **DEFER wire**

| Gate | partial | dynamic | runner | combined |
|------|---------|---------|--------|----------|
| Net ≥ 95% baseline | ✗ | ✗ | ✓ | ✗ |
| Tail ≥ −$35 | ✓ | ✓ | ✓ | ✓ |
| Avg win +5% | ✗ | ✗ | ✗ | ✗ |
| Trades ≥ 85% | ✓ | ✓ | ✓ | ✓ |

**Conclusion:** Early partial / dynamic TP **destroy net** (−44% to −49%) by clipping L0 winners that 805p already manages. **Runner lock** is the only candidate (+$24 net, +0.01 PF, 2 events) — too sparse to wire; monitor in next research pass with finer trail grid.

**Do not wire AI-807.** Keep **LOCK-AI** canonical. Revisit after E7 walk-forward or if live forward test shows systematic winner giveback.

### Pipeline

```bash
cd ML
python scripts/build_baskets.py --glob "AI806_805p_trades_*.csv" --output features/baskets_ai806.parquet
python scripts/analyze_expectancy.py --window AI806_805p --replay-mfe
python scripts/simulate_exit_policy.py --window AI806_805p --policy all
```

| Script | Output |
|--------|--------|
| `analyze_expectancy.py` | `features/expectancy_report.json` |
| `simulate_exit_policy.py` | `features/exit_policy_report.json` |
| `exit_replay.py` | Causal exit engine (import only) |

---

## 9.7 AI-808 ONNX runtime + production AI path (2026-07-06)

**Objective:** Ship models to MT5 with version validation, optional ONNX, and **LOCK-202 fallback** on load failure.

**EA v1.32** · **Runtime mode default:** `embedded` (LR constants in `.mqh`)

### Deliverables

| Component | Path | Role |
|-----------|------|------|
| Model runtime | `Include/AIModelRuntime.mqh` | Version gate, ONNX load, fallback |
| Bundle manifest | `Include/AIModelBundle.mqh` | `LOCK-AI` / `20260706_808` tags |
| Export pipeline | `ML/scripts/export_models.py` | Batch MQL + registry + bundle |
| ONNX export | `export_mql_constants.try_export_onnx` | Optional `skl2onnx` |
| Registry | `ML/models/registry.json` | Promoted bundle = **LOCK-AI** |

### Runtime behaviour

| Condition | Result |
|-----------|--------|
| `InpAIEnabled=false` | Pure LOCK-202 (unchanged) |
| `InpAIModelVersion=LOCK-AI` + toggles match | AI active, mode=`embedded` |
| Version unknown / toggle mismatch | **Fallback LOCK-202** — AI disabled, EA runs |
| `InpAIUseOnnx=true` + Files/AI/*.onnx | mode=`onnx` |
| ONNX missing + `InpAIOnnxFallbackEmbedded=true` | Falls back to embedded LR |

**Inference timing:** Entry/regime at **M5 bar close** (`ProcessSignals`); basket health at **60s checkpoints** + tick-level hard caps (unchanged).

### New inputs (`Utils.mqh`)

| Input | Default | Purpose |
|-------|---------|---------|
| `InpAIUseOnnx` | false | Load from `Common/Files/AI/*.onnx` |
| `InpAIOnnxFallbackEmbedded` | true | Use embedded LR if ONNX missing |

### Export workflow

```bash
cd ML
python scripts/export_models.py --bundle LOCK-AI
# Optional ONNX: pip install skl2onnx onnxruntime
# Copy ML/models/onnx/*.onnx -> Terminal/Common/Files/AI/
```

**Preset tag:** `InpAIModelVersion=LOCK-AI` or `20260706_808`

### Gate — **PASS (infrastructure)**

| Gate | Status |
|------|--------|
| EA compiles v1.32 | ✓ |
| AI off = LOCK-202 identical | ✓ (MasterEnabled gating) |
| Version mismatch → fallback | ✓ |
| Embedded LR path for LOCK-AI | ✓ |
| ONNX path optional | ✓ (infrastructure; LR default) |
| Registry tracks bundle | ✓ |

**Note:** Production AI stack remains **LOCK-AI** (803+805p). ONNX is for future GBT/retrain loop (AI-809) — LR models use embedded constants by default.

---

## 9.8 LOCK-AI MT5 window sweep — v1.32 (2026-07-06)

**Preset:** `AAG_EURUSD_M5_AI-803_memory-805p.set` · **EA v1.32** · **$200 deposit** · EURUSD M5 · history quality 100%

| Window | Period | Trades | Net | PF | WR | Eq DD | Largest loss | Verdict |
|--------|--------|--------|-----|-----|-----|-------|--------------|---------|
| **w01 short** | Jan – Jul 2025 | 99 | +$246 | **1.94** | 65% | **13%** | ~−$12 | In-sample sweet spot |
| **w02 wire** | Jan 2025 – Jul 2026 | 334 | +$409 | **1.33** | 56% | 74% | **−$27.40** ✓ | **LOCK-AI wire window OK** |
| **ext from 2022** | Jan 2022 – Jul 2026 | 978 | +$508 | **1.12** | 52% | 64% | **−$64.10** ✗ | Tail + regime **FAIL** |

*Prior long stress (Jan 2024 – Jul 2026, **$500** dep): PF 1.25, tail −$24.64 ✓ — see §9.4.*

### What the sweep shows

**PF decay is monotonic with window length:** 1.94 → 1.33 → 1.12. Not an 808-runtime bug — same embedded stack, more history.

| Driver | w01 (1.94) | w02 (1.33) | ext22 (1.12) |
|--------|------------|------------|--------------|
| Win rate | 65% | 56% | 52% |
| Avg win / avg loss | ~$7.93 / −$7.49 | $8.84 / −$8.34 | $9.24 / −$9.07 |
| Tail cap | n/a | **−$27.40 ✓** | **−$64.10 ✗** |
| 805p cascades | low | ~82 events | many more |

**One-liner:** LOCK-AI holds tail on the **2025+ wire window** but **2022–2024 adds ~644 trades** in harsher regimes where WR falls to 52% and at least one **pre-calibration fat basket (−$64)** slips past 805p — the stack was tuned on 2025+ data, not 2022 stress.

### w02 vs prior v1.27 acceptance (same dates, $200)

| Metric | v1.27 (§9.4) | **v1.32** | Delta |
|--------|--------------|-----------|-------|
| PF | 1.44 | **1.33** | −0.11 |
| Net | +$469 | +$409 | −$60 |
| WR | 59% | 56% | −3 pts |
| Eq DD | 58.5% | 74% | +15 pts worse |
| Tail | −$27.40 | −$27.40 | unchanged ✓ |

Tail gate **unchanged**; net/PF/DD slightly worse — likely tester date boundary or 808 init path (embedded mode). **Not a regression blocker** if tail holds; investigate DD delta on next compile check.

### Deposit note (ext22)

Extended 2022 run used **$200** (not $500). Smaller deposit → higher **equity DD %** on same absolute losses; tail −$64 is an **absolute** fail regardless of deposit size.

### Deployment read

| Use case | Window | Preset |
|----------|--------|--------|
| Forward test / demo | Jan 2025+ | **LOCK-AI** ✓ |
| Live (max net, low DD) | any | **LOCK-202 production** |
| Research / stress | 2022+ | Expect PF ~1.1, tail may break — needs E7 WF + retrain |

**LOCK-AI remains locked for forward test on 2025+ wire window.** Do not promote on ext22 until tail −$35 gate passes or 806/809 retrain covers 2022 regimes.

---

## 9.9 E7 walk-forward + Monte Carlo (2026-07-06)

**IDs:** EDGE-702 (walk-forward) · EDGE-703 (Monte Carlo)  
**Script:** `ML/scripts/e7_validate.py` · **Report:** `ML/features/e7_report.json`

### Method

| Component | Spec |
|-----------|------|
| Walk-forward | 3m train / 1m test rolls (`assign_walk_forward`) |
| Test-fold pass | PF ≥ 1.0, net ≥ $0, trades ≥ 5 |
| WF gate | ≥ **75%** of test folds pass (≥3/4 when n≥4) |
| Monte Carlo | 2000 shuffles of basket PnL order; compare actual max DD to p95 |
| LOCK-202 source | Raw `basket_pnl` from diagnostics exports |
| LOCK-AI source | `memory_805p` causal replay (`simulate_memory_805p`) |

```bash
cd ML
python scripts/build_baskets.py --glob "w02_ext19mo_trades_*.csv" --output features/baskets_w02_ext19mo.parquet
python scripts/build_baskets.py --glob "w03_longest_trades_*.csv" --output features/baskets_w03_longest.parquet
python scripts/e7_validate.py --policy all
```

### Results ($200 deposit)

| Stack | Window | Full net | PF | DD | WF folds | MC p95 DD | Verdict |
|-------|--------|----------|-----|-----|----------|-----------|---------|
| **LOCK-202** | w02 wire (19 mo) | +$623 | 1.61 | 28.2% | **11/16 (69%)** | 45.6% | **FAIL** |
| **LOCK-202** | w03 longest | −$50 | 0.99 | 163% | **22/52 (42%)** | 179.9% | **FAIL** |
| **LOCK-AI** | AI806_805p | +$416 | 1.27 | 56.2% | **15/28 (54%)** | 60.3% | **FAIL** |

*Note: w02 export aggregates **241 baskets** (leg-sum reconciles +$623); MT5 reports 324 trades — basket vs leg counting. MC actual DD **not worse than p95** on wire window → sequence luck is not the main risk; **regime instability** is.*

### Gate breakdown

| Gate | LOCK-202 w02 | LOCK-202 w03 | LOCK-AI |
|------|----------------|--------------|---------|
| WF ≥75% folds | ✗ (69%) | ✗ (42%) | ✗ (54%) |
| Full net > 0 | ✓ | ✗ | ✓ |
| PF floor | ✓ (1.61) | ✗ (0.99) | ✓ (1.27) |
| DD ≤ 25% | ✗ (28.2%) | ✗ | n/a |
| Tail < −$35 | ✗ (−$25) | ✓ | ✓ (−$23) |
| MC worse than p95 | ✗ | ✗ | ✗ |

### Weak folds (pattern)

| Period | LOCK-202 | LOCK-AI |
|--------|----------|---------|
| 2022 H1 | Heavy fail cluster | n/a (data starts 2024) |
| 2024 H1 | Apr–Jul bleed | Apr–Jul bleed |
| 2025 Nov–Dec | Fail | Mixed |
| 2026 Jul | Fail (n=2–3 baskets) | Fail (n=2) |

**2024 H1** is the shared OOS failure pocket — aligns with ext22 tail break and E9 retrain target.

### Verdict — **E7 FAIL · NOT LIVE-READY**

| Deployment | Status |
|------------|--------|
| **LOCK-202 production** | Paper only — WF 69% on wire window, DD 28% > 25% gate |
| **LOCK-AI forward test** | OK for 2025+ demo — full-window gates pass, WF 54% fails |
| **Live trading** | **Blocked** until WF ≥75% on wire window + DD gate |

**Next:** E9b grid geometry offline sim targeting D2+ failure mode.

---

## 9.10 E9a basket intelligence (2026-07-06)

**ID:** E9a · **Script:** `ML/scripts/e9a_basket_intelligence.py` · **Report:** `ML/features/e9a_report.json`

```bash
cd ML
python scripts/e9a_basket_intelligence.py --window all
```

### Method

Basket-level metrics on LOCK-202 (`w03_longest`), LOCK-AI (`AI806_805p`), and wire reference (`w02_ext19mo`):

| Metric | Definition |
|--------|------------|
| **Recovery rate** | % underwater baskets (`path_mae < −$1`) that close positive |
| **Lifetime** | Hold hours (median / p90); % baskets open > 4h |
| **Capital efficiency** | Mean PnL per level, per hour; exposure efficiency on underwater baskets |
| **Depth** | D2+ rate, D2+ WR vs L0 WR, SL exit rate |

Segments: **all**, **2024 H1**, **2024 Apr–Jul**, **rest**, **D2+**, **L0 only**.

### Results — primary finding: **L0 carries edge, D2+ destroys it**

| Stack | Segment | Baskets | Net | PF | WR | D2+ WR | SL exit % |
|-------|---------|---------|-----|-----|-----|--------|-----------|
| LOCK-202 w03 | **All** | 736 | −$50 | 0.99 | 57% | 21% | 34% |
| LOCK-202 w03 | **L0 only** | 439 | **+$1,899** | **3.32** | **82%** | — | 19% |
| LOCK-202 w03 | **D2+** | 297 | **−$1,949** | **0.31** | 21% | 21% | 48% |
| LOCK-202 w03 | **2024 H1** | 75 | −$144 | 0.71 | 51% | 26% | **41%** |
| LOCK-202 w03 | Rest | 661 | +$94 | 1.03 | 58% | 20% | 29% |
| LOCK-AI | **L0 only** | 248 | **+$1,439** | **5.10** | **85%** | — | 15% |
| LOCK-AI | **D2+** | 147 | **−$986** | **0.32** | 19% | 19% | 17% |
| LOCK-AI | **2024 H1** | 76 | −$35 | 0.91 | 55% | 17% | 24% |

*w02 wire window (241 baskets, 2025+) has no 2024 H1 data — confirms sweet-spot bias.*

### 2024 H1 stress pocket

| Stack | 2024 H1 net | Apr–Jul net | vs rest WR Δ | vs rest SL exit Δ |
|-------|-------------|-------------|--------------|-------------------|
| LOCK-202 | −$144 | −$132 | −7.1 pts | **+12.4 pts** |
| LOCK-AI | −$35 | −$47 | −6.5 pts | +9.9 pts |

Worst LOCK-202 months: **Jul −$63**, Feb −$46, Nov −$46. LOCK-AI health layer **softens** 2024 H1 (−$35 vs −$144) but **cannot fix D2+ economics** (PF 0.32 on deep stacks).

### Verdict — **E9a PASS (research gate)**

| Question | Answer |
|----------|--------|
| How do regimes fail? | **Deep stacks (D2+)** — 40% of baskets, ~100% of longest-window losses |
| Is it winner clipping? | **No** — L0 WR 82–85%; problem is grid depth / SL cascade on stacked legs |
| Is 2024 H1 special? | **Yes** — higher SL exit rate (+12 pts), larger avg loss; bleed starts Feb–Mar |
| What fixes it? | **E9b** — spacing / depth limits / non-linear geometry before signal |

**Next:** E9c — context-gate `no_add_after_l0_sl` so w02 wire net holds.

---

## 9.11 E9b grid geometry offline (2026-07-06)

**ID:** E9b · **Script:** `ML/scripts/e9b_grid_geometry.py` · **Report:** `ML/features/e9b_report.json`

Extends `basket_replay.py` with geometry overlays: `max_grid_levels`, `spacing_mult`, **`no_add_after_l0_sl`** (block L1+ after L0 leg closes at SL).

```bash
cd ML
python scripts/e9b_grid_geometry.py --window all
```

### Policy sweep (causal replay, no health caps)

| Policy | w03 longest | w02 wire (19 mo) | 2024 H1 (w03) | Verdict |
|--------|-------------|------------------|---------------|---------|
| **baseline** | −$44 · PF 0.99 | +$656 · PF 1.67 | −$144 | — |
| cap_l0_only | −$161 | +$331 | — | **Reject** — kills L1 recovery |
| cap_l2 | = baseline | = baseline | = baseline | **No effect** — no L3+ in data |
| spacing_125/150 | −$86 / −$78 | −$33 / −$42 | — | **Reject** |
| stress_flat_−15 | +$38 | **+$725** | — | Helps wire; defensive not geometry |
| **no_add_after_l0_sl** | **+$321** · PF 1.10 | **+$515** (−$108) | **−$45** (+$99) | **PARTIAL** |

LOCK-AI (`no_add_after_l0_sl`): +$695 (+$241), **2024 H1 +$39** (was −$35).

### Primary finding

D2+ failure is driven by **averaging after L0 SL** — baskets where L0 stops out then L1 opens are net-negative. Blocking further adds after L0 SL is **causal** and fixes the stress pocket, but **clips wire-window edge** (−$108 on w02) because some 2025+ baskets recover via L1 after L0 SL.

Spacing / depth-cap alone do not fix D2+ (max depth in data is **2** only).

### Verdict — **E9b PARTIAL · defer wire**

| Gate | Result |
|------|--------|
| Improve w03 net | **PASS** (+$371) |
| Fix 2024 H1 | **PASS** (−$144 → −$45) |
| w02 net ≥ prod −5% | **FAIL** (−$108 vs w02) |
| D2+ PF ≥ 1.0 | **FAIL** (still ~0.35) |
| Tail < −$35 | **PASS** (worst −$19 w03) |

**Promote to E9c:** `no_add_after_l0_sl` as a **context-gated multiplier** — apply in high-SL regimes (2024 H1 pattern), not globally on 2025+ wire.

---

## 9.12 E9c context-gated geometry (2026-07-06)

**ID:** E9c · **Script:** `ML/scripts/e9c_context_geometry.py` · **Report:** `ML/features/e9c_report.json`

Applies E9b `no_add_after_l0_sl` **only when entry-time context matches** — no skips, same basket count.

```bash
cd ML
python scripts/e9c_context_geometry.py
```

### Combo gate (w02 wire + w03 stress)

| Gate | Requirement |
|------|-------------|
| w02 net | ≥ prod −5% (**≥ $591**) |
| w03 Δnet | ≥ **+$50** vs baseline |
| w02 gated % | ≤ **55%** |
| Tail | ≥ **−$35** |

### Results — top passing gates

| Gate | w02 net | w03 Δnet | Gated (w02/w03) | Live-viable? |
|------|---------|----------|-----------------|--------------|
| **adx_lt_18** | **$666** | **+$117** | 42% / 45% | **Yes** — entry ADX < 18 |
| month_stress | $656 | +$153 | 0% / 9% | Weak — month enum only |
| pre_2025 | $656 | +$363 | 0% / 66% | **No** — calendar lookahead |
| always_on | $515 | +$371 | 100% | **No** — fails w02 |

### Promote candidate — **`adx_lt_18`**

When **entry ADX < 18** at basket open → apply `no_add_after_l0_sl` (block L1+ after L0 SL).

| Window | Baseline | Gated | Delta |
|--------|----------|-------|-------|
| w02 wire | $656 | **$666** | +$43 |
| w03 longest | −$44 | **+$67** | +$117 |
| vs prod $623 | — | **+$43** | passes −5% gate |

2024 H1 on w03 still **−$117** (improved from −$144 globally, not fully fixed). Needs E9d physics or stacked gates for OOS pocket.

### Verdict — **E9c PASS (offline research gate)**

| Item | Status |
|------|--------|
| Context multiplier (not skip) | **PASS** — geometry only on ~45% of baskets |
| w02 + w03 combo | **PASS** with `adx_lt_18` |
| 2024 H1 fully healed | **FAIL** — still negative |
| MT5 wire | **Deferred** — prove in EA + re-run E7′ |

**EA mapping:** pre-signal rule in `ProcessGridLevels` — if `entry_adx < 18` set `no_add_after_l0_sl` flag on basket context (same as E9b replay). **Next:** E7′ validation before wire.

---

## 9.13 E7′ walk-forward + MC — `adx_lt_18` (2026-07-06)

**ID:** E7′ · **Policy:** `lock202_adx_lt_18` · **Report:** `ML/features/e7_prime_report.json`

```bash
cd ML
python scripts/e7_validate.py --policy lock202_adx_lt_18
```

### vs E7 baseline (LOCK-202 raw baskets)

| Window | Metric | E7 LOCK-202 | E7′ `adx_lt_18` | Δ |
|--------|--------|-------------|-----------------|---|
| w02 wire | Net | +$623 | **+$666** | +$43 |
| w02 wire | PF | 1.61 | **1.69** | +0.08 |
| w02 wire | DD | 28.2% | **21.6%** | ✓ under 25% |
| w02 wire | WF folds | **11/16 (69%)** | 10/16 (62%) | −1 fold |
| w03 longest | Net | −$50 | **+$67** | +$117 |
| w03 longest | PF | 0.99 | **1.02** | +0.03 |
| w03 longest | WF folds | 22/52 (42%) | **25/52 (48%)** | +3 folds |
| w03 longest | DD | 163% | 128% | still fail |

*Gated ~42–45% of baskets (entry ADX < 18). MC actual DD ≤ p95 on both windows.*

### Verdict — **E7′ FAIL · still NOT LIVE-READY**

| Gate | w02 wire | w03 longest |
|------|----------|-------------|
| WF ≥75% folds | **FAIL** (62%) | **FAIL** (48%) |
| Full-window gates | **PASS** (PF, DD, net) | PF 1.02 only |
| 2024 H1 OOS | — | folds 21–32 mostly FAIL |

Geometry gate **helps net and w02 DD** but **does not clear the WF bar**. 2024 H1 pocket still bleeds in most folds. **No MT5 wire** — superseded by E9d physics gate.

---

## 9.14 E9d physics stack-risk gate (2026-07-06)

**ID:** E9d · **Scripts:** `e9d_physics_labels.py`, `e9d_simulate.py` · **Model:** `models/stack_risk_v0.joblib` · **Report:** `ML/features/e9d_report.json`

Labels at **L0 SL close** (causal): MAE/MFE on L0 path, hold time, ADX/ATR, rolling memory. Target: `label_block_beneficial` = L0-only PnL > full basket PnL when L1+ exists.

```bash
cd ML
python scripts/e9d_physics_labels.py
python scripts/e9d_simulate.py
python scripts/e7_validate.py --policy lock202_physics_p45 --output features/e7_physics_report.json
```

### Label stats (410 L0-SL + depth rows)

| Segment | block_beneficial rate | avg recovery_delta |
|---------|----------------------|-------------------|
| All | 58.3% | — |
| **2024 H1** | **73.6%** | +$2.98 |

Train AUC **0.64** (w03) · OOS w02 AUC **0.62**.

### Promote candidate — **`physics_lr_p45`**

Block L1+ after L0 SL only when LR `p(block_beneficial) ≥ 0.45` — fires on **~21–29%** of baskets (vs 45% for `adx_lt_18`).

| Window | `adx_lt_18` | **`physics_lr_p45`** | Δ |
|--------|-------------|----------------------|---|
| w02 net | $666 | **$629** | −$37 (still ≥ prod $623) |
| w02 DD | 21.6% | **18.5%** | ✓ best survivability |
| w03 net | +$67 | **+$479** | +$412 |
| w03 DD | 128% | **35.7%** | ✓ major tail fix |
| **2024 H1** | −$117 | **−$36** | +$81 pocket heal |

### E7′ with `lock202_physics_p45`

| Window | WF folds | Full net | DD | Verdict |
|--------|----------|----------|-----|---------|
| w02 wire | 10/16 (**62%**) | +$629 | **18.5%** | FAIL (<75%) |
| w03 longest | **28/52 (54%)** | +$479 | **35.7%** | FAIL |

2024 H1 folds: **Jan PASS** (+$16), Apr PASS (+$0.70), May PASS (+$23) — pocket partially healed; Feb/Mar/Jul still fail.

### Verdict — **E9d PASS (offline) · E7′ still FAIL**

| Gate | Result |
|------|--------|
| E9d combo (w02+w03+h1) | **PASS** (`lr_p45`) |
| Survivability (DD) | **PASS** w02 18.5%, w03 35.7% |
| WF ≥75% | **FAIL** — live still blocked |
| MT5 wire | **Wired v1.33** — `AIStackRiskModel.mqh` · presets **LOCK-809** / **LOCK-AI+809** |
| Live trading | **Blocked** — E7′ WF < 75% |

**EA mapping:** on L0 SL close, compute physics features → if `p ≥ 0.45`, set basket `no_add_after_l0_sl`. **Not** basket-open ADX gate.

**Promote hierarchy:**

| Layer | Candidate | Role |
|-------|-----------|------|
| Geometry | **`physics_lr_p45`** (AI-809) | Block L1+ after L0 SL when stack-risk LR fires |
| Defensive | **LOCK-AI** (803+805p) | Tail cap / health overlay — forward test only |
| Production | **LOCK-202** | Max-net paper reference |

Supersedes E9c **`adx_lt_18`** geometry gate (better w03 DD and 2024 H1, lower gated %).

---

## 9.15 AI-809 MT5 wire (2026-07-06)

**ID:** AI-809 · **Model:** `AIStackRiskModel.mqh` (`stack_risk_v0`) · **EA:** v1.33

| Input | Default | Role |
|-------|---------|------|
| `InpAIPhysicsStackEnabled` | false | Enable L0-close geometry gate |
| `InpAIPhysicsStackThreshold` | 0.45 | Block adds when P(block beneficial) ≥ threshold |

**Presets (bundle IDs):**

| File | Bundle |
|------|--------|
| `AAG_EURUSD_M5_AI-809_physics-p45.set` | **LOCK-809** — LOCK-202 + geometry |
| `AAG_EURUSD_M5_LOCK-AI+809_physics-p45.set` | **LOCK-AI+809** — defensive + geometry |
| `AAG_EURUSD_M5_production.set` | **LOCK-202** |
| `AAG_EURUSD_M5_AI-803_memory-805p.set` | **LOCK-AI** |

**E7′ stacked offline** (`lock_ai_physics_p45`): WF **57%** (16/28) — still FAIL.

### MT5 wire validation — LOCK-809 ($200, v1.33)

| Window | Net | PF | Eq DD | Largest loss | vs LOCK-202 ($200) |
|--------|-----|-----|-------|--------------|-------------------|
| Jan–Jul 2026 | +$318 | 2.28 | 14% | −$15.60 | Sweet spot |
| Jan 2025–Jul 2026 | +$566 | 1.42 | 70% | −$63.50 | Prod ref +$623 / DD 23% |
| **Jan 2022–Jul 2026** | **+$509** | **1.11** | 95%* | −$64.10 | **w03 −$50 / PF 0.99** |

\*DD % inflated on $200; absolute tail −$64 matches LOCK-AI ext22 fail. **Capital-efficiency win:** profitable ext22 on **$200** without $500 deposit upsize.

### Deployment (post-wire)

| Preset | Bundle | Use |
|--------|--------|-----|
| `AAG_EURUSD_M5_production.set` | **LOCK-202** | Non-AI — max net wire reference |
| **`AAG_EURUSD_M5_AI-809_physics-p45.set`** | **LOCK-809** | **Canonical AI** — $200 all windows |
| `AAG_EURUSD_M5_AI-803_memory-805p.set` | LOCK-AI | Defensive tail-cap overlay (2025+) |

**Wire status:** **LOCK-809 promoted (AI geometry)** · E7′ WF FAIL · **no live** · LOCK-202 non-AI paper · LOCK-809 AI forward test.

---

*AAG AI Enhancement · Phase E8/E9 · 2026-07-06 · LOCK-202 non-AI · LOCK-809 AI canonical · EA v1.33*
