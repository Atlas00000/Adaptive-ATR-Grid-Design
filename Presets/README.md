# AAG Tester Presets

**Location:** `MQL5\Profiles\Tester\` (Strategy Tester → Inputs → Load)

## Production (winning stack)

| Preset | Purpose |
|---|---|
| **`AAG_EURUSD_M5_production.set`** | **Canonical preset — live chart + validation backtests** |
| `AAG_EURUSD_M5_EDGE-LOCK-202_15-17-rsi.set` | Same inputs; diagnostics **on** (enhancement / journal runs) |

**Full system profile:** [`../system-profile.md`](../system-profile.md)

Both are identical strategy settings (15–17 session, RSI rotation, SL 2× / TP 1.5× ATR, grid 6). Use **production** for deployment; copy **production** (or LOCK-202) when building E3+ test presets.

**Reference metrics (confirmed LOCK-202 / production):**

| Window | PF | Net | WR | Trades | DD (eq) |
|---|---|---|---|---|---|
| Jan–Jul 2025 | **1.93** | +$273 | 72% | 96 | 12.4% |
| Jan 2025 – Jul 2026 | **1.46** | +$623 | 66% | 324 | 23.0% |
| Longest ($200) | 0.95 | −$192 | 56% | 581 | 98% |

Enhancement must improve longest-window PF, not only Jan–Jun.

| Preset | Purpose |
|---|---|
| `AAG_EURUSD_M5_EDGE-LOCK_15-17.set` | v1 superseded (session only, no RSI) |

## Discovery archive (E0–E2) — complete

See `Edge Discovery.md` for full history. Key presets:

| Preset | Role |
|---|---|
| `EDGE-000_baseline` | Pre-edge reference |
| `EDGE-001_diagnostics` | Trade journal CSV |
| `EDGE-104-402_overlap-15-17` | Session winner → LOCK v1 |
| `EDGE-202_rsi-extreme` | Entry winner → LOCK v2 |

## Enhancement phases (E3+) — copy production

| Phase | First test | Needs code? |
|---|---|---|
| **E5** exits | **504–507** coded in v1.05 — see presets below |
| **E4** grid tail | **403 → 405 → 402 → 404** coded in v1.06 | Presets ready |
| **E3** regime | **306 → 302 → 301 → 303 → 304 → 305** coded in v1.07 | **Complete — all rejected** |
| **E6** structure | **602 → 601 → 603 → 604** coded in v1.08 | **Complete — all rejected** |
| **E7** validation | Walk-forward on production | Tester / external |

Preset naming: copy **production**, change one input group, unique `InpDiagnosticsFilePrefix`.

Each preset uses a unique CSV prefix so files do not overwrite.

### Phase E5 — exit presets (production base)

Load from Strategy Tester → Inputs → **Load**. Compare vs **production** on Jan–Jun 2025, Jan25–Jul26, longest.

| Preset | Change |
|---|---|
| `AAG_EURUSD_M5_EDGE-501_rr-flip.set` | SL 1.5×ATR, TP 2×ATR |
| `AAG_EURUSD_M5_EDGE-502_basket-tp-12.set` | Basket TP $12 — **test next** |
| `AAG_EURUSD_M5_EDGE-502_basket-tp-15.set` | Basket TP $15 (tested = production) |
| `AAG_EURUSD_M5_EDGE-502_basket-tp-20.set` | Basket TP $20 — **test next** |
| `AAG_EURUSD_M5_EDGE-502_basket-tp-25.set` | Basket TP $25 (tested = production) |
| `AAG_EURUSD_M5_EDGE-503_basket-tp-pct.set` | Basket TP 0.25% equity — **test next** |

### Phase E5 — coded exits (EA v1.05+, production base)

| Preset | Change |
|---|---|
| `AAG_EURUSD_M5_EDGE-504_trail-basket.set` | Trail: lock **50%** of peak once floating ≥ **$12** |
| `AAG_EURUSD_M5_EDGE-505_mr-exit-ema.set` | Close basket on **EMA touch** (0.05×ATR tol) |
| `AAG_EURUSD_M5_EDGE-506_adaptive-basket-tp.set` | Basket TP = **levels × 0.5 × ATR** (money) |
| `AAG_EURUSD_M5_EDGE-507_time-stop.set` | Close basket after **90 min** |

**Test order:** 504 → 505 → 506 → 507 vs `production`. Diagnostics on; check CSV for `BASKET_TRAIL`, `BASKET_MR_EMA`, `BASKET_TP_ADAPTIVE`, `BASKET_TIME_STOP`.

### Phase E4 — grid & risk (EA v1.06+, production base)

| Preset | Change |
|---|---|
| `AAG_EURUSD_M5_EDGE-403_basket-dd-cap.set` | Block new grid adds if basket loss ≥ **2% equity** |
| `AAG_EURUSD_M5_EDGE-405_mae-exit.set` | Emergency close if price **4×ATR** against anchor |
| `AAG_EURUSD_M5_EDGE-402_adaptive-depth.set` | Max **3** levels if ADX ≥ **25**, else **6** |
| `AAG_EURUSD_M5_EDGE-404_scaled-lots.set` | Lot × **0.85^level** per grid add |

**Test order:** 403 → 405 → 402 → 404 vs `production`. Check diagnostics for `basket_dd_cap`, `MAE_EXIT`.

### Phase E3 — regime gates (EA v1.07+, production base)

| Preset | Change |
|---|---|
| `AAG_EURUSD_M5_EDGE-306_seasonal-skip.set` | Skip new baskets **Jun–Sep** |
| `AAG_EURUSD_M5_EDGE-302_vol-pause.set` | Block if ATR > **1.8×** 20-bar avg |
| `AAG_EURUSD_M5_EDGE-301_adx-slope.set` | Block if ADX rising **3** bars |
| `AAG_EURUSD_M5_EDGE-303_atr-percentile.set` | Block if ATR > **80th** percentile (100 bars) |
| `AAG_EURUSD_M5_EDGE-304_chop-only.set` | Require **3+** EMA crosses in **20** bars |
| `AAG_EURUSD_M5_EDGE-305_regime-combo.set` | **302 + 301** combined |

**Test order:** 306 → 302 → 301 → 303 → 304 → 305 vs `production`. Gates apply to **new baskets only** (not grid adds).

### Phase E6 — structure & liquidity (EA v1.08+, production base)

| Preset | Change |
|---|---|
| `AAG_EURUSD_M5_EDGE-602_session-hl.set` | Buy near **session low**, sell near **session high** (0.35×ATR from 15:00) |
| `AAG_EURUSD_M5_EDGE-601_pdh-l.set` | Buy near **prior day low**, sell near **prior day high** (0.35×ATR) |
| `AAG_EURUSD_M5_EDGE-603_liq-sweep.set` | **Sweep + rejection** at session H/L (0.05×ATR min wick) |
| `AAG_EURUSD_M5_EDGE-604_range-mid.set` | Grid anchor at **session range midpoint** (levels radiate from mid) |

**Test order:** 602 → 601 → 603 → 604 vs `production`. Gates (601–603) apply to **new baskets only**; 604 shifts grid anchor only.
