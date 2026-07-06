# AAG Edge Enhancement

*EURUSD M5 — post-discovery optimisation on the locked stack.*

> **System profile:** see [`system-profile.md`](system-profile.md) for consolidated architecture, edge profile, trade profile (winners/losers), and multi-horizon performance.  
> **Composition report:** see [`compo-report.md`](compo-report.md) for full build summary.

**Phase status:** E0–E2 **complete** (edge found and entry layer locked). **E3–E6 complete** — no promotion. **E7** validation next.

**Goal:** Improve **EDGE-LOCK-202** on PF, drawdown, expectancy, and tail risk while preserving the validated session + RSI rotation core.

**Baseline for all E3+ tests:** `AAG_EURUSD_M5_production.set` (alias: `EDGE-LOCK-202_15-17-rsi`)

### Confirmed baseline — LOCK-202 / production (re-verified 2026-07-05)

Use these numbers when comparing **EDGE-504–507** (and any enhancement). Same preset: `AAG_EURUSD_M5_EDGE-LOCK-202_15-17-rsi` = `production`.

| Window | PF | Net | WR | Trades | DD (eq) | Avg win / loss |
|---|---|---|---|---|---|---|
| **Jan–Jul 2025** | **1.93** | **+$273** | **72%** | **96** | **12.4%** | +$8.22 / −$10.90 |
| **Jan 2025 – Jul 2026** | **1.46** | **+$623** | **66%** | **324** | **23.0%** | +$9.30 / −$12.42 |

*Note: short window is **Jan–Jul 2025** (7 mo), not Jan–Jul 2026.*

**Preset naming:**

```text
MQL5\Profiles\Tester\AAG_EURUSD_M5_<PHASE-ID>_<short-description>.set
```

**Test windows:**

| Window | Use |
|---|---|
| **2025-01-01 → 2025-06-30** | Primary A/B (in-sample enhancement) |
| **2025-01-01 → 2025-07-31** | Short OOS confirm (LOCK-202 reference) |
| **2025-01-01 → 2026-07-31** | Medium regime (19 months) |
| **Longest available** | Stress / tail-risk test — must not bleed |

Variable spread, $200 deposit.

**Enhancement rule:** One change per preset. Compare vs **LOCK-202**, not EDGE-000. Pass = improves ≥2 of: net, PF, DD, expectancy — without trade count < 50% of LOCK-202.

---

## What we know (validated)

Facts from E0–E2 — **do not re-test** unless LOCK-202 changes.

| Topic | Finding | Implication for E3+ |
|---|---|---|
| **When** | Edge lives in **15–17** server time (overlap core) | Session is locked; E3+ does not widen hours |
| **Entry** | **RSI rotation** (buy ≤48, sell ≥45) lifts long WR 48%→71% | E2 winner baked into LOCK-202 |
| **Direction** | Shorts dominate volume; longs few but now profitable | No sell-only required yet; structure filters optional |
| **Grid** | Full 6 levels works in 15–17; blanket max1 **rejected** | E4 = conditional containment, not depth=1 |
| **D2 adds** | Toxic on unfiltered 24h grid (93% of loss $) | In LOCK window, grid recovers (~1h 49m hold); still cap tail risk |
| **Exits** | **0 basket TP** hits historically; all SL/TP per-leg | **E5 highest priority** — avg loss ($10.90) &gt; avg win ($8.22) |
| **R:R design** | SL 2×ATR &gt; TP 1.5×ATR — WR-driven profit | Flip R:R (E501) cautiously; tune basket TP first (E502) |
| **Regime** | Bleed in expansion / session transitions (9, 16, 18–22) | E3 gates expansion **inside** 15–17, not new session search |
| **BB / HTF / EMA distance** | Over-filter or no lift vs RSI | **Dropped** — do not revisit unless combined with new logic |
| **LOCK-202 (Jan–Jul 25)** | +$273, PF 1.93, WR 72%, DD 12%, 96 trades | Short-window reference |
| **LOCK-202 (Jan 25–Jul 26)** | +$623, PF 1.46, WR 66%, DD 23%, 324 trades | **Profitable medium regime** |
| **LOCK-202 (longest)** | −$192, PF 0.95, WR 56%, DD 98%, 581 trades | **Edge degrades** — fat-tail losses |

### Remaining weaknesses (enhancement targets)

1. **Per-leg R:R inverted** — avg loss still > avg win at all horizons; basket TP at $50 rarely/never hits.
2. **Fat-tail losses** — longest test: largest loss **−$66**, avg loss −$14.76 vs avg win +$10.88; DD → 98%.
3. **Seasonal regime** — **Jan–May strong**, activity and net drop **Jun–Dec** (visible on 19-month run).
4. **PF decay over time** — 1.93 (7 mo) → 1.46 (19 mo) → **0.95 (longest)**; edge is real but not stationary.
5. **Walk-forward required** — profitable on medium window does not guarantee full-history survival.

<details>
<summary>Historical baseline, diagnostics, session search, entry filters (click to expand)</summary>

### Baseline snapshot (Phase 1 — EDGE-000)

| Metric | Value | Implication |
|---|---|---|
| Net profit | -$180.10 on $200 | Strategy is net negative in current form |
| Profit factor | 0.67 | Losses dominate gross profit |
| Win rate | 47.6% (119 / 131) | Below 50%; not compensated by R:R |
| Avg win / avg loss | $3.09 / -$4.18 | **Negative expectancy** (~-$0.72/trade) |
| Max DD | 90% | Grid stacking + fixed lot on small account |
| Total trades | 250 (~Jan cluster) | High frequency → spread + SL accumulation |
| Short WR / Long WR | 49.3% / 45.5% | Shorts slightly better; both sub-50% |
| Avg hold time | ~22 min | Scalping-style; exits are fast SL/TP hits |
| MAE correlation | 0.83 | Trades that go ~4+ units against rarely recover |
| MFE correlation | 0.84 | Favorable moves exist but are not captured fully |

### Core diagnosis

The EA **does find rotational moves** (MFE shows price often moves in your favour). The problem is **trade quality control and failure containment**:

1. **Entries are too permissive** — ADX < 20 + loose EMA flat rule fires in weak rotation *and* in pre-breakout compression.
2. **Grid adds into adverse expansion** — buy grids layer as price falls; each leg carries individual SL (2×ATR). One directional push stops out multiple levels.
3. **R:R realization is inverted** — designed SL (2×ATR) > TP (1.5×ATR) per leg; with ~48% WR this guarantees slow bleed unless basket TP saves the basket. Basket TP ($50 on $200) is too far relative to per-leg outcomes.
4. **No session/regime gate** — worst hours (9, 16, 18–22) align with open spikes, London close, and NY momentum — exactly when mean-reversion grids fail.
5. **No volatility ceiling** — ATR grid widens in volatility but still opens; expansion regimes invalidate mean reversion.

**Edge hypothesis:** The EA’s edge lives in **quiet rotational microstructure** (London mid-session, lower ADX, moderate ATR, flat HTF). It bleeds during **session transitions, trend expansion, and stacked grid stop-outs**.

---

## Fundamental win vs loss patterns

### What winners look like

| Pattern | Evidence |
|---|---|
| Price rotates within ATR band | High MFE correlation; winners reach TP zone |
| Low trend pressure | ADX gate passes; EMA flat or mild slope |
| Few grid levels filled | 1–2 legs, basket or TP closes before deep stacking |
| London mid-session (10–13) | Profit clusters in hour-of-day chart |
| Tue / Wed / Fri | Weekday chart shows better blue bars |

### What losers look like

| Pattern | Evidence |
|---|---|
| Adverse excursion ≥ ~4 units then SL | MAE chart — no recovery above that threshold |
| Multi-leg grid in one direction | Several SL hits ≈ -$4 each → wipes many small wins |
| Session open / close / NY evening | Hours 9, 16, 18–19, 21–22 heavily red |
| Thursday | Largest single weekday loss cluster |
| Longs in bearish micro-trend | Long WR 45.5% < Short WR 49.3% (Jan 2025 context) |

### What we know vs what we still need

| Known (from report) | Still need (export / code) |
|---|---|
| Hour-of-day edge map | Per-trade log: ADX, ATR, levels filled, session tag |
| Weekday bias | MFE/MAE at entry by regime bucket |
| MAE failure threshold | Win rate by grid depth (L0 vs L2 vs L5) |
| Avg hold ~22 min | % closed by SL vs TP vs basket TP |
| PF 0.67, negative expectancy | Forward test vs backtest slippage sensitivity |

---

## Session & structure — when it works / fails

| Window (broker server time) | Performance | Likely reason |
|---|---|---|
| 00–08 Asian | Low volume, mixed/small green | Quiet range; fewer grids triggered |
| **09** | **Heavy losses** | EU pre-open / spike / false rotation |
| **10–13** | **Best pocket** | London liquidity, two-way auction |
| 14–15 | Mixed | Continuation of London rotation |
| **16** | **Losses** | London close, trend handoff |
| 17 | Transition | Pre-NY positioning |
| **18–19, 21–22** | **Losses** | NY momentum, expansion |
| **Thursday** | **Worst day** | ECB/USD macro, trend days common |
| Tue / Wed / Fri | Relatively better | More rotational EU/US overlap |

**Structural implication (concept-aligned):** Phase 2 should trade **near session VWAP / prior day H-L / range midpoint** in London core only — not 24h blind grid.

---

## Optimisation levers (priority order)

### 1. Failure containment (highest ROI)

- Cap grid depth dynamically (e.g. max 3 levels if ADX rising).
- **Stop adding** when basket floating loss > X% equity.
- Reduce lot on levels 2+ (progressive sizing inverse — smaller adds).
- Emergency basket close when MAE exceeds threshold (from your MAE chart: ~4 units).

### 2. Entry quality

- BB rejection confirm (close outside → back inside).
- RSI filter (buy ≤35 / sell ≥65) — only in rotation.
- HTF EMA (M15/H1): buy grid only above HTF EMA, sell below.
- Require **minimum distance from EMA** (don’t buy into falling knife at EMA).

### 3. Exit & trade management

- **Widen TP or tighten SL** on leg 1 only; test SL 1.5×ATR / TP 2×ATR (flip R:R for grid first entry).
- **Basket trailing** — lock 50% at +$15, trail rest (Phase 2 `BasketManager`).
- **Mean-reversion exit** — close basket when price crosses grid centre / EMA.
- **Adaptive basket TP** — scale target with levels filled and ATR (lower TP for deep baskets to escape).
- Partial basket close at breakeven after N minutes underwater.

### 4. Regime detection

- ADX **slope** rising → block new baskets (not just level).
- ATR percentile: block if ATR > 80th percentile of 20-day range.
- Volatility pause (max ATR threshold).
- Choppiness / range detection: only trade when price crossed EMA 3+ times in 20 bars.

---

## Implementation phases & task IDs

Work **one ID at a time** → implement → preset → backtest → record PF, WR, DD, avg win/loss → proceed.

---

### Phase E0 — Diagnostics (no strategy change)

| ID | Task | Output | Preset | Status |
|---|---|---|---|---|
| **EDGE-000** | Baseline archive | Reference metrics | `Profiles\Tester\AAG_EURUSD_M5_EDGE-000_baseline.set` | Preset ready |
| **EDGE-001** | Trade journal CSV: hour, weekday, level, exit reason, ADX, ATR | `AAG_diag_trades_*.csv` | `Profiles\Tester\AAG_EURUSD_M5_EDGE-001_diagnostics.set` | **Implemented** |
| **EDGE-002** | Grid depth buckets from summary CSV | Table below | Same as EDGE-001 | Run after EDGE-001 |
| **EDGE-003** | Jan 2025 vs full 2025 | Two reports | EDGE-001 + date ranges | See `Docs/E0-run-guide.md` |

**Gate to Phase E1:** Confirm ≥60% of loss $ comes from baskets with ≥3 levels OR hours 9/16/18–22. Printed automatically in Journal on test end.

**Run guide:** `Docs/E0-run-guide.md`

#### E0 Results — EDGE-001 (`AAG_EURUSD_M5_EDGE-001_diagnostics`)

**Report:** Net -$180.10 | PF 0.67 | WR 47.6% | DD 90% | 250 trades | Avg win $3.09 / avg loss -$4.18

**Gate analysis (from `AAG_diag_trades_EURUSD.csv`):**

| Metric | Value |
|---|---|
| Loss from basket depth ≥3 | **0%** (max depth reached = **2**) |
| Loss from bad hours (9,16,18-19,21-22) | **27.8%** |
| Loss from 2-level baskets (D2) | **93.0%** |
| Basket TP exits | **0** |
| Original gate pass? | **NO** |

**EDGE-002 — By leg level:**

| Level | Trades | Wins | WR% | P/L |
|---|---|---|---|---|
| L0 | 153 | 73 | 47.7% | -$113.50 |
| L1 | 97 | 46 | 47.4% | -$66.60 |
| L2+ | 0 | — | — | — |

**EDGE-002 — By basket depth:**

| Depth | Trades | Wins | WR% | P/L |
|---|---|---|---|---|
| D1 | 66 | 57 | **86.4%** | **+$134.70** |
| D2 | 184 | 62 | 33.7% | **-$314.80** |
| D3+ | 0 | — | — | — |

**Exit split:** SL 131 (-$548) | TP 119 (+$368) | BASKET **0**

**EDGE-003 — By month:**

| Month | Trades | WR% | P/L |
|---|---|---|---|
| Jan–Jun 2025 | 250 | 47.6% | -$180.10 |

**E0 conclusion:** D2 grid adds are toxic, but **max-1-level alone does not fix P/L** (EDGE-401: -$184, all D1). D1 +$135 in baseline was a *subset* of good rotations, not all first entries. **Next:** entry filters (EDGE-105/201) + conditional grid or R:R on singles — not blanket depth cap.

**CSV:** `Terminal\Common\Files\AAG_diag_trades_EURUSD.csv`

---

### Phase E1 — Session & time filters (`RiskManager`) — **Implemented v1.02**

| ID | Task | Preset | Status |
|---|---|---|---|
| **EDGE-101** | Hours **10–13** only | `AAG_EURUSD_M5_EDGE-101_london-core.set` | Ready |
| **EDGE-102** | Block **Thursday** | `AAG_EURUSD_M5_EDGE-102_no-thursday.set` | Ready |
| **EDGE-103** | Blacklist hours **9,16,18,19,21,22** | `AAG_EURUSD_M5_EDGE-103_hour-blacklist.set` | Ready |
| **EDGE-104** | Overlap window **13–17** | `AAG_EURUSD_M5_EDGE-104_overlap.set` | Ready |
| **EDGE-105** | **10–13 + no Thursday** (combo) | `AAG_EURUSD_M5_EDGE-105_combo-session.set` | Ready |

All presets in `MQL5\Profiles\Tester\`. Test **one preset at a time** vs EDGE-000.

**E1 + E4 combos (after EDGE-104):**

| Preset | Description |
|---|---|
| `AAG_EURUSD_M5_EDGE-104-401_overlap-max1.set` | **13–17 + max 1 level** — **tested / rejected** |
| `AAG_EURUSD_M5_EDGE-104-402_overlap-15-17.set` | 15–17 only — **tested / PASS** (first profitable) |
| `AAG_EURUSD_M5_EDGE-104-402_sell-only.set` | 15–17 + sell-only — **run next** (shorts 74% WR) |

**Success criteria:** PF > 1.0, DD < 40%, trade count reduced ≥30%.

### Phase E2 — Entry confirmation — **complete**

RSI rotation (EDGE-202) won → baked into LOCK-202. BB, HTF EMA, EMA distance rejected.

</details>

---

## Locked stack — **v2 adopted (EDGE-LOCK-202)**

**Current:** `AAG_EURUSD_M5_production.set` (= `EDGE-LOCK-202_15-17-rsi`, E2 winner)

| Layer | Setting | Source |
|---|---|---|
| Session | Hours **15–17** | EDGE-104-402 |
| Grid | Max **6** levels | Phase 1 default |
| Risk | 0.10 lot, SL 2×ATR, TP 1.5×ATR | Phase 1 default |
| Basket TP | $50 money target | Phase 1 default |
| Entry filter | **RSI rotation** — buy ≤48, sell ≥45 | **EDGE-202** |

**Validated (Jan–Jul 2025):** Net **+$273** | PF **1.93** | WR **72%** | DD **12%** | 96 trades

**Extended regime tests (same preset, no code change):**

| Window | Net | PF | WR | DD | Trades | Notes |
|---|---|---|---|---|---|---|
| Jan 2025 – Jul 2026 | **+$623** | **1.46** | 66% | 23% | 324 | Still profitable; PF/WR soften vs 7 mo |
| Longest available | **−$192** | **0.95** | 56% | **98%** | 581 | Net negative; tail losses dominate |

See **Regime analysis** below — enhancement must lift PF on longest window and cap −$66 outliers.

**Superseded v1:** `AAG_EURUSD_M5_EDGE-LOCK_15-17.set` — Jan–Jun +$174, PF 1.23, 184 trades (no E2 filter)

All **Phase E3+** presets inherit **LOCK-202** and change one layer only.

---

## Regime analysis (LOCK-202 extended tests)

LOCK-202 on a **longer horizon** reveals where the edge holds and where it bleeds. Enhancement phases should target these patterns — not rediscover session/RSI.

### Time-of-day (unchanged)

All runs cluster **15:00–18:00** (preset 15–17 + bar close timing). No edge outside this block. **Do not widen hours.**

### Seasonal / monthly regime

| Period | Pattern (Jan 25 – Jul 26 run) |
|---|---|
| **Jan–May** | Highest trade count (~35–40/mo) and strongest gross profit |
| **Jun–Dec** | Lower activity (~25–30/mo); net profit flattens or turns red |
| **H2 weakness** | Jun–Sep notably weaker on P/L charts — candidate for E3 seasonal gate or reduced size |

**Implication:** E3 should add **month/season awareness** (or ATR regime) to skip or downsize H2 bleed — not just intraday filters.

### Horizon decay (PF vs sample length)

```text
Jan–Jul 2025     PF 1.93   WR 72%   DD 12%    ← discovery sweet spot
Jan 25 – Jul 26  PF 1.46   WR 66%   DD 23%    ← still tradeable
Longest test     PF 0.95   WR 56%   DD 98%    ← fails without tail control
```

Edge is **real in favourable regime** but **not robust** across full history without exit/containment fixes.

### Loss anatomy (longest test)

| Metric | Longest test | Jan–Jul 2025 |
|---|---|---|
| Avg win / avg loss | +$10.88 / **−$14.76** | +$8.22 / −$10.90 |
| Largest loss | **−$66.00** | ~−$12 |
| Max consec losses | **6** | 3 |
| Short WR | 54.8% (520 trades) | 72% |
| Long WR | 68.9% (61 trades) | 71% |

WR stays above 50% on longest run but **loss size kills equity** — classic negative expectancy from fat tails. Short WR collapses from 72% → 55% over extended sample (more bad regimes included).

### Enhancement priorities (informed by regime)

| Priority | Phase | Target regime problem |
|---|---|---|
| **1** | E5 exits | Avg loss > avg win; basket TP never fires; capture MFE |
| **2** | E4 tail cap | −$66 outliers; max 6 consec losses; basket stack bleed |
| **3** | E3 regime | H2 / high-ATR months; short WR collapse in bad regimes |
| **4** | E7 validation | Pass must include **longest window PF ≥ 1.1**, not just Jan–Jun |

**Gate to promote any enhancement:** Must improve **both** Jan–Jun 2025 **and** not worsen longest-test PF (or lift longest PF above 1.0).

### E2 phase complete — summary

| ID | Trades | Net (Jan–Jul) | PF | Verdict |
|---|---|---|---|---|
| **EDGE-202** | **96** | **+$273** | **1.93** | **Winner → LOCK v2** |
| EDGE-204 | 171 | +$162 | 1.23 | LOCK-tier; loses to 202 |
| EDGE-201 | 22 | +$63 | 2.61 | Over-filtered |
| EDGE-203 | 18 | +$53 | 2.68 | BB+RSI too strict |
| EDGE-205 | **0** | $0 | — | EMA stretch conflicts with base signal |

---

## Enhancement roadmap (E3–E7)

All presets copy **LOCK-202** inputs and change **one layer**. Compare vs LOCK-202 on Jan–Jun 2025.

### Priority order

```text
E5 exits (basket TP, trailing)     ← avg loss > avg win; fat tails on longest test
  → E4 grid tail containment       ← −$66 outliers; 6 consec losses
  → E3 regime gates                ← H2 seasonal bleed; short WR collapse
  → E7 walk-forward + longest-window gate  ← PF 0.95 on full history = not live-ready
  → E6 structure refinements       ← optional polish inside 15–17
```

---

### Phase E5 — Exit & trade management — **Priority 1**

**Why now:** LOCK-202 still has avg loss ($10.90) > avg win ($8.22). Historical runs: **0 basket TP exits**; all closes are per-leg SL/TP.

| ID | Task | Targets | Preset | Status |
|---|---|---|---|---|
| **EDGE-501** | Flip leg R:R: SL 1.5× / TP 2× ATR | Per-leg economics | `AAG_EURUSD_M5_EDGE-501_rr-flip.set` | **Promising economics — not adopted** (PF below LOCK-202) |
| **EDGE-502** | Lower basket TP (money) | Reachable basket exit | see variants below | **$25 tested — no change** |
| | Basket TP **$12** | Aggressive — near avg win | `AAG_EURUSD_M5_EDGE-502_basket-tp-12.set` | **Ready to test** |
| | Basket TP **$15** | Mid target | `AAG_EURUSD_M5_EDGE-502_basket-tp-15.set` | **Tested 2025 — = production** |
| | Basket TP **$20** | Tune matrix level | `AAG_EURUSD_M5_EDGE-502_basket-tp-20.set` | **Ready to test** |
| | Basket TP **$25** | First E5 attempt | `AAG_EURUSD_M5_EDGE-502_basket-tp-25.set` | **Rejected — = production** |
| **EDGE-503** | Basket TP **0.25%** equity | Scale with account | `AAG_EURUSD_M5_EDGE-503_basket-tp-pct.set` | **Ready to test** |
| **EDGE-504** | Trailing basket: lock 50% at +$12 | Capture MFE (0.86 corr) | `AAG_EURUSD_M5_EDGE-504_trail-basket.set` | **Tested ext — rejected vs production** |
| **EDGE-505** | Mean-reversion exit at EMA touch | Rotation-aligned exit | `AAG_EURUSD_M5_EDGE-505_mr-exit-ema.set` | **Tested ext — catastrophic reject** |
| **EDGE-506** | Adaptive basket TP ∝ levels × ATR | Deep-basket escape | `AAG_EURUSD_M5_EDGE-506_adaptive-basket-tp.set` | **Tested ext — rejected vs production** |
| **EDGE-507** | Time stop: close if open > 90 min | Cap underwater hold | `AAG_EURUSD_M5_EDGE-507_time-stop.set` | **Tested ext — rejected vs production** |

**Suggested test order (coded E5):** **504** → **505** → **506** → **507** (one at a time vs `production`). Recompile **AAG v1.05** before loading presets.

**501 reserve:** Keep **LOCK-202** as the only enhancement baseline. **EDGE-501** stays on file as a **promising alternate stack** — healthier avg win/loss (+$10.88 / −$8.18) and PF 1.64 / 1.29 — to revisit after coded exits (E504/E403) or as a hybrid target (LOCK entries + 501-style leg economics).

**Pass:** PF ≥ 2.0 **or** avg win ≥ avg loss; net ≥ LOCK-202; DD ≤ 15%; trades ≥ 50% LOCK-202.

---

### Phase E4 — Grid & risk containment — **Priority 2**

**Why now:** Grid works in LOCK-202 but tail losses (3 consec, -$54) remain. **Do not** retest blanket max1 (EDGE-401 rejected).

| ID | Task | Targets | Preset | Status |
|---|---|---|---|---|
| **EDGE-403** | Stop adding if basket DD > 2% equity | Cap stack bleed | `AAG_EURUSD_M5_EDGE-403_basket-dd-cap.set` | **Tested ext — rejected vs production** |
| **EDGE-405** | Emergency close if MAE > 4×ATR | MAE failure threshold | `AAG_EURUSD_M5_EDGE-405_mae-exit.set` | **Tested ext — hard reject** |
| **EDGE-402** | Dynamic max levels (ADX-based) | Depth only when rotation | `AAG_EURUSD_M5_EDGE-402_adaptive-depth.set` | **Tested ext — = production** |
| **EDGE-404** | Decreasing lot per level | Smaller adds = smaller tail | `AAG_EURUSD_M5_EDGE-404_scaled-lots.set` | **Tested ext — below production** |
| ~~EDGE-401~~ | ~~Max 1 level~~ | — | — | **Archived — rejected** |

**Suggested test order (E4):** **403** → **405** → **402** → **404** vs `production`. Recompile **AAG v1.06** first. Windows: Jan–Jul 2025 + Jan 2025–Jul 2026.

**Pass:** Max consec losses ≤ 3; DD ≤ 12%; net ≥ production −5%.

---

### Phase E3 — Regime & volatility gates — **COMPLETE (all rejected)**

**Why now:** Extended tests show **H2 seasonal weakness** (Jun–Sep) and short WR drop (72% → 55%) on longest run. Gate bad regimes inside 15–17 — including **month/season**, not only intraday ATR.

| ID | Task | Targets | Preset | Status |
|---|---|---|---|---|
| **EDGE-302** | ATR pause: no new basket if ATR > 1.8× 20-bar avg | Vol expansion / news days | `AAG_EURUSD_M5_EDGE-302_vol-pause.set` | **Tested ext — = production** |
| **EDGE-306** | **Seasonal gate: skip Jun–Sep** | H2 bleed from regime chart | `AAG_EURUSD_M5_EDGE-306_seasonal-skip.set` | **Tested ext — hard reject** |
| **EDGE-301** | ADX slope: block if ADX rising 3 bars | Trend building | `AAG_EURUSD_M5_EDGE-301_adx-slope.set` | **Tested ext — below production** |
| **EDGE-303** | ATR percentile cap (80th) | High-vol day skip | `AAG_EURUSD_M5_EDGE-303_atr-percentile.set` | **Tested ext — rejected vs production** |
| **EDGE-304** | Chop-only: 3+ EMA crosses in 20 bars | Rotation confirm | `AAG_EURUSD_M5_EDGE-304_chop-only.set` | **Tested ext — rejected vs production** |
| **EDGE-305** | Combo: 301 + 302 | Stricter regime | `AAG_EURUSD_M5_EDGE-305_regime-combo.set` | **Tested ext — rejected (= 301)** |

**Suggested test order (E3):** **306** → **302** → **301** → **303** → **304** → **305** vs `production`. Recompile **AAG v1.07**. Windows: Jan–Jul 2025 + Jan 2025–Jul 2026 + longest.

**Pass:** PF ≥ production on Jan–Jul 2025 **and** longest-window PF ≥ 1.0; max consec losses ≤ 4.

**E3 conclusion (2026-07-05):** All six gates tested on Jan 25–Jul 26 ext. **None promote.** 302 inert in 15–17; 301/305 marginal harm; 303/304 over-filter; **306 removes profitable summer pocket** and **DD worse** (41% vs 23%). Keep production with E3 **off**. **Next: E7** walk-forward / longest-window validation on production baseline.

---

### Phase E6 — Structure & liquidity — **COMPLETE (all rejected)**

**Why now:** E3–E5 complete with no promotion. Structure layers refine entries **within** 15–17 — align with concept Phase 2 (PD H/L, session bounds, sweep rejection, range-mid anchor).

| ID | Task | Logic | Preset | Status |
|---|---|---|---|---|
| **EDGE-601** | Prior day H/L boundary | Buy if close ≤ PDL + 0.35×ATR; sell if close ≥ PDH − 0.35×ATR | `AAG_EURUSD_M5_EDGE-601_pdh-l.set` | **Tested ext — hard reject** |
| **EDGE-602** | Session high/low filter | Buy near session low, sell near session high (from 15:00) | `AAG_EURUSD_M5_EDGE-602_session-hl.set` | **Tested ext — hard reject** |
| **EDGE-603** | Liquidity sweep + rejection | Wick beyond session H/L then close back inside (0.05×ATR min sweep) | `AAG_EURUSD_M5_EDGE-603_liq-sweep.set` | **Tested ext — hard reject** |
| **EDGE-604** | Range midpoint grid anchor | Grid levels radiate from session mid; first leg still at market | `AAG_EURUSD_M5_EDGE-604_range-mid.set` | **Tested ext — rejected** |

**Suggested test order (E6):** **602 → 601 → 603 → 604** vs `production`. Recompile **AAG v1.08**. Windows: Jan–Jul 2025 + Jan 25–Jul 26 ext.

**Pass:** Net and PF ≥ production; trades ≥ 30% production (97+ on ext); DD ≤ production.

**E6 conclusion (2026-07-05):** All four structure layers tested on Jan 25–Jul 26 ext. **None promote.** 601/602/603 **over-filter** (38/32/7 trades); 604 keeps volume (+369 trades) but **anchor mismatch** worsens DD (42% vs 23%) and net **−$101**. Keep production with E6 **off**. **Next: E7** walk-forward / longest-window validation.

---

### Phase E7 — Validation — **Before live**

| ID | Task | When |
|---|---|---|
| **EDGE-702** | Walk-forward: 3m train / 1m test rolls on LOCK-202 | After E5/E4 winner stacked |
| **EDGE-703** | Monte Carlo on trade sequence | DD tail risk check |
| **EDGE-701** | AI regime classifier | Defer — needs labelled bars |

**Gate to live:** LOCK-202 (+ enhancements) profitable on Jan–Jun **and** longest-window PF ≥ 1.1; max DD < 25% on 19-month run; walk-forward ≥ 3/4 windows pass.

---

## Acceptance targets

| Metric | LOCK-202 Jan–Jul 25 | Jan 25–Jul 26 | Longest test | Enhancement stretch |
|---|---|---|---|---|
| Profit factor | 1.93 | 1.46 | 0.95 | **≥1.1 longest**; ≥1.5 Jan–Jun |
| Win rate | 72% | 66% | 56% | ≥ 65% Jan–Jun |
| Max DD | 12% | 23% | 98% | **< 25%** on 19-mo |
| Net ($200) | +$273 | +$623 | −$192 | Positive longest |
| Avg win vs loss | 8.2 / 10.9 | 9.3 / 12.4 | 10.9 / 14.8 | **avg win ≥ avg loss** |
| Largest loss | ~−$12 | ~−$16 | **−$66** | cap < −$25 |
| Basket TP exits | 0 | — | — | > 0 |

---

## Enhancement priority map

| Lever | Phase | Why (given LOCK-202) |
|---|---|---|
| Lower / adaptive basket TP | **E502, E506** | $50 basket never hits |
| Trailing basket | **E504** | MFE corr 0.86 — capture more |
| Basket DD cap / MAE exit | **E403, E405** | Tail loss clusters |
| ATR / ADX regime gate | **E302, E301** | H2 bleed; short WR collapse |
| Seasonal gate (Jun–Sep) | **E306** (new) | From 19-month regime chart |
| Walk-forward + longest | **E702** | PF 0.95 on full history |
| ~~Session search~~ | E1 | **Done** |
| ~~Entry extremes~~ | E2 | **Done — RSI only** |
| ~~Blanket max1~~ | E401 | **Rejected** |
| Structure / PD H-L | E6 | Optional polish |

---

## Enhancement checklist

```text
[ ] Preset = LOCK-202 + one change; saved as AAG_EURUSD_M5_<ID>_<desc>.set
[ ] Re-test on Jan–Jun 25, Jan 25–Jul 26, and longest window
[ ] Compare vs LOCK-202: net, PF, WR, DD, avg win/loss, trade count
[ ] Pass ≥2 of: net↑ PF↑ DD↓ expectancy↑; trades ≥ 50% LOCK-202
[ ] Log result below; stack winner into LOCK-202 v3 if promoted
```

### Results log (discovery + enhancement)

| ID | Date | PF | WR | DD% | Net | Notes |
|---|---|---|---|---|---|---|
| EDGE-000 | | 0.67 | 47.6% | 90% | -180 | Baseline Jan–Jun 2025 |
| EDGE-001 | 2026-07-05 | 0.67 | 47.6% | 90% | -180 | D1 +$135 / D2 -$315; 0 basket exits |
| tune_sl15-tp20_max3 | 2026-07-05 | 0.60 | 30.6% | 93% | -185 | D1 +$26 / D2 -$211; R:R flip hurt WR |
| EDGE-401 | 2026-07-05 | 0.65 | 47.1% | 92% | -184 | All D1 only — **no improvement** vs baseline |
| EDGE-101 | 2026-07-05 | 0.43 | 36.8% | 91% | -182 | 10–13 only; trades -70% but **worse** WR/PF |
| EDGE-102 | 2026-07-05 | 0.82 | 51.8% | 96% | -189 | No Thu; WR↑ PF↑ but DD worse, net similar |
| EDGE-103 | 2026-07-05 | 0.63 | 44.4% | 91% | -181 | Blacklist hrs; trades -42% but **same net**, D2 -$260 |
| EDGE-104 | 2026-07-05 | 0.91 | 54.3% | 71% | -112 | 13–17 overlap; D1 +$538 / D2 -$650 |
| EDGE-104-401 | 2026-07-05 | 0.84 | 52.2% | 80% | -141 | Overlap + max1; **rejected** |
| **EDGE-104-402** | **2026-07-05** | **1.23** | **62.0%** | **25%** | **+174** | **15–17; adopted as EDGE-LOCK** |
| EDGE-LOCK | — | 1.23 | 62.0% | 25% | +174 | Re-run v1.03 to confirm identical |
| EDGE-201 | 2026-07-05 | 2.61 | 77.3% | 12% | +63 | v1.04 full yr 2025 — 22 trades; quality yes, volume low |
| **EDGE-202** | **2026-07-05** | **1.93** | **71.9%** | **12%** | **+273** | v1.04 Jan–Jul 2025 — **best E2; adopt candidate** |
| EDGE-203 | 2026-07-05 | 2.68 | 77.8% | 12% | +53 | Jan–Jul 2025 — 18 trades; BB+RSI too strict |
| EDGE-204 | 2026-07-05 | 1.23 | 62.0% | 19% | +162 | Jan–Jul 2025 — ~LOCK; loses to 202 |
| EDGE-205 | 2026-07-05 | n/a | n/a | 0% | 0 | Jan–Jul 2025 — **0 trades**; conflicts with EMA base |
| **EDGE-LOCK-202** | — | 1.93 | 72% | 12% | +273 | Jan–Jul 2025 reference |
| LOCK-202 ext | 2026-07-05 | 1.46 | 66% | 23% | +623 | **Jan 25 – Jul 26** (19 mo) |
| LOCK-202 stress | 2026-07-05 | 0.95 | 56% | 98% | −192 | Longest ($200) — not live-ready |
| EDGE-502 | 2026-07-05 | 1.93 / 1.46 / 0.99 | 72% / 66% / 57% | 12% / 23% | +273 / +623 / −50 | **= LOCK-202** on 6mo & 19mo; $25 TP never fires |
| **EDGE-501** | 2026-07-05 | **1.64 / 1.29** | **55%** | **15% / ~17% eq** | **+$203** (Jan–Jul) | R:R flip: avg win **$10.88** > avg loss **$8.18**; PF/net below LOCK-202 |
| EDGE-502-15 | 2026-07-05 | **1.93** | **72%** | **12.4%** | **+$273** | Full 2025 — **identical to LOCK-202**; basket TP $15 never fires |
| **EDGE-504** | 2026-07-05 | **1.30** | **63%** | **23.4%** | **+$389** | Jan 25–Jul 26 ext — **below production** (PF 1.46, +$623) |
| **EDGE-505** | 2026-07-05 | **0.08** | **13%** | **90%** | **−$180** | Jan 25–Jul 26 ext — **account killer**; avg hold **15s** |
| **EDGE-506** | 2026-07-05 | **1.28** | **80%** | **46.9%** | **+$223** | Jan 25–Jul 26 ext — WR↑ but net **−$400** vs production |
| **EDGE-507** | 2026-07-05 | **1.20** | **57%** | **62.0%** | **+$244** | Jan 25–Jul 26 ext — time stop fires; DD **62%**, net **−$379** |
| **EDGE-402** | 2026-07-05 | **1.46** | **66%** | **23.0%** | **+$623** | Jan 25–Jul 26 ext — **identical to production**; ADX≥25 rare in 15–17 |
| **EDGE-404** | 2026-07-05 | **1.43** | **66%** | **23.7%** | **+$565** | Jan 25–Jul 26 ext — scaled lots active; net **−$58** vs production |
| **EDGE-405** | 2026-07-05 | **1.00** | **57%** | **79.0%** | **+$5** | Jan 25–Jul 26 ext — MAE exit kills edge; **PF 1.0, DD 79%** |
| **EDGE-403** | 2026-07-05 | **1.30** | **63%** | **28.4%** | **+$344** | Jan 25–Jul 26 ext — DD cap fires; **−$279** net vs production |
| **EDGE-301** | 2026-07-05 | **1.44** | **66%** | **28.1%** | **+$595** | Jan 25–Jul 26 ext — ADX slope fires lightly; **−$28** vs production |
| **EDGE-302** | 2026-07-05 | **1.46** | **66%** | **23.0%** | **+$623** | Jan 25–Jul 26 ext — **identical to production**; ATR pause never fires in 15–17 |
| **EDGE-303** | 2026-07-05 | **1.27** | **63%** | **35.6%** | **+$307** | Jan 25–Jul 26 ext — 80th pct fires; **−$316** net, DD worse |
| **EDGE-304** | 2026-07-05 | **1.36** | **64%** | **28.8%** | **+$250** | Jan 25–Jul 26 ext — chop gate; **143 trades** (4 longs!), **−$373** net |
| **EDGE-305** | 2026-07-05 | **1.44** | **66%** | **28.1%** | **+$595** | Jan 25–Jul 26 ext — combo **= EDGE-301**; 302 inert, **−$28** vs production |
| **EDGE-306** | 2026-07-05 | **1.34** | **64%** | **41.3%** | **+$359** | Jan 25–Jul 26 ext — skip Jun–Sep; **−$264** net, **DD 41%** (worse than prod) |
| **EDGE-601** | 2026-07-05 | **1.35** | **61%** | **49.4%** | **+$160** | Jan 25–Jul 26 ext — PD H/L gate; **38 trades** (5 longs), **−$463** net, DD **49%** |
| **EDGE-602** | 2026-07-05 | **1.65** | **69%** | **45.8%** | **+$154** | Jan 25–Jul 26 ext — session H/L; **32 trades**, **−$469** net, DD **46%** |
| **EDGE-603** | 2026-07-05 | **4.50** | **86%** | **15.9%** | **+$80** | Jan 25–Jul 26 ext — liq sweep; **7 trades** (0 longs!), **−$543** net |
| **EDGE-604** | 2026-07-05 | **1.31** | **64%** | **41.6%** | **+$522** | Jan 25–Jul 26 ext — range-mid anchor; **369 trades**, **−$101** net, DD **42%** |

#### EDGE-104-402 detail (overlap 15–17)

| Metric | Value |
|--------|-------|
| Net | **+$173.80** |
| PF | 1.23 |
| WR | 61.96% (114W / 70L) |
| DD | 25.3% ($89) |
| Trades | 184 |
| Expectancy | +$0.94/trade |
| Sharpe | 5.54 |
| Avg win / loss | +$8.22 / -$10.91 |
| Short WR | **73.7%** (99 trades) |
| Long WR | 48.2% (85 trades) |
| Avg hold | ~1h 46m |

**E1 success criteria:** PF > 1.0 ✓ | DD < 40% ✓ | trades -60% vs EDGE-104 ✓

**vs EDGE-104:** Net flipped **+$174 vs -$112**. Dropping hours 13–14 and 16 removed the bleed while keeping full grid (6 levels). WR +8 pts, DD cut from 71% → 25%.

**vs EDGE-104-401:** Proves the fix is **session refinement**, not max1. Full grid in the right 3-hour window beats singles across 13–17.

**Direction split:** Shorts carry the edge (74% WR); longs near coin-flip (48%). Sell-only combo is the obvious next test.

**Test window:** Jan–Jun 2025 — **same range as all EDGE runs above** (apples-to-apples).

**Caveat:** Avg loss still > avg win — profitability is WR-driven. Next validation: extend to **Jul–Dec 2025** or full year; run diagnostics CSV for D1/D2 split.

**Verdict:** **PASS — adopt as Phase E baseline.** Next: sell-only preset, then EDGE-204 HTF filter on longs.

#### EDGE-104-401 detail (overlap + max1)

| Metric | Value |
|--------|-------|
| Net | **-$141.10** |
| PF | 0.84 |
| WR | 52.2% (164W / 150L) |
| DD | ~80% |
| Trades | 314 (all D1 / L0 only) |
| Avg win / loss | +$4.52 / -$5.89 |
| Short WR | 57.8% (142 trades) |
| Long WR | 47.7% (172 trades) |

**Depth:** max depth 1 on all baskets — D2 adds fully blocked.

**vs EDGE-104:** Net **worse** (-$141 vs -$112) despite removing D2 losses. More marginal first entries (314 singles at 52% WR) vs 104’s selective D1 bucket (143 baskets at ~93% WR, +$538). Session filter helps vs bare max1 (-$184) but **max1 on overlap is the wrong combo**.

**Month:** April +$51 only green month; May -$101 worst.

**Hour:** 17:00 least bad (-$12); 16:00 worst (-$45).

**Verdict:** **Rejected combo.** Keep EDGE-104 as best E1; pursue **EDGE-104-402** (15–17), sell bias / HTF filter (EDGE-204), or conditional grid (EDGE-403) instead of blanket max1.

#### EDGE-201 detail (LOCK + BB rejection)

| Metric | Value |
|--------|-------|
| Net | +$7.90 |
| PF | n/a (0 losses) |
| WR | 100% (1W / 0L) |
| DD | 4.4% equity ($8.90) |
| Trades | **1** (1 short) |
| Avg hold | 1h 3m |
| Entry | Jun, Wed, hour 15 |

**vs EDGE-LOCK:** Trades **184 → 1** (−99.5%). Net +$8 vs +$174 — not an improvement; sample size is statistically useless.

**Why:** BB reject requires bar 2 **fully outside** the band and bar 1 **closed back inside** on M5, stacked on top of EMA+ADX base signal, inside a 3-hour window. That combination fires almost never.

**Verdict:** **Rejected (v1.03 strict).** Retest on **v1.04** relaxed BB wick-touch logic.

#### EDGE-201 detail — v1.04 full year 2025

| Metric | Value |
|--------|-------|
| Window | **2025 full year** |
| Net | **+$62.70** |
| PF | **2.61** |
| WR | 77.3% (17W / 5L) |
| DD | 12.5% ($26) |
| Trades | **22** |
| Avg win / loss | +$5.98 / -$7.80 |
| Short WR | 71.4% (14 trades) |
| Long WR | 87.5% (8 trades) |
| Avg hold | ~1h 3m |

**E2 criteria:** PF ≥ 1.2 ✓ | WR ≥ 52% ✓ | trades ≥ 30% LOCK ✗ (22 vs ~55+ needed on comparable window)

**vs EDGE-LOCK (Jan–Jun only):** LOCK +$174 / 184 trades / PF 1.23. EDGE-201 full-year net is **lower** on far fewer trades — cherry-picked quality, not scalable volume.

**Pattern:** Entries cluster **Wed–Thu**, hours **14–17** (peak 16), **April** heaviest. BB wick reject still filters ~88%+ of LOCK signals.

**Verdict:** **Partial — quality yes, volume no.** PF 2.61 and 12% DD are strong but 22 trades/year is too thin to adopt. Keep LOCK as baseline; continue **EDGE-204** / **EDGE-202** for higher-count enhancement. Optional: relax BB (drop midline rule) in a future EDGE-201b if 204/202 also under-trade.

#### EDGE-202 detail (LOCK + RSI — v1.03 strict run)

| Metric | Value |
|--------|-------|
| Net | $0.00 |
| Trades | **0** |
| DD | 0% |

**vs EDGE-LOCK:** 184 → **0** trades. RSI ≤35 (buy) / ≥65 (sell) on bar 1 never coincides with the base EMA+ADX signal inside the 15–17 window over Jan–Jun 2025.

**Why:** Base signal fires on EMA slope or flat-EMA price position — typically mid-range RSI. Requiring simultaneous RSI extremes is mutually exclusive with most LOCK entries.

**Verdict:** **Rejected (v1.03 strict).** v1.04 uses RSI ≤48 buy / ≥45 sell to trim overbought longs without zeroing trades.

#### EDGE-202 detail — v1.04 Jan–Jul 2025

| Metric | Value |
|--------|-------|
| Window | **Jan–Jul 2025** |
| Net | **+$272.80** |
| PF | **1.93** |
| WR | 71.9% (69W / 27L) |
| DD | 12.4% ($38) |
| Trades | **96** |
| Avg win / loss | +$8.22 / -$10.90 |
| Short WR | 72.0% (**82** trades) |
| Long WR | 71.4% (14 trades) |
| Avg hold | ~1h 49m |
| Max consec losses | 3 |

**E2 criteria:** PF ≥ 1.2 ✓ | WR ≥ 52% ✓ | trades ≥ 30% LOCK ✓ (96 vs ~55 min; ~52% of LOCK H1 pace)

**vs EDGE-LOCK (Jan–Jun):** Net **+$273 vs +$174** | PF **1.93 vs 1.23** | WR **72% vs 62%** | DD **12% vs 25%** | trades 96 vs 184 (−47%). **Strict improvement** on all quality metrics with acceptable volume.

**vs EDGE-201 (full yr):** EDGE-202 delivers **4× net** on **4× trades** — RSI rotation is the right enhancement layer; BB reject too selective.

**Pattern:** Still 15–18h cluster, Wed peak, Feb/Mar strongest. RSI filter cuts weak longs (82 short / 14 long) while lifting long WR to 71%.

**Verdict:** **PASS — top E2 candidate.** Next: run **EDGE-LOCK Jan–Jul** for same-window confirm, then **EDGE-204**. If 204 doesn't beat 202, promote **EDGE-202** to locked stack v2.

#### EDGE-203 detail — v1.04 Jan–Jul 2025

| Metric | Value |
|--------|-------|
| Net | +$52.50 |
| PF | 2.68 |
| WR | 77.8% (14W / 4L) |
| DD | 12.5% ($26) |
| Trades | **18** |
| Short / Long | 13 / 5 (longs 100% WR) |
| Avg hold | ~1h 3m |

**E2 criteria:** PF ✓ | WR ✓ | volume ✗ (18 ≈ 19% of LOCK H1 pace)

**vs EDGE-202:** Net **+$53 vs +$273** on **18 vs 96** trades. Stacking BB on top of RSI destroys volume without beating 202 on quality-adjusted basis.

**Verdict:** **Rejected.** RSI alone (202) is the right layer; BB combo over-filters. Skip — proceed **EDGE-205**, then promote **EDGE-202** if 205 doesn't beat it.

#### EDGE-204 detail — v1.04 Jan–Jul 2025

| Metric | Value |
|--------|-------|
| Net | +$162.40 |
| PF | 1.23 |
| WR | 62.0% (106W / 65L) |
| DD | 19.2% ($75) |
| Trades | 171 |
| Short WR | 72.4% (87 trades) |
| Long WR | 51.2% (84 trades) |
| Avg win / loss | +$8.21 / -$10.90 |
| Avg hold | ~1h 49m |

**vs EDGE-LOCK (Jan–Jun):** Nearly identical PF (1.23) and WR (62%), similar trade count (171 vs 184), slightly lower net (+$162 vs +$174 on shorter LOCK window). HTF soft align barely moves the needle — longs still weak at 51%.

**vs EDGE-202:** Net **+$162 vs +$273** | PF **1.23 vs 1.93** | WR **62% vs 72%** | DD **19% vs 12%** | long WR **51% vs 71%**. EDGE-202 wins on every quality metric.

**Verdict:** **Rejected vs EDGE-202.** **EDGE-202 → LOCK v2 adopted.**

#### EDGE-205 detail — v1.04 Jan–Jul 2025

| Metric | Value |
|--------|-------|
| Net | $0.00 |
| Trades | **0** |

**Why:** Requires close ≥0.15×ATR away from EMA, but base signal fires on EMA slope/flat proximity — mutually exclusive, same failure mode as v1.03 RSI extremes.

**Verdict:** **Rejected.** E2 phase complete; **EDGE-202** promoted to **`EDGE-LOCK-202_15-17-rsi`**.

#### EDGE-501 detail — R:R flip SL 1.5× / TP 2× ATR (LOCK-202 + E5)

| Window | Net | PF | WR | Trades | DD | Avg win / loss |
|---|---|---|---|---|---|---|
| Jan–Dec 2025 (12 mo) | — | **1.64** | ~55% | ~87+ | ~15% bal | **+$10.88 / −$8.18** |
| Jan–Jul 2025 (screenshot) | **+$203** | 1.64 | 55.2% | 87 | 15.0% / 17.4% eq | +$10.88 / −$8.18 |
| Jan 2025 – Jul 2026 | — | **1.29** | — | — | — | — |

**vs LOCK-202:**

| Window | LOCK-202 PF | EDGE-501 PF | LOCK-202 net | EDGE-501 net |
|---|---|---|---|---|
| Jan–Jul 2025 | 1.93 | 1.64 | +$273 | +$203 |
| Jan 25 – Jul 26 | 1.46 | 1.29 | +$623 | — |

**What improved:** Per-leg economics — avg win now **exceeds** avg loss (E5 partial criterion). Tighter SL (−8.60 max loss vs −10.90 on LOCK). Max consec losses still 3.

**What degraded:** WR **72% → 55%** — wider TP is not reached as often. PF and net **below LOCK-202** on every comparable window. DD slightly higher (15% vs 12%).

**E5 pass check:** avg win ≥ avg loss ✓ | PF ≥ 2.0 ✗ | net ≥ LOCK-202 ✗ | DD ≤ 15% ~ (borderline) | trades ≥ 50% LOCK ✓

**Verdict:** **Not adopted — promising reserve.** Rejected as LOCK replacement (PF/net below LOCK-202; WR 72% → 55%). **Worth keeping:** avg win > avg loss, tighter tails, PF still > 1.0 on tested windows. **Goal for coded E5:** achieve 501-like economics **on top of** LOCK-202’s WR via trailing basket (E504) or partial TP — not a blind R:R swap.

**Status:** `EDGE-LOCK-202` = **baseline** | `EDGE-501` = **economics reference** (preset archived in `Profiles\Tester\`)

#### EDGE-502 detail — basket TP $25 (LOCK-202 + E5)

| Window | Net | PF | WR | Trades | vs LOCK-202 |
|---|---|---|---|---|---|
| Jan–Jul 2025 (~6 mo) | +$273 | 1.93 | 72% | 96 | **Identical** |
| Jan 2025 – Jul 2026 | +$623 | 1.46 | 66% | 324 | **Identical** |
| Jan 2022 – Jul 2026 | −$50 | 0.99 | 57% | 1061 | PF 0.99 vs 0.95 ($200 longest); $500 deposit — ignore DD |

**Conclusion:** Lowering basket TP **$50 → $25** changed **nothing** — metrics match LOCK-202 on overlapping windows. Basket TP still not driving exits (all closes remain per-leg SL/TP).

**Verdict:** **Rejected — preset-only exit tweak insufficient.** Next: **implement E504** (trailing basket) or **E403/E405** (tail cap) in code; ~~optional try **$12–15**~~ **502-15 confirmed = LOCK-202** (skip 502-12/20 unless diagnostics check wanted).

#### EDGE-502-15 detail — basket TP $15 (LOCK-202 + E5)

| Metric | Value |
|---|---|
| Window | **Jan–Dec 2025** (full year) |
| Net | **+$272.80** |
| PF | **1.93** |
| WR | **71.88%** (69W / 27L) |
| Trades | **96** |
| DD | **12.44%** equity ($37.50) |
| Avg win / loss | +$8.22 / −$10.90 |
| Max consec losses | 3 |

**vs LOCK-202 (Jan–Jul 2025):** Net +$273 | PF 1.93 | WR 72% | 96 trades | DD 12% — **byte-for-byte match.**

**Conclusion:** Basket TP **$15** changes nothing. Per-leg SL/TP still close every basket before floating P/L reaches $15. Same failure mode as $25.

**Verdict:** **Rejected** — skip remaining 502 money presets (12/20); basket TP path dead without code.

#### EDGE-504 detail — trailing basket (production + E5, v1.05)

| Metric | EDGE-504 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$388.90** | **+$623** |
| PF | **1.30** | **1.46** |
| WR | **63.1%** | **66.0%** |
| Trades | **360** | **324** |
| DD (eq) | **23.4%** | **23.0%** |
| Avg win / loss | +$7.45 / −$9.80 | +$9.30 / −$12.42 |
| Max consec losses | **6** (−$75.60) | ~3–4 typical |
| Avg hold | **~54 min** | ~1h 45m |

**What changed:** Trail **is firing** (more trades, shorter holds). Avg loss improved (−$9.80 vs −$12.42) but avg win fell more (+$7.45 vs +$9.30) — net expectancy down.

**Verdict:** **Rejected** — cuts winners early; extended PF **1.30 vs 1.46**, net **−$234** vs production. Continue with **505 → 507**.

#### EDGE-505 detail — MR exit at EMA (production + E5, v1.05)

| Metric | EDGE-505 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **−$180.20** | **+$623** |
| PF | **0.08** | **1.46** |
| WR | **13.4%** | **66.0%** |
| Trades | **343** | **324** |
| DD (eq) | **90.1%** | **23.0%** |
| Avg win / loss | +$0.33 / −$0.66 | +$9.30 / −$12.42 |
| Max consec losses | **73** (−$45.60) | ~3–4 typical |
| Avg hold | **~15 sec** | ~1h 45m |

**Root cause:** Entries fire **near EMA** (rotation core). MR exit closes basket on **immediate EMA touch** — baskets exit before per-leg SL/TP can work. Micro P/L (+$0.33 / −$0.66) = spread + churn death spiral.

**Verdict:** **Hard reject — do not iterate preset.** MR-at-EMA exit is **antagonistic** to LOCK entry logic. Skip redesign unless exit requires profit filter + closed-bar confirm (future R&D only). Run **506 → 507**.

#### EDGE-506 detail — adaptive basket TP (production + E5, v1.05)

| Metric | EDGE-506 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$222.90** | **+$623** |
| PF | **1.28** | **1.46** |
| WR | **80.0%** | **66.0%** |
| Trades | **385** | **324** |
| DD (eq) | **46.9%** | **23.0%** |
| Avg win / loss | +$3.29 / −$10.28 | +$9.30 / −$12.42 |
| Max consec losses | 4 (−$67.70) | ~3–4 typical |
| Avg hold | **~21 min** | ~1h 45m |

**What changed:** Adaptive basket TP **fires** (high WR, short holds). Targets are **too low** — many small +$3 wins vs full −$10 losses. WR trap: **80% WR** but net **−$400** vs production.

**Verdict:** **Rejected** — DD doubled (47% vs 23%), PF **1.28 vs 1.46**. Basket exit path not viable at 0.5×ATR/level scale. Run **507** last.

#### EDGE-507 detail — time stop 90 min (production + E5, v1.05)

| Metric | EDGE-507 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$243.70** | **+$623** |
| PF | **1.20** | **1.46** |
| WR | **57.1%** | **66.0%** |
| Trades | **375** | **324** |
| DD (eq) | **62.0%** | **23.0%** |
| Avg win / loss | +$6.84 / −$7.57 | +$9.30 / −$12.42 |
| Max consec losses | **10** (−$98.30) | ~3–4 typical |
| Avg / max hold | **~33 min / 1h 30m** | ~1h 45m / longer |

**What changed:** 90 min cap **fires** (max hold = 1:30). Cuts underwater baskets early but also interrupts recoveries. WR and net down; **DD 62%** worst of E5 coded tests.

**Verdict:** **Rejected.** Per-leg economics slightly tighter (+$6.84 / −$7.57) but headline metrics collapse vs production.

#### E5 coded phase summary (504–507, Jan 25–Jul 26 ext)

| ID | PF | Net | DD | Verdict |
|---|---|---|---|---|
| production | **1.46** | **+$623** | **23%** | **baseline** |
| 504 trail | 1.30 | +$389 | 23% | Reject — clips winners |
| 505 MR EMA | 0.08 | −$180 | 90% | Hard reject — antagonistic |
| 506 adaptive TP | 1.28 | +$223 | 47% | Reject — WR trap |
| 507 time stop | 1.20 | +$244 | 62% | Reject — DD blowout |

**E5 conclusion:** **No coded exit promotes to production.** Keep `production` locked. **Next phase: E4** (EDGE-403 basket DD cap, EDGE-405 MAE exit) for tail control.

#### EDGE-402 detail — adaptive depth ADX≥25 → max 3 (production + E4, v1.06)

| Metric | EDGE-402 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$623.30** | **+$623** |
| PF | **1.46** | **1.46** |
| WR | **66.1%** | **66.0%** |
| Trades | **324** | **324** |
| DD (eq) | **23.0%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.42 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$75.60) | 6 (−$75.60) |

**Conclusion:** **Byte-for-byte match** with production — adaptive cap never engaged in practice. ADX ≥ 25 during 15–17 entries is rare (stack already filters ADX > 20 for signal, but rotation pocket stays below 25 at add-time).

**Verdict:** **Rejected — no effect.** Skip ADX threshold retune unless diagnostics show cap events. Continue **403 / 405**.

#### EDGE-404 detail — scaled lots ×0.85^level (production + E4, v1.06)

| Metric | EDGE-404 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$564.84** | **+$623** |
| PF | **1.43** | **1.46** |
| WR | **66.1%** | **66.0%** |
| Trades | **324** | **324** |
| DD (eq) | **23.7%** | **23.0%** |
| Avg win / loss | +$8.77 / −$11.93 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$70.66) | 6 (−$75.60) |

**What changed:** Deeper grid adds use smaller lots (0.85^level) — avg loss slightly tighter (−$11.93 vs −$12.42) but avg win also down (+$8.77 vs +$9.30). Same trade count; net **−$58** (−9%) vs production.

**Verdict:** **Rejected** — tail slightly smaller on paper but **net and PF below production**. Not worth the complexity.

#### EDGE-405 detail — MAE exit 4×ATR from anchor (production + E4, v1.06)

| Metric | EDGE-405 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$4.80** | **+$623** |
| PF | **1.00** | **1.46** |
| WR | **56.7%** | **66.0%** |
| Trades | **379** | **324** |
| DD (eq) | **79.0%** | **23.0%** |
| Avg win / loss | +$6.62 / −$8.65 | +$9.30 / −$12.42 |
| Max consec losses | 8 (−$51.50) | 6 (−$75.60) |
| Avg hold | **~43 min** | ~1h 45m |

**What changed:** MAE exit **fires often** — closes baskets when price moves 4×ATR against anchor before per-leg recovery. More trades, shorter holds, WR down 9 pts, **DD 79%**, net effectively **zero**.

**Verdict:** **Hard reject** — 4×ATR from anchor is too tight for grid MR; wipes +$623 edge. Do not retune without anchor/level-aware logic.

#### EDGE-403 detail — basket DD cap 2% equity (production + E4, v1.06)

| Metric | EDGE-403 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$343.50** | **+$623** |
| PF | **1.30** | **1.46** |
| WR | **63.4%** | **66.0%** |
| Trades | **254** | **324** |
| DD (eq) | **28.4%** | **23.0%** |
| Avg win / loss | +$9.31 / −$12.42 | +$9.30 / −$12.42 |
| Max consec losses | **5** (−$63.30) | 6 (−$75.60) |

**What changed:** 2% basket DD cap **fires** — blocks grid adds (−70 trades). Max consec losses improve (5 vs 6) but **DD worse** (28% vs 23%) and net **−$279** (−45%) vs production. Shallow stacks miss recoveries that full grid captures.

**Verdict:** **Rejected** — cap reduces depth but doesn't improve risk-adjusted outcome on extended window.

#### E4 coded phase summary (403–405–402–404, Jan 25–Jul 26 ext)

| ID | PF | Net | DD | Trades | Verdict |
|---|---|---|---|---|---|
| **production** | **1.46** | **+$623** | **23%** | **324** | **baseline** |
| 403 DD cap | 1.30 | +$344 | 28% | 254 | Reject — fewer trades, worse DD |
| 405 MAE exit | 1.00 | +$5 | 79% | 379 | Hard reject |
| 402 adaptive depth | 1.46 | +$623 | 23% | 324 | No effect |
| 404 scaled lots | 1.43 | +$565 | 24% | 324 | Reject — net −$58 |

**E4 conclusion:** **No grid/risk containment promotes to production.** Deep grid is part of the edge; blunt caps hurt net without fixing longest-window tail. **Next: E3** regime gates (302, 306 seasonal) or longest-window stress retest.

#### EDGE-301 detail — ADX slope block (production + E3, v1.07)

| Metric | EDGE-301 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$595.30** | **+$623** |
| PF | **1.44** | **1.46** |
| WR | **65.7%** | **66.0%** |
| Trades | **321** | **324** |
| DD (eq) | **28.1%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.42 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$75.60) | 6 (−$75.60) |

**What changed:** ADX rising-3-bar gate **fires lightly** (−3 trades). Blocks few trend-building entries but **DD worse** (28% vs 23%) with no net gain.

**Verdict:** **Rejected** — marginal −$28 net, PF 1.44 vs 1.46. Continue **306 → 302 → 303 → 304 → 305**.

#### EDGE-302 detail — ATR vol pause 1.8× (production + E3, v1.07)

| Metric | EDGE-302 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$623.30** | **+$623** |
| PF | **1.46** | **1.46** |
| WR | **66.1%** | **66.0%** |
| Trades | **324** | **324** |
| DD (eq) | **23.0%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.42 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$75.60) | 6 (−$75.60) |

**Conclusion:** **Byte-for-byte match** with production. ATR > 1.8× 20-bar avg rarely/never true at 15–17 entry time in this pocket.

**Verdict:** **Rejected — no effect.** Continue **306 → 303 → 304 → 305**.

#### EDGE-303 detail — ATR 80th percentile cap (production + E3, v1.07)

| Metric | EDGE-303 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$307.00** | **+$623** |
| PF | **1.27** | **1.46** |
| WR | **62.9%** | **66.0%** |
| Trades | **248** | **324** |
| DD (eq) | **35.6%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.43 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$74.20) | 6 (−$75.60) |

**What changed:** 80th-percentile ATR gate **fires** (−76 trades). Filters ~24% of entries but **DD worse** (36% vs 23%) and net **−$316** (−51%) vs production.

**Verdict:** **Rejected** — blocking high-ATR days removes profitable pocket trades, not just tails. Continue **306 → 304 → 305**.

#### EDGE-304 detail — chop-only 3+ EMA crosses (production + E3, v1.07)

| Metric | EDGE-304 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$250.30** | **+$623** |
| PF | **1.36** | **1.46** |
| WR | **64.3%** | **66.0%** |
| Trades | **143** (4 long / 139 short) | **324** |
| DD (eq) | **28.8%** | **23.0%** |
| Avg win / loss | +$10.19 / −$13.47 | +$9.30 / −$12.42 |
| Max consec losses | 5 (−$67.70) | 6 (−$75.60) |

**What changed:** Chop gate **over-filters** — trades cut **56%** (324→143). Long side nearly eliminated (**4 longs** vs 63). Net **−$373** (−60%) vs production.

**Verdict:** **Rejected** — 3+ EMA crosses in 20 bars is too strict for this pocket; destroys long rotation entries. Continue **306**.

#### EDGE-305 detail — regime combo 301 + 302 (production + E3, v1.07)

| Metric | EDGE-305 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$595.30** | **+$623** |
| PF | **1.44** | **1.46** |
| WR | **65.7%** | **66.0%** |
| Trades | **321** (62 long / 259 short) | **324** |
| DD (eq) | **28.1%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.42 | +$9.30 / −$12.42 |
| Max consec losses | 6 (−$75.60) | 6 (−$75.60) |

**What changed:** Combo is **byte-for-byte identical to EDGE-301**. ATR pause (302) never fires in 15–17; only ADX slope (−3 trades) is active. No additive benefit from stacking gates.

**Verdict:** **Rejected** — same as 301: marginal −$28 net, PF 1.44 vs 1.46, DD worse.

#### EDGE-306 detail — seasonal skip Jun–Sep (production + E3, v1.07)

| Metric | EDGE-306 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$359.40** | **+$623** |
| PF | **1.34** | **1.46** |
| WR | **64.2%** | **66.0%** |
| Trades | **240** (39 long / 201 short) | **324** |
| DD (eq) | **41.3%** | **23.0%** |
| Avg win / loss | +$9.28 / −$12.44 | +$9.30 / −$12.42 |
| Max consec losses | 5 (−$63.20) | 6 (−$75.60) |

**What changed:** Jun–Sep gate **fires** (−84 trades, −26%). Monthly charts confirm zero entries Jun–Sep. Despite targeting H2 bleed, net **−$264** (−42%) and **DD nearly doubles** (41% vs 23%) — summer months were net-positive in this pocket, not the main tail source.

**Verdict:** **Hard reject** — highest-priority E3 candidate failed on both net and DD. **E3 complete; production unchanged.**

#### EDGE-601 detail — prior day H/L boundary (production + E6, v1.08)

| Metric | EDGE-601 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$160.20** | **+$623** |
| PF | **1.35** | **1.46** |
| WR | **60.5%** | **66.0%** |
| Trades | **38** (5 long / 33 short) | **324** |
| DD (eq) | **49.4%** | **23.0%** |
| Avg win / loss | +$26.95 / −$30.65 | +$9.30 / −$12.42 |
| Max consec losses | 4 (−$122.40) | 6 (−$75.60) |

**What changed:** PD H/L gate **over-filters** — trades cut **88%** (324→38). Long side nearly eliminated (**5 longs** vs 63). Net **−$463** (−74%), DD **more than doubles** (49% vs 23%). Requiring price at prior-day extremes is too rare in the 15–17 rotation pocket.

**Verdict:** **Hard reject** — fails pass rule on net, PF, trades (<30%), and DD.

#### EDGE-602 detail — session H/L boundary (production + E6, v1.08)

| Metric | EDGE-602 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$154.10** | **+$623** |
| PF | **1.65** | **1.46** |
| WR | **68.8%** | **66.0%** |
| Trades | **32** (12 long / 20 short) | **324** |
| DD (eq) | **45.8%** | **23.0%** |
| Avg win / loss | +$17.78 / −$23.70 | +$9.30 / −$12.42 |
| Max consec losses | 4 (−$95.00) | 6 (−$75.60) |

**What changed:** Session H/L gate **over-filters** — trades cut **90%** (324→32). PF/WR look better on the tiny sample but net **−$469** (−75%) and DD **doubles** (46% vs 23%). Requiring price at session extremes at 15–17 entry time is too rare; kills volume without fixing tail risk.

**Verdict:** **Hard reject** — headline PF misleading on 32 trades; fails net, trades (<97), and DD.

#### EDGE-603 detail — liquidity sweep + rejection (production + E6, v1.08)

| Metric | EDGE-603 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$80.40** | **+$623** |
| PF | **4.50** | **1.46** |
| WR | **85.7%** | **66.0%** |
| Trades | **7** (0 long / 7 short) | **324** |
| DD (eq) | **15.9%** | **23.0%** |
| Avg win / loss | +$17.23 / −$23.00 | +$9.30 / −$12.42 |
| Max consec losses | 1 (−$23.00) | 6 (−$75.60) |

**What changed:** Sweep gate **nearly eliminates trading** — **7 trades** in 19 months (−98%). PF 4.50 / WR 86% are **statistically meaningless** on this sample. Long side **zeroed** (0 vs 63). Net **−$543** (−87%). Lower DD is an artifact of not trading, not tail control.

**Verdict:** **Hard reject** — most aggressive over-filter in E6 so far.

#### EDGE-604 detail — range midpoint grid anchor (production + E6, v1.08)

| Metric | EDGE-604 | production (baseline) |
|---|---|---|
| Window | **Jan 2025 – Jul 2026** | same |
| Net | **+$521.60** | **+$623** |
| PF | **1.31** | **1.46** |
| WR | **63.7%** | **66.0%** |
| Trades | **369** (96 long / 273 short) | **324** |
| DD (eq) | **41.6%** | **23.0%** |
| Avg win / loss | +$9.30 / −$12.41 | +$9.30 / −$12.42 |
| Max consec losses | 9 (−$113.00) | 6 (−$75.60) |

**What changed:** Session-mid anchor **does not block entries** (+14% trades). Per-leg economics unchanged but grid geometry misaligned — first fill at market, levels radiate from session mid → **deeper grid adds**, longer holds, **DD nearly doubles** (42% vs 23%). Net **−$101** (−16%), max consec losses **9** vs 6.

**Verdict:** **Rejected** — only E6 test with full trade volume; geometry change hurts tail without lifting net. **E6 complete; production unchanged.**

---

## Summary

**Discovery (E0–E2) is complete.** Locked stack **LOCK-202** (15–17 + RSI rotation) is profitable in **favourable regime** (PF 1.46 over 19 months, +$623) but **fails on longest history** (PF 0.95, −$192, 98% DD) without tail control.

**Regime lessons:** Jan–May strong; H2 weaker; fat losses to −$66; short WR degrades over time.

**Enhancement goal:** Lift longest-window PF above 1.0, cap tail losses, fix exit economics — while keeping Jan–Jun edge.

**Dual track:** **LOCK-202** remains the sole live/enhancement baseline. **EDGE-501** is documented as a **promising reserve** — better per-trade economics (avg win > avg loss) even though headline PF trails LOCK today. Long-term target: LOCK’s WR + 501’s payoff shape via coded exits, not preset R:R flip.

**Enhancement status (E3–E6):** **All enhancement phases complete — no promotion.** Production **LOCK-202** remains locked with E3/E4/E5/E6 **off**.

**Next action:** **E8 AI** — see [`ai_enhance.md`](ai_enhance.md). Start **AI-800** infra + **AI-801** diagnostics export. **E7** walk-forward runs in parallel on LOCK-202 baseline.
