# AAG ML Pipeline (Phase E8)

Offline training and policy simulation for the AI supervisor layer.

**Do not wire models to the EA until offline gates pass** — see [`../ai_enhance.md`](../ai_enhance.md).

## Layout

| Path | Purpose |
|---|---|
| `export/` | Raw diagnostics CSV from Strategy Tester |
| `features/` | Basket-level feature tables |
| `models/` | Trained models + `registry.json` |
| `notebooks/` | EDA only |
| `scripts/` | Build, train, simulate, export |

## Quick start

```bash
cd ML
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

python scripts/build_baskets.py --input export/ --output features/baskets.parquet
python scripts/build_features.py --input features/baskets.parquet
python scripts/simulate_policy.py --policy health --window w02_ext19mo
python scripts/simulate_policy.py --policy health --window w02_ext19mo --legacy-health  # hindsight compare
python scripts/test_basket_replay.py
```

### AI-802 outputs (`features/`)

| File | Purpose |
|---|---|
| `train.parquet` | Full feature matrix (1 row / basket) |
| `train_entry.parquet` | Entry-safe features for AI-804 |
| `train_health.parquet` | Close-state features for AI-805 |
| `train_folds.parquet` | Walk-forward expanded rows (w02, 3m/1m) |
| `feature_report.json` | Label rates, leakage check |
| `sim_report.json` | Policy sim gates (`simulate_policy.py`) |

### AI-810 health sim (causal replay)

`simulate_policy.py --policy health` uses **event-level replay** from leg CSVs (`export/*_trades_*.csv`):

- **Open / close / 60s checkpoints** with linear leg-PnL interpolation (floating estimate)
- **`flatten_only`** (default) — matches EA v1.13 wire guards
- **`full`** — no-add, tighten TP, trim best leg (v1.12 wire)
- **`--legacy-health`** — deprecated post-hoc PnL cap (hindsight; do not use for wire gates)

Requires diagnostics leg export for the window under test.

### AI-807 exit / expectancy research (offline only)

```bash
python scripts/analyze_expectancy.py --window AI806_805p --replay-mfe
python scripts/simulate_exit_policy.py --window AI806_805p --policy all
```

Causal exit overlays on 805p health replay (`exit_replay.py`). **No EA wire** — see [`../ai_enhance.md`](../ai_enhance.md) §9.6.

### E7 walk-forward + Monte Carlo (EDGE-702/703)

```bash
python scripts/e7_validate.py --policy all
```

Basket-level WF (3m/1m) + 2000-iter MC shuffle. See [`../ai_enhance.md`](../ai_enhance.md) §9.9.

### E7′ re-validation (E9c `adx_lt_18` policy)

```bash
python scripts/e7_validate.py --policy lock202_adx_lt_18
```

See [`../ai_enhance.md`](../ai_enhance.md) §9.13 · report `features/e7_prime_report.json`.

### E9a basket intelligence (offline)

```bash
python scripts/e9a_basket_intelligence.py --window all
```

Recovery, lifetime, capital efficiency, depth segments. See [`../ai_enhance.md`](../ai_enhance.md) §9.10.

### E9b grid geometry sweep (offline)

```bash
python scripts/e9b_grid_geometry.py --window all
```

Depth cap, spacing, `no_add_after_l0_sl` on causal replay. See [`../ai_enhance.md`](../ai_enhance.md) §9.11.

### E9c context-gated geometry

```bash
python scripts/e9c_context_geometry.py
```

Sweep entry-context gates for `no_add_after_l0_sl`. See [`../ai_enhance.md`](../ai_enhance.md) §9.12.

### E9d physics stack-risk gate

```bash
python scripts/e9d_physics_labels.py
python scripts/e9d_simulate.py
python scripts/e7_validate.py --policy lock202_physics_p45
python scripts/e7_validate.py --policy lock_ai_physics_p45
python scripts/export_mql_constants.py --model models/stack_risk_v0.joblib --type stack
```

See [`../ai_enhance.md`](../ai_enhance.md) §9.14–§9.15 · promote **`physics_lr_p45`** · presets **LOCK-809** / **LOCK-AI+809**.

### AI-808 model export + runtime

```bash
python scripts/export_models.py --bundle LOCK-AI
python scripts/export_mql_constants.py --model models/basket_health_v0.joblib --type health
```

- **Embedded LR** (default): weights in `Include/AI*Model.mqh`
- **Optional ONNX:** `pip install skl2onnx` then copy `models/onnx/*.onnx` → `Terminal/Common/Files/AI/`
- **Registry:** `models/registry.json` — EA reads `InpAIModelVersion` at init

## Config

Thresholds and feature lists live in `config.yaml`. Defaults are **low-threshold / anti-overfilter** aligned with E8 design.

## Model registry

`models/registry.json` tracks promoted model versions. EA reads version via `InpAIModelVersion` (AI-808).
