# Phase E0 — Run Guide

Diagnostics do **not** change strategy logic. Recompile (F7), then run backtests with diagnostics presets.

---

## EDGE-000 — Baseline archive

**Preset:** `MQL5\Profiles\Tester\AAG_EURUSD_M5_EDGE-000_baseline.set`

1. Strategy Tester → select **AAG** → EURUSD M5 → 2025.01.01 – 2025.12.31  
2. **Inputs → Load** → pick preset from list above  
3. Save HTML report as reference (PF, WR, DD)  
4. Log metrics in `Edge Discovery.md` → Results log  

---

## EDGE-001 — Trade journal export

**Preset:** `MQL5\Profiles\Tester\AAG_EURUSD_M5_EDGE-001_diagnostics.set`

**After test completes**, open the Experts tab and look for:

```text
========== AAG E0 GATE ANALYSIS (EDGE-001/002) ==========
```

**CSV files** (MetaTrader shared data folder):

| File | Content |
|---|---|
| `AAG_diag_trades_EURUSD.csv` | One row per closed leg |
| `AAG_diag_summary_EURUSD.csv` | Aggregated buckets |

**Windows path:** `File → Open Data Folder → MQL5 → Files`  
(With `FILE_COMMON`, also check `Terminal\Common\Files`)

### Trade CSV columns

`ticket`, `basket_id`, `level`, `levels_at_open`, `basket_max_levels`, `direction`, `hour`, `weekday`, `session`, `bad_hour`, `adx`, `atr`, `profit`, `hold_sec`, `exit_reason` (SL / TP / BASKET)

### Summary CSV sections

| Section | EDGE task |
|---|---|
| `level_leg` | EDGE-002 — WR/P/L by leg level L0–L6 |
| `basket_depth` | EDGE-002 — WR/P/L by max basket depth D1–D6 |
| `hour` | Session edge map |
| `weekday` | Day-of-week edge |
| `exit` | SL vs TP vs BASKET split |
| `month` | EDGE-003 seasonality |

---

## EDGE-002 — Grid depth buckets

No extra code. After EDGE-001 run:

1. Open `AAG_diag_summary_EURUSD.csv`  
2. Copy `level_leg` and `basket_depth` rows into `Edge Discovery.md` → **E0 Results**  
3. Note which depth has worst P/L and lowest WR  

**Gate question:** Do depth ≥3 baskets account for most losses?

---

## EDGE-003 — Jan 2025 vs full 2025

Same preset (`EDGE-001`). Only the **tester date range** changes.

| Run | Tester dates | Summary filter |
|---|---|---|
| **EDGE-003a** | 2025.01.01 – 2025.01.31 | `month` row = 1 |
| **EDGE-003b** | 2025.01.01 – 2025.12.31 | All months |

Compare PF, WR, DD from HTML reports + monthly rows in summary CSV.

Rename CSV between runs to avoid overwrite:

- `AAG_diag_trades_EURUSD_2025jan.csv`
- `AAG_diag_trades_EURUSD_2025full.csv`

---

## E0 gate → Phase E1

Proceed to **EDGE-101** when the Journal prints:

```text
E0 Gate (>=60% one factor): PASS — proceed to E1
```

Gate passes if **either**:

- ≥60% of loss $ from legs where `basket_max_levels >= 3`, **or**
- ≥60% of loss $ from `bad_hour` trades (hours 9, 16, 18, 19, 21, 22)

If inconclusive, inspect trade CSV in Excel and refine bad-hour / depth thresholds before E1.

---

## Inputs reference

| Input | Default | Purpose |
|---|---|---|
| `InpDiagnosticsEnabled` | true | Master switch |
| `InpDiagnosticsCSV` | true | Write CSV files |
| `InpDiagnosticsFilePrefix` | AAG_diag | File name prefix |

Set `InpDiagnosticsEnabled=false` for production / optimisation runs without CSV overhead.
