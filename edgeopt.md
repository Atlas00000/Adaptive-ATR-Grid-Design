Based on your discovery report and system profile, I don't think you need more indicators or more filters. The discovery process has already shown that **most traditional optimizations reduce trade frequency without improving expectancy**.  

The current edge is already well-defined:

* Session edge (15–17)
* RSI rotation
* ATR adaptive spacing
* EMA + ADX filter
* Full grid (6 levels)
* PF 1.93 on the discovery window and 1.46 over 19 months
* Failure comes from long-horizon tail losses, not poor entries. 

Instead of adding more filters, I'd improve the **performance metrics**.

---

# 1. Improve Expectancy ⭐⭐⭐⭐⭐

Current weakness

* Win Rate = High
* Average Loss > Average Win
* PF depends heavily on maintaining a high WR

Improve by making winners larger instead of filtering more entries.

Ideas

* Dynamic TP based on ATR percentile
* Partial profit at 1R
* Runner on remaining position
* Profit locking after 1 ATR

Goal

* Avg Win > Avg Loss
* Expectancy increases without reducing WR

---

# 2. Reduce Tail Risk ⭐⭐⭐⭐⭐

This is your biggest weakness.

Instead of stopping baskets earlier...

Predict baskets that will become catastrophic.

Build a Basket Health Score

Inputs

* Current ATR
* ATR acceleration
* ADX acceleration
* EMA slope
* Grid depth
* Floating DD
* Time in trade
* Distance from EMA
* Distance from VWAP

Score example

```text
0-30     Healthy

30-60    Monitor

60-80    Defensive

80-100   Emergency
```

Actions

* reduce new adds
* shrink lot multiplier
* reduce TP
* hedge
* flatten basket

Instead of

```text
IF DD>2%

Close Basket
```

---

# 3. Adaptive Grid Density ⭐⭐⭐⭐⭐

Currently

```text
Distance

ATR ×1.5
```

Make spacing nonlinear.

Example

Low ATR

* tighter spacing

Medium ATR

* normal

High ATR

* wider than linear

Example

```text
Grid Distance

ATR × Volatility Curve
```

Instead of

```text
ATR × Constant
```

---

# 4. Dynamic Grid Depth ⭐⭐⭐⭐☆

Instead of

```text
Max Levels = 6
```

Use

```text
Compression

8 levels

Rotation

6

Expansion

3

Trend

0
```

Not based only on ADX.

Include

* ATR percentile
* EMA slope
* Volatility acceleration

---

# 5. Entry Quality Score ⭐⭐⭐⭐⭐

Current

Binary

Trade

or

No Trade

Instead

Every signal gets scored.

Example

| Metric                  | Score |
| ----------------------- | ----: |
| RSI quality             |    20 |
| EMA slope               |    20 |
| ATR regime              |    15 |
| Spread                  |    10 |
| Session timing          |    10 |
| Distance from EMA       |    10 |
| Previous basket outcome |     5 |
| HTF bias                |    10 |

Only trade

```text
Score >70
```

---

# 6. Adaptive Position Sizing ⭐⭐⭐⭐☆

Instead of

Fixed

```text
0.10
```

Use

```text
Lot

Base

×

Edge Score

×

Regime Score

×

Recent Performance
```

Strong conditions

Higher size

Weak conditions

Lower size

---

# 7. Adaptive Cooldown ⭐⭐⭐⭐☆

Instead of

20 minutes

Use

After

Good basket

```text
5 min
```

After

Deep recovery

```text
45 min
```

After

Stop Loss

```text
60 min
```

---

# 8. AI Probability Layer ⭐⭐⭐⭐⭐

Don't let AI generate trades.

Use AI to estimate

* Probability of mean reversion
* Probability of recovery
* Probability basket reaches TP
* Probability trend continues
* Expected maximum adverse excursion
* Expected holding time

AI becomes a supervisor.

---

# 9. Performance Memory ⭐⭐⭐⭐⭐

The EA should learn from recent performance.

Example

Last 20 baskets

Metrics

* WR
* PF
* Avg DD
* Avg Recovery
* Avg Hold Time

If performance deteriorates

Automatically

* reduce lot
* reduce levels
* increase spacing
* increase cooldown

---

# 10. Market State Machine ⭐⭐⭐⭐⭐

Current

Simple

Trade / Don't Trade

Upgrade to

```text
Compression

↓

Accumulation

↓

Rotation

↓

Expansion

↓

Trend

↓

Exhaustion

↓

Rotation
```

Each state has

* spacing
* TP
* SL
* max levels
* lot multiplier
* cooldown

---

# 11. Recovery Efficiency Metric ⭐⭐⭐⭐☆

Track

* % baskets recovered
* Recovery time
* Maximum grid level used
* Recovery distance

Then optimize for

* Faster recovery
* Fewer levels
* Less capital

instead of only Net Profit.

---

# 12. Portfolio-Level Metrics ⭐⭐⭐⭐☆

Instead of optimizing only

* PF
* WR

Track

* Recovery Factor
* Ulcer Index
* MAR Ratio
* Return / Max DD
* Profit per Trading Hour
* Profit per Basket
* Profit per Grid Level
* Capital Efficiency (Profit ÷ Margin Used)
* Maximum Floating Exposure
* Consecutive Basket Losses

---

# 13. Build a Meta-Optimizer ⭐⭐⭐⭐⭐

Rather than optimizing individual parameters, optimize objectives such as:

* Maximize Expectancy
* Maximize PF
* Minimize Tail Risk
* Minimize Capital Usage
* Minimize Recovery Time
* Maximize Profit per Hour
* Maximize Recovery Factor

This shifts optimization from "best parameter values" to "best system behavior."

---

## Overall priorities

| Priority | Improvement                          | Expected Impact |
| -------- | ------------------------------------ | --------------: |
| ⭐⭐⭐⭐⭐    | Basket Health Score                  |       Very High |
| ⭐⭐⭐⭐⭐    | Entry Quality Scoring                |       Very High |
| ⭐⭐⭐⭐⭐    | AI Regime/Recovery Layer             |       Very High |
| ⭐⭐⭐⭐⭐    | Performance Memory (self-adaptive)   |       Very High |
| ⭐⭐⭐⭐⭐    | Dynamic Expectancy Optimization      |       Very High |
| ⭐⭐⭐⭐☆    | Nonlinear ATR Grid Spacing           |            High |
| ⭐⭐⭐⭐☆    | Dynamic Grid Depth                   |            High |
| ⭐⭐⭐⭐☆    | Adaptive Position Sizing             |            High |
| ⭐⭐⭐⭐☆    | Portfolio-Level Optimization Metrics |            High |
| ⭐⭐⭐☆☆    | Additional indicators                |             Low |

The evidence from your discovery process suggests the **entry edge is already largely optimized**. Nearly all added filters (BB, HTF EMA, structure filters, seasonal filters, ATR gates, adaptive exits) either reduced trade count or degraded net performance. The next meaningful gains are more likely to come from **adaptive trade management and intelligent state estimation**—improving capital efficiency, controlling tail risk, and increasing expectancy while preserving the existing entry edge.  
