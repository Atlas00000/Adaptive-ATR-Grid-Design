We are building an MT5 Expert Advisor (EA) centred around the following trading concept and system architecture:

> **Live system profile:** [`system-profile.md`](system-profile.md)

[Adaptive ATR Grid (AAG)

The Adaptive ATR Grid (AAG) is an evolution of the traditional grid trading strategy, replacing fixed grid spacing with volatility-adjusted spacing based on the Average True Range (ATR). Rather than placing orders every fixed number of pips (e.g., 20 or 50 pips), the EA dynamically adjusts the distance between grid levels according to current market volatility. This allows the system to tighten the grid during quiet markets to capture frequent oscillations and widen it during volatile conditions to reduce overexposure. The primary edge comes from exploiting the market's tendency to oscillate within temporary value ranges while adapting to changing volatility regimes. Unlike conventional grids that often fail during volatility expansion, an ATR-based approach attempts to maintain proportional spacing that reflects current market conditions.

Trading Edge

The Adaptive ATR Grid exploits several well-known market behaviours:

Volatility clustering (high volatility follows high volatility, low follows low).
Short-term price oscillations around temporary equilibrium.
Mean-reverting behaviour during rotational markets.
Market auction cycles where price repeatedly revisits previous value before establishing a new trend.

Instead of predicting market direction, the EA profits from repeated price movement between dynamically calculated grid levels.

Core Strategy

The EA continuously measures ATR over a predefined lookback period (typically ATR 14 or ATR 20). Grid spacing is then calculated as:

Grid Distance = ATR × Volatility Multiplier

Example:

ATR = 12 pips
Multiplier = 1.5

Grid spacing = 18 pips

If ATR expands to 40 pips:

Grid spacing automatically widens to 60 pips.

This adaptation prevents excessive trade density during highly volatile conditions while increasing trading opportunities during calmer markets.

Recommended Timeframes

The system performs best on lower and intermediate intraday timeframes where rotational price behaviour is common.

Recommended:

M5 (Primary)
M15 (Highly recommended)
M30
H1 (lower frequency)

Avoid:

M1 due to excessive noise.
H4 and Daily, where trends often dominate over short-term rotation.
Recommended Instruments

Suitable markets include:

EURUSD
GBPUSD
USDJPY
AUDUSD
EURJPY
XAUUSD (with wider ATR multipliers)
NASDAQ CFDs
GER40

Markets with consistent liquidity and relatively stable spreads are preferable.

Trading Frequency

Expected activity depends on volatility.

Low ATR:

15–40 trades per session.

Medium ATR:

8–20 trades.

High ATR:

3–10 trades.

Unlike conventional grids, trade frequency naturally decreases as volatility increases because grid spacing expands.

Position Sizing

Rather than fixed aggressive scaling, several sizing models can be implemented.

Fixed Lots
Constant lot size.
Simplest implementation.
Most consistent for performance evaluation.
Progressive Grid

Each additional position increases slightly.

Example:

0.20
0.25
0.30
0.36
0.43
ATR Weighted

Position size decreases as ATR increases.

Higher volatility automatically results in smaller exposure.

Equity Scaling

Lot size increases with account growth while maintaining proportional exposure.

Market Conditions

The Adaptive ATR Grid performs best during:

Sideways markets.
Rotational sessions.
Low ADX environments.
Intraday consolidations.
Session overlap periods with two-way order flow.

Poor conditions include:

Strong directional trends.
High-impact news.
Volatility breakouts.
Persistent directional momentum.

Adding a market regime filter to disable the grid during expansion phases can materially improve robustness.

Indicator Stack
Primary
ATR (dynamic spacing)
EMA 50 (trend filter)
ADX (trend strength)
Bollinger Bands (volatility extremes)
Optional
RSI
Tick Volume
Previous Day High/Low
Session High/Low
VWAP (where available)
Multi-timeframe EMA
Structural Filters

Rather than opening grid levels blindly, entries can be aligned with technical structure.

Examples:

Swing highs.
Swing lows.
Previous Day High/Low.
Session extremes.
Consolidation boundaries.
Support and resistance.
Liquidity sweep rejection.
Range midpoint.

This significantly improves entry quality compared with fixed-price grids.

Entry Conditions

A buy grid may require:

Price reaches next ATR grid level.
EMA slope is flat or mildly bullish.
ADX below threshold (indicating weak trend).
Bollinger lower band interaction.
RSI approaching oversold (optional).
Tick volume not indicating breakout participation.

Sell logic mirrors these conditions.

Exit Strategy

Several exit methods can coexist.

Basket Target

Close all positions when combined profit reaches a predefined monetary or percentage target.

Dynamic ATR Target

Profit objective expands with ATR.

Mean Reversion Exit

Close positions when price returns toward the grid centre or moving average.

Trailing Basket

Lock profits while allowing the basket to continue if rotation extends.

Strengths
Automatically adapts to market volatility.
Generates frequent trading opportunities.
Less sensitive to parameter changes than fixed grids.
Reduces overtrading during volatile periods.
Well suited to automated execution.
Straightforward to optimize across instruments.
Weaknesses
Sustained one-directional trends can accumulate large floating losses.
False assumptions of mean reversion during strong momentum.
Frequent execution increases transaction costs.
Performance depends on accurate market regime identification.
Highly volatile news events may invalidate normal ATR relationships.
Enhancements

Several extensions can improve the strategy while preserving its core philosophy:

Trend-Aware Grid: Only deploy buy grids above a higher-timeframe EMA and sell grids below it.
Liquidity Grid: Activate new grid levels only after liquidity sweeps or failed breakouts.
Session Grid: Restrict trading to London and New York sessions.
Volatility Pause: Suspend new entries when ATR exceeds a maximum threshold.
Adaptive Basket Exit: Scale profit targets dynamically based on ATR expansion or contraction.
AI Market Regime Filter: Use a classification model to distinguish ranging, trending, compression, and expansion regimes, enabling the grid only when historical conditions favour rotational behaviour.
Summary

The Adaptive ATR Grid modernizes the classic grid concept by replacing static spacing with volatility-responsive positioning and by incorporating structural, trend, and regime filters. Its theoretical edge is rooted in auction-market rotation and volatility adaptation rather than simple price averaging. When combined with market structure, session context, and dynamic trade management, it becomes a flexible framework for exploiting intraday oscillations while remaining responsive to changing market conditions.]
Current Development Scope (Phase 1):
The focus right now is strictly on building the automated execution engine based on the selected indicators and signal logic. We are intentionally keeping the system lightweight and modular at this stage.
Important:
Do NOT introduce advanced filtering, AI layers, session filters, portfolio management, adaptive optimisation, or overengineered logic yet.
Do NOT add unnecessary complexity outside the core execution workflow.
The goal is simply to automate trade execution reliably using the selected indicators and trading conditions.
Core Objective:
Build a configurable execution engine capable of:
Reading indicator values and market conditions in real time
Evaluating entry conditions
Executing buy/sell trades automatically
Managing basic trade risk
Providing clean parameter configuration for optimization and future scaling
Execution Engine Requirements:
Configurable indicator inputs
Configurable entry conditions
Buy/sell execution logic
Support for market orders initially
Clean order validation before execution
Low-latency and lightweight processing
Modular architecture for future expansion
Basic Risk Management & Position Sizing:
Include foundational risk and trade management features only, such as the following:
Fixed lot size input
Optional risk-based position sizing (% (risk per trade)
Stop Loss (fixed points/pips or ATR-based if applicable)
Take Profit configuration
Risk-to-reward ratio support
Maximum spread filter
Slippage control
Maximum simultaneous open trades
Basic cooldown between trades
Magic number management
Equity/balance safety checks
Configurable trading permissions (buy only / sell only / both)
One Symbol vs Multi-Symbol
Use:
Single symbol
Single timeframe
Based strictly on the current chart
This is the correct decision for Phase 1.
Benefits:
Simpler execution flow
Easier debugging
Lower CPU usage
Cleaner state management
More reliable order tracking
Avoids synchronization complexity
Architecture assumption:
One EA instance per chart
One symbol context
One timeframe context
Avoid for now:
multi-symbol scanning
centralized portfolio engine
cross-chart communication
symbol routing
correlation logic
Future extensibility:
Your modular structure should still isolate the following:
signal engine
execution engine
risk engine
This makes future multi-symbol expansion possible without rewriting the core.
The EA should:
Be modular and extensible
Use clean separation of concerns
Support future integration of:
filters
session logic
AI optimization
volatility layers
portfolio controls
advanced trade management
multi-strategy routing
Architecture Goals:
Clean and maintainable codebase
Production-style folder structure
Clear module responsibilities
Configurable engine design
Scalable architecture without premature complexity
High execution reliability
Easy debugging and testing
Suggested Focus Areas:
Signal evaluation pipeline
Indicator management system
Trade execution module
Risk management module
Position sizing engine
Configuration/input management
Logging and debugging utilities
State and trade tracking
What I need from you:
Design the execution engine architecture
Define module responsibilities and execution workflow
Recommend an MT5 production-grade folder structure
Suggest industry best practices for EA development
Keep implementation practical, scalable, and efficient
Avoid unnecessary abstraction or feature creep
Prioritize configurability, maintainability, and execution reliability
The current objective is NOT strategy perfection or advanced intelligence.
The objective is building a strong, configurable execution foundation first.

Gap answered
### Phase 1 Boundary

* **Recommendation:** Build a **single-direction, multi-layer ATR Grid** (true grid), not a single-entry EA.
* Maximum 5–8 grid levels.
* State machine:

  * `IDLE`
  * `ARMED`
  * `GRID_ACTIVE`
  * `MANAGING`
  * `EXITING`
  * `COOLDOWN`

---

### Indicator Subset (Phase 1)

**Mandatory**

* ATR(14) – Grid spacing
* EMA(50) – Directional bias
* ADX(14) – Trend strength filter

**Deferred**

* Bollinger Bands
* RSI
* Tick Volume
* VWAP
* HTF EMA
* Structure/Liquidity filters

---

### Entry Rule Precision

* EMA slope:

  * Flat: |Slope| < 0.10 ATR over last 5 bars
  * Bullish: EMA rising for ≥3 closed candles
* ADX:

  * Maximum = **20** (allow grid)
* BB:

  * Close outside band then rejection close back inside
* RSI (if enabled):

  * Buy ≤35
  * Sell ≥65

---

### Grid Level Math

* Anchor = **first entry price**
* Grid Distance = `ATR × Multiplier`
* Levels:

  * Buy: Anchor − (n × Distance)
  * Sell: Anchor + (n × Distance)
* Freeze ATR distance for the entire basket.
* Recalculate only after basket closes.

---

### Exit Model (Phase 1)

* Individual SL
* Individual TP
* Basket TP (enabled)
* No partial closes yet
* No trailing basket
* No mean-reversion exit (Phase 2)

---

### Position Sizing Formula

* Risk based on **Equity**
* Lot Size = Risk% ÷ SL Distance
* Normalize to broker lot step
* Min/Max lot limits configurable
* Optional fixed-lot mode

---

### SL / TP Modes

* Default:

  * SL = 2 × ATR
  * TP = 1.5 × ATR
* Optional fixed-pip mode
* Risk:Reward automatically derived from ATR mode

---

### Trade Direction Policy

* One direction at a time
* Never run buy and sell grids simultaneously
* Bias determined by EMA filter
* Compatible with both Hedging and Netting accounts

---

### Cooldown Semantics

* Time-based
* Default: 15–30 minutes after basket closes
* Global cooldown (not per direction)

---

### New-Bar Detection

* Signals evaluated **only on closed bars**
* Trade management (SL/TP) runs every tick
* Prevents duplicate entries and repainting

---

### Restart / Persistence

* On EA restart:

  * Detect existing positions
  * Rebuild basket state
  * Recover anchor, levels, and basket metrics
* Never reset active grids automatically

---

### Requote & Error Handling

* Retry transient errors (2–3 attempts)
* Handle:

  * Requotes
  * Busy trade context
  * Invalid stops
  * Off quotes
* Abort on fatal errors
* Log all `TRADE_RETCODE_*` results

---

### Parameter Defaults

* ATR Period = **14**
* ATR Multiplier = **1.5**
* EMA = **50**
* ADX = **14**
* ADX Threshold = **20**
* BB = **20, 2.0**
* RSI = **14**
* Max Grid Levels = **6**
* Max Spread = **2.0 pips** (pair dependent)

---

### Testing Plan

**Initial Build**

* Instrument: EURUSD
* Timeframe: M5
* Period: 3–5 years
* Variable spread enabled

**Acceptance Criteria**

* Positive expectancy
* Profit Factor > 1.3
* Win Rate > 60%
* Max DD < 20%
* Stable across multiple years

**Validation**

1. Backtest
2. Walk-forward
3. Monte Carlo
4. Demo forward test
5. Live micro account

---

### Logging Level

**Strategy Tester**

* Full debug logs
* Signal decisions
* Grid calculations
* Basket statistics

**Live**

* Errors
* Entries/Exits
* Basket summaries
* Risk events

**Optional**

* CSV performance log

---

### File Layout Decision

```text
AdaptiveATRGrid/
│
├── AdaptiveATRGrid.mq5
├── AdaptiveATRGrid.mqproj
├── Include/
│   ├── ATREngine.mqh
│   ├── SignalEngine.mqh
│   ├── GridEngine.mqh
│   ├── BasketManager.mqh
│   ├── RiskManager.mqh
│   ├── TradeManager.mqh
│   ├── StateMachine.mqh
│   ├── Logger.mqh
│   └── Utils.mqh
│
├── Indicators/
├── Presets/
├── Tests/
└── Docs/
```

This structure keeps Phase 1 modular, testable, and ready for Phase 2 additions (AI regime filter, structural filters, VWAP, liquidity logic, and adaptive basket management).
