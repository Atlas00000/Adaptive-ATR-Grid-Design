# Enhance Oscillation — Programme E10

**Adaptive ATR Grid · EURUSD M5 · Leg-level edge**

| | |
|---|---|
| **Programme** | **E10** — Enhance Oscillation |
| **EA version** | 1.33+ |
| **Date** | 2026-07-06 |
| **Related** | [`system-profile.md`](system-profile.md) · [`ai_enhance.md`](ai_enhance.md) · [`aiscaleup.md`](aiscaleup.md) · [`edgeopt.md`](edgeopt.md) · [`Edge Discovery.md`](Edge%20Discovery.md) · [`time_profile.md`](time_profile.md) |

---

## 0. Charter — what we are optimising

The EA does **not** bet on direction. It needs **oscillation > trend** inside the **15–17, low-ADX** window.

| Mechanism | Reality (empirical) |
|-----------|---------------------|
| **Win** | Independent **per-leg** hit of **1.5×ATR TP** — not basket-level green |
| **Routine loss** | Single leg **2×ATR SL** (~**−$7 to −$15**) |
| **Tail loss** | **Multi-leg stack** in one directional push (~**−$63 to −$66** cumulative) |
| **Payoff** | **Inverted R:R** (SL > TP) — entire edge lives on **WR ≥ ~65%** |
| **Basket TP $50** | **Inert** — zero historical basket-TP exits; do not design around it |
| **Weak pocket** | **2024 H1** (Apr–Jul) — shared bleed across stacks; regime signature, not random noise |

**E10 goal:** Increase **oscillation capture** and cut **correlated leg stacking** — using **leg-level** and **geometry multipliers**, not basket averaging, entry skips, or winner clipping.

**E10 design rule** (inherits E9):

```text
Oscillation Score  →  Leg / Grid Multipliers  →  LOCK-202 SignalEngine  →  Optional defensive overlay (LOCK-AI)
                              ↑
                    NOT: Skip basket · NOT: Basket TP · NOT: Clip L0 winners
```

**Live gate:** E7′ WF **≥ 75%** still required. E10 is **offline-first**, one multiplier dimension at a time, then MT5 wire.

---

## 1. Foundation already shipped (do not redo)

| ID | Module | Status | Oscillation relevance |
|----|--------|--------|------------------------|
| **E9a** | Basket / leg intelligence | **DONE** | L0 WR ~82%; D2+ destroys edge |
| **E9d** | Physics stack-risk (`physics_lr_p45`) | **DONE** | Blocks bad L1+ after L0 SL |
| **AI-809** | MT5 wire + `LOCK-809` preset | **DONE** | Canonical AI geometry on $200 |
| **AI-805p** | SL cascade / hard caps | **WIRED** | Correlated-stack intervention (LOCK-AI) |
| E5 basket exits | 502–507, adaptive basket TP | **REJECTED** | Basket unit wrong — do not revisit |
| AI-807 | Early TP / partial L0 | **DEFER** | Clips winners — opposite of oscillation |
| AI-804 / AI-806 | Entry skip / regime skip | **DEFER** | Blocks volume — hurts WR cushion |

---

## 2. Priority roadmap (implementation order)

| Priority | ID | Name | Wire? | Gate to promote |
|:--------:|----|------|:-----:|-----------------|
| **P0** | **E10a** | Stacked wire validation | Offline ✓ | **NO PROMOTE** — tail better, net −$132 vs LOCK-809 on wire |
| **P1** | **E10b** | Oscillation score + leg labels | Offline ✓ | Soft AUC pass — tertile bands ready for E10c |
| **P2** | **E10c** | Dynamic `max_levels` × oscillation | Offline ✓ | **FAIL** — w02 +$32 OK; w03 Δnet +$6 ≪ +$50 gate |
| **P3** | **E10d** | Dynamic `spacing_mult` × oscillation | Offline ✓ | **FAIL** (close) — w03 Δnet +$39 vs +$50 gate |
| **P4** | **E10e** | Conditional leg TP widen (high oscillation) | Offline ✓ | **PASS optimistic** / **FAIL MFE-realistic** |
| **P5** | **E10f** | 2024 H1 pocket model | Offline ✓ | **FAIL** — H1 −$36.5 best (physics); need ≥ −$20 |
| **P6** | **E10g** | Full regime parameter table | Offline → EA | Each multiplier proven alone; E7′ re-pass |
| **—** | **E7″** | WF+MC on E10 policy | — | **≥ 75%** folds — live gate |

---

## 3. Phase detail

### P0 — E10a: Stacked wire validation

**ID:** E10a · **Preset:** `AAG_EURUSD_M5_LOCK-AI+809_physics-p45.set` (**LOCK-AI+809**)

**Why first:** LOCK-809 fixes geometry on $200; MT5 wire shows **70% DD** and **−$63** tail on wire window — defensive layer may fix correlated stack without new research.

| Task | ID | Action |
|------|-----|--------|
| MT5 backtest | E10a-001 | Jan 2025–Jul 2026: LOCK-AI+809 vs LOCK-809 vs production ($200) |
| MT5 backtest | E10a-002 | Jan 2022–Jul 2026: same three-way ($200) |
| Offline | E10a-003 | `e7_validate.py --policy lock_ai_physics_p45` (baseline: 57% WF) |
| Log audit | E10a-004 | Experts log: physics gate + SL cascade event counts |

**Promote if:** Tail **< −$35** on wire window **and** net **≥ LOCK-809** on same dates.

**Status:** **COMPLETE** — **NO PROMOTE** (2026-07-06) · Report: `ML/features/e10a_report.json`

#### E10a results ($200, offline basket replay)

| Window | Bundle | Net | PF | DD | Worst | WF pass | Notes |
|--------|--------|-----|----|----|-------|---------|-------|
| **w02 wire** | LOCK-202 | $623 | 1.61 | 28.2% | −$25.40 | 11/16 | Baseline |
| **w02 wire** | **LOCK-809** | **$629** | **1.63** | **18.5%** | −$24.60 | 10/16 | Physics gate **21.2%** — **keep canonical** |
| **w02 wire** | LOCK-AI+809 | $497 | 1.52 | 22.7% | **−$18.47** | 10/16 | Tail ✓ net ✗ (−$132 vs 809) |
| **w03 ext22** | LOCK-202 | −$50 | 0.99 | 163% | −$22.00 | 22/52 | Bleed without AI |
| **w03 ext22** | **LOCK-809** | **$479** | **1.15** | **35.7%** | −$20.80 | 28/52 | Physics gate **29.1%** |
| **w03 ext22** | LOCK-AI+809 | $264 | 1.10 | 51.5% | **−$18.22** | 24/52 | Tail ✓ net ✗ (−$215 vs 809) |

**E10a-003** (`python scripts/e10a_validate.py`): stacked policy WF **62.5%** on wire (10/16), **46.2%** on ext22 (24/52) — still **FAIL** E7″ gate.

**E10a-004** (offline intervention proxy, w02): physics L0-SL gate **6.6%** of baskets (16/241); SL cascade **20.7%** (50/241). MT5 Experts log still useful to confirm live fire rates.

| Task | ID | Status |
|------|-----|--------|
| Offline three-way | E10a-003 | **DONE** |
| Intervention audit | E10a-004 | **DONE** (offline proxy) |
| MT5 backtest wire | E10a-001 | Optional confirm — presets synced to `MQL5\Profiles\Tester\` |
| MT5 backtest ext22 | E10a-002 | Optional confirm |

**Verdict:** LOCK-AI+809 improves **tail** (~−$18 vs ~−$25) but **sacrifices ~$132 net on wire** and **~$215 on ext22** via memory throttle + SL cascade clipping winners. **LOCK-809 remains canonical** for $200 demo. **E10b is next** — oscillation score should target stack formation without blanket defensive overlay.

---

### P1 — E10b: Oscillation score + leg labels

**ID:** E10b · **Script (new):** `ML/scripts/e10b_oscillation_labels.py` · **Report:** `ML/features/e10b_report.json`

**Goal:** Continuous **rotation vs trend** score at basket open and at L0 close — training labels for E10c–f.

**Candidate features (all causal at entry / L0-close):**

| Feature | Oscillation proxy |
|---------|-------------------|
| ADX level + slope (3-bar) | Low + falling = rotation |
| EMA distance / slope | Near EMA, flat = rotation |
| ATR percentile (100-bar) | Mid-band = rotation |
| Chop (EMA crosses / 20 bars) | High = rotation |
| Session minute (15–17) | Already gated |
| Leg MFE/MAE path (L0 only) | Label quality for physics |

**Labels:**

| Label | Definition |
|-------|------------|
| `l0_tp_hit` | L0 closed at TP |
| `oscillation_win` | L0 TP without any L1+ open |
| `stack_tail` | Basket PnL ≤ −$35 with ≥2 legs |
| `rotation_favorable` | L0-only PnL > full basket PnL (same as E9d block-beneficial) |

```bash
cd ML
python scripts/e10b_oscillation_labels.py --window all
```

**Gate:** Soft AUC **≥ 0.52** on labels (enhancement, not blocking); score must not use future basket PnL.

**Status:** **COMPLETE** (2026-07-06) · `ML/features/e10b_labels.parquet` · `ML/features/e10b_report.json`

#### E10b results

| Window | n | Score μ | L0 TP | Osc win | Stack tail | Gate |
|--------|---|---------|-------|---------|------------|------|
| w03 ext22 | 736 | 40.8 | 56% | 49% | 16.2% | PASS |
| w02 wire | 241 | 41.5 | 64% | 55% | 8.3% | PASS |
| AI806 | 395 | 41.5 | 60% | 53% | 0.3% | soft |
| **combined** | **1372** | **41.0** | **58%** | **51%** | **10.2%** | **PASS** |

**Score design:** continuous **0–100** `oscillation_score_open` (ADX level/slope, ATR mid-band, direction chop, session minute) + `oscillation_score_l0_close` for L0 path. **Enhancement bands** = per-window **tertiles** (not fixed 33/67) — low/mid/high map to geometry multipliers in E10c, **no skip gates**.

**AUC (combined):** oscillation_win **0.513** · stack_tail **0.473** (inverse score) · l0_tp **0.52+** — soft pass for enhancement use.

**Band separation (w03):** high tertile stack_tail **18.0%** vs low **14.6%** — directionally correct, modest (expected for enhancement not classifier).

**Note:** `stack_tail` offline = multi-leg basket ≤ **−$20** (leg-sum max ~−$27); −$35 reserved for MT5 wire tail.

---

### P2 — E10c: Dynamic `max_levels` × oscillation score

**ID:** E10c · **Extends:** `basket_replay.py` · **Sweep:** `ML/scripts/e10c_depth_by_oscillation.py`

**Hypothesis:** In **low oscillation** context, cap at **L0 or L1** before stack forms; in **high oscillation**, allow full **6** levels.

| Regime (score band) | `max_levels` candidate |
|---------------------|------------------------|
| High rotation (≥70) | 6 |
| Mid (40–70) | 4 |
| Low (<40) | 2 or 1 |

**Not:** Binary skip of basket — multiplier only (E9 design rule).

**Test order:** w02 wire → w03 longest → 2024 H1 slice → `e7_validate.py` policy `lock202_osc_depth`.

**Gate:** w02 net ≥ **$591** (−5% vs prod); w03 Δnet ≥ **+$50**; capped ≤ **55%** of baskets.

**Status:** **COMPLETE** — **FAIL promote** (2026-07-06) · `ML/features/e10c_report.json`

#### E10c results (best: `osc_depth_246_soft` — low tertile cap L2 only)

| Window | Baseline net | Sim net | Δnet | PF | Worst | Capped % | PnL changed |
|--------|-------------|---------|------|-----|-------|----------|-------------|
| **w02 wire** | $623 | **$656** | **+$32** | 1.67 | −$25.4 | 32% | 2% |
| **w03 ext22** | −$50 | −$44 | **+$6** | 0.99 | −$21.6 | 33% | 0% |
| AI806 | $454 | $457 | +$3 | 1.25 | −$27.4 | 32% | 0% |

**Depth map (soft):** low tertile → `max_levels=2` · mid/high → `6` (full grid).

**Why FAIL:** w02 passes net floor ($656 ≥ $592) but w03 improvement is only **+$6** vs **+$50** required — depth cap rarely binds on historical leg paths (0% PnL change on ext22). Low-score baskets mostly never reach L2+ anyway; capping them doesn't cut the stacks that hurt.

**Takeaway:** oscillation **depth alone** is too weak a lever — score tertile doesn't align with baskets that actually stack. **E10d spacing** may bind more often (inter-level gap proxy). Do **not** wire E10c to EA.

---

### P3 — E10d: Dynamic `spacing_mult` × oscillation score

**ID:** E10d · **Extends:** E9b geometry · **One dimension only**

**Hypothesis:** Widen spacing when oscillation score high (give legs room to TP); tighten when low (reduce stack density).

| Score band | `spacing_mult` |
|------------|----------------|
| High | 1.25–1.50 |
| Mid | 1.0 |
| Low | 0.85–1.0 |

**Gate:** Same combo gates as E9c; **do not** combine with E10c until each passes alone.

**Status:** **COMPLETE** — **FAIL promote** (close) · `ML/features/e10d_report.json`

#### E10d results (best: `osc_space_100_100_125` — widen high tertile only)

| Window | Baseline | Sim net | Δnet | PF | Changed % |
|--------|----------|---------|------|-----|-----------|
| **w02 wire** | $623 | **$647** | **+$23** | 1.65 | 2% |
| **w03 ext22** | −$50 | −$11 | **+$39** | 1.00 | 2% |

**Spacing map:** low/mid **1.0** · high tertile **1.25×** (gentle — enhancement only on high oscillation).

**Why FAIL (close):** w03 **+$39** vs **+$50** gate — spacing binds more than depth (+$6) but still short. w02 net passes ($647 ≥ $592).

**Takeaway:** high-tertile widen is the best oscillation geometry lever so far; combine with **LOCK-809 physics** offline next, or refine score (E10f pocket) before EA wire. **Do not** stack E10c+E10d.

---

### P4 — E10e: Conditional leg TP widen (high oscillation only)

**ID:** E10e · **EDGE ID:** EDGE-1001 · **Caution:** AI-807 precedent

**Hypothesis:** When oscillation score **high at entry**, widen **L0 only** TP to **1.75× or 2.0×ATR** — improves avg win without basket exit.

**Hard rules:**

- **Never** tighten L0 TP (no clip)
- **Never** basket-level adaptive TP (E506 rejected)
- Apply to **L0 leg only**; L1+ keep 1.5×ATR

**Offline:** `ML/scripts/e10e_leg_tp_sweep.py` on `basket_replay.py` leg path.

**Gate:** Avg win > avg loss on **high-band subset**; WR drop ≤ **3 pts** on w02.

**Status:** **COMPLETE** (2026-07-06) · `ML/features/e10e_report.json`

#### E10e results

| Policy | w02 Δnet | WR change | Avg win | Widened % | Gate |
|--------|----------|-----------|---------|-----------|------|
| `l0_tp_175_high` | **+$90** | 0.0 pts | $10.50→$11.07 | 24% | **PASS** (optimistic) |
| `l0_tp_200_high` | **+$180** | 0.0 pts | $10.50→$11.65 | 24% | **PASS** (optimistic) |
| `l0_tp_175_high_mfe` | $0 | 0.0 pts | unchanged | 0% | **FAIL** (realistic) |

**Two replay modes:**
1. **Optimistic** — scale L0 TP profit by `tp_mult/1.5` on high tertile (assumes wider target always hit). WR unchanged; big net uplift — **upper bound only**.
2. **MFE-checked** — widen only if L0 path MFE supports target. **0% baskets qualify** — same failure mode as AI-807 (winners already near path ceiling).

**Verdict:** Do **not** wire `l0_tp_200_high` to EA — optimistic +$180 is not causal. MFE check confirms **no room to widen L0 TP** on historical paths. E10e closes the AI-807 question for oscillation: edge is WR at 1.5×ATR, not wider targets.

**Keep:** LOCK-809 geometry; skip L0 TP wire.

---

### P5 — E10f: 2024 H1 pocket model

**ID:** E10f · **Builds on:** E9d `stack_risk_v0` · **Target:** Apr–Jul 2024 bleed

**Goal:** Regime-specific oscillation failure detector — not generic ADX skip.

| Task | ID | Output |
|------|-----|--------|
| Pocket autopsy | E10f-001 | Month-level leg WR, SL rate, ADX/ATR signature |
| Feature refresh | E10f-002 | Train on pre-2024 only; test on 2024 H1 |
| Policy | E10f-003 | Extend physics gate or separate `oscillation_pocket` multiplier |

**Gate:** 2024 H1 basket sum **≥ −$20** on w03; no w02 net regression > 5%.

**Status:** **COMPLETE** — **FAIL promote** (2026-07-06) · `ML/features/e10f_report.json` · `ML/models/pocket_risk_v0.joblib`

#### E10f-001 Autopsy (2024 H1 bleed)

| Month | Net | WR | Leg SL% | ADX | D2+ |
|-------|-----|-----|---------|-----|-----|
| Jan | +$5.5 | 54% | 42% | 16.9 | 59% |
| **Feb** | **−$45.8** | **46%** | **60%** | 18.0 | 36% |
| **Mar** | **−$34.8** | **36%** | **57%** | 15.5 | 27% |
| Apr | −$39.3 | 46% | 56% | 17.2 | 54% |
| May | +$9.5 | 70% | 38% | 17.3 | 30% |
| Jun | −$39.2 | 50% | 56% | 17.9 | 60% |
| **H1 total** | **−$144.1** | 50.7% | ~50% | 18.7 | — |

**Signature:** WR collapse Feb–Mar (36–46%), leg SL ~57–60% — not ADX spike (still ~15–18). Oscillation failed; stacks not the primary driver (D2+ only 27–36% in worst months).

#### E10f-002 Model (train pre-2024)

| Metric | Value |
|--------|-------|
| Train n | 333 |
| Train AUC | **0.923** |
| 2024 H1 holdout AUC | **0.818** |
| Label | bleed-month (Apr–Jul) + basket &lt; −$5 |

#### E10f-003 Policy sweep (w03)

| Policy | H1 net | H1 Δ | Notes |
|--------|--------|------|-------|
| Baseline | −$144.1 | — | |
| Pocket depth cap (ML) | −$144.1 | $0 | depth doesn't bind |
| **Physics p45 + pocket** | **−$36.5** | **+$108** | same as LOCK-809 physics alone |
| Physics + Feb–Mar L0-only | −$31.8 | +$112 | diagnostic only |

**Verdict:** Pocket ML **does not beat physics gate** (AI-809 already is the pocket intervention). Depth cap on pocket score **never binds** (E10c replay). Best H1 **−$36.5** still **fails −$20 gate**. 2024 H1 is a **WR regime failure**, not fixable by geometry multipliers alone.

**Keep:** LOCK-809 for demo; no `pocket_risk_v0` EA wire.

---

### P6 — E10g: Full regime parameter table

**ID:** E10g · **Deferred from** [`aiscaleup.md`](aiscaleup.md) · **After** E10c–E10f prove single dimensions

**Four regimes × multiplier surface:**

| Regime | `spacing_mult` | `max_levels` | `tp_atr_mult` (L0) | `cooldown_mult` |
|--------|----------------|--------------|---------------------|-----------------|
| Compression | TBD | TBD | TBD | TBD |
| Rotation | TBD | TBD | TBD | TBD |
| Expansion | TBD | TBD | TBD | TBD |
| Trend | **no new baskets** | — | — | — |

**Note:** “Trend = disabled” is the **only** hard skip — all other regimes use **multipliers**, not blocks.

**Gate:** E7″ pass on combined policy.

**Status:** **DEFER**

---

### E7″ — Re-validation gate (all E10 promotes)

**ID:** E7″ · **Script:** `ML/scripts/e7_validate.py`

Run on every promoted E10 policy:

```bash
python scripts/e7_validate.py --policy <e10_policy_name> --output features/e7_e10_report.json
```

| Gate | Threshold |
|------|-----------|
| WF fold pass rate | **≥ 75%** |
| w02 DD | ≤ **25%** (or improved vs baseline with net hold) |
| Tail largest loss | **< −$35** (stretch goal on $200) |
| Longest PF | **≥ 1.1** |

**No live trading until E7″ PASS.**

---

## 4. Presets & EA mapping (planned)

| Preset | Bundle | E10 phase |
|--------|--------|-----------|
| `AAG_EURUSD_M5_production.set` | LOCK-202 | Baseline |
| `AAG_EURUSD_M5_AI-809_physics-p45.set` | LOCK-809 | E9d shipped |
| `AAG_EURUSD_M5_LOCK-AI+809_physics-p45.set` | LOCK-AI+809 | E10a |
| `AAG_EURUSD_M5_E10-osc-depth.set` | LOCK-202+E10c | After offline pass |
| `AAG_EURUSD_M5_E10-osc-spacing.set` | LOCK-202+E10d | After offline pass |

Copy to `MQL5\Profiles\Tester\` after each wire.

---

## 5. What E10 explicitly rejects

| Idea | Why |
|------|-----|
| Lower basket TP / basket trail (E502–E507) | Basket exits don't fire; wrong unit |
| Entry skip on low score (806-style) | Kills WR cushion |
| Partial L0 / early TP (807-style) | Clips oscillation winners |
| Global `no_add_after_l0_sl` without gate | Hurts w02 wire (−$108 E9b) |
| Scaled lots / depth budget (E404) | −$58 net precedent |
| Live promotion on sweet-spot only | Jan–Jul 2026 PF 2.28 ≠ E7″ |

---

## 6. Success metrics (leg-level)

Track per phase on **leg** and **basket** separately:

| Metric | Target direction |
|--------|------------------|
| L0 TP rate | ↑ |
| L1+ open after L0 SL | ↓ (809 / E10c) |
| D2+ basket PF | ↑ toward 1.0+ |
| Avg leg win / avg leg loss | ↑ (E10e) |
| WR on w02 | Hold **≥ 63%** |
| 2024 H1 net | ↑ toward breakeven |
| WF pass rate | **≥ 75%** |

---

## 7. One-liner

**E10 enhances oscillation** by scoring rotation vs trend, then applying **leg-level grid multipliers** (depth, spacing, conditional L0 TP) — building on **LOCK-809** geometry, rejecting basket fantasies, and re-passing **E7″** before live.

---

## 8. Time Profile Reference (demo ops)

For demo forward-testing operations and session-time alignment, use:

- [`time_profile.md`](time_profile.md)

Key rule: keep `15–17` as **server-time** window for LOCK-809 comparability.

---

*AAG Enhance Oscillation · Programme E10 · 2026-07-06 · EA v1.33 · LOCK-809 demo · E7″ blocks live*
