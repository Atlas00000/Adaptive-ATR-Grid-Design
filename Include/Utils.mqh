//+------------------------------------------------------------------+
//| Utils.mqh — inputs, types, helpers                               |
//+------------------------------------------------------------------+
#ifndef AAG_UTILS_MQH
#define AAG_UTILS_MQH

//--- Enums (must precede inputs)
enum ENUM_GRID_STATE
  {
   GRID_STATE_IDLE       = 0,
   GRID_STATE_ARMED      = 1,
   GRID_STATE_GRID_ACTIVE = 2,
   GRID_STATE_MANAGING   = 3,
   GRID_STATE_EXITING    = 4,
   GRID_STATE_COOLDOWN   = 5
  };

enum ENUM_TRADE_BIAS
  {
   BIAS_NONE  = 0,
   BIAS_BUY   = 1,
   BIAS_SELL  = -1
  };

enum ENUM_SIZING_MODE
  {
   SIZING_FIXED_LOT = 0,
   SIZING_RISK_PERCENT = 1
  };

enum ENUM_SLTP_MODE
  {
   SLTP_ATR   = 0,
   SLTP_FIXED = 1
  };

enum ENUM_TRADE_PERMISSION
  {
   TRADE_BOTH = 0,
   TRADE_BUY_ONLY = 1,
   TRADE_SELL_ONLY = 2
  };

enum ENUM_BASKET_TP_MODE
  {
   BASKET_TP_MONEY   = 0,
   BASKET_TP_PERCENT = 1
  };

enum ENUM_ENTRY_FILTER
  {
   ENTRY_FILTER_NONE         = 0,
   ENTRY_FILTER_BB_REJECT    = 1,
   ENTRY_FILTER_RSI          = 2,
   ENTRY_FILTER_BB_RSI       = 3,
   ENTRY_FILTER_HTF_EMA      = 4,
   ENTRY_FILTER_EMA_DISTANCE = 5
  };

//--- Inputs: Indicators
input group "=== Indicators ==="
input int    InpATRPeriod       = 14;
input double InpATRMultiplier   = 1.5;
input int    InpEMAPeriod       = 50;
input int    InpADXPeriod       = 14;
input int    InpADXThreshold    = 20;

//--- Inputs: Grid
input group "=== Grid ==="
input int    InpMaxGridLevels   = 6;

//--- Inputs: Risk
input group "=== Risk ==="
input ENUM_SIZING_MODE InpSizingMode     = SIZING_FIXED_LOT;
input double InpFixedLot                 = 0.10;
input double InpRiskPercent              = 1.0;
input double InpMinLot                   = 0.01;
input double InpMaxLot                   = 5.0;
input double InpMaxSpreadPips            = 2.0;
input int    InpSlippagePoints            = 10;
input int    InpMaxOpenTrades            = 6;
input int    InpCooldownMinutes          = 20;
input double InpEquityFloorPercent       = 50.0;
input ENUM_TRADE_PERMISSION InpTradePermission = TRADE_BOTH;

//--- Inputs: SL / TP
input group "=== SL / TP ==="
input ENUM_SLTP_MODE InpSLTPMode         = SLTP_ATR;
input double InpSLATRMult                = 2.0;
input double InpTPATRMult                = 1.5;
input double InpSLFixedPips              = 20.0;
input double InpTPFixedPips              = 15.0;

//--- Inputs: Basket exit
input group "=== Basket Exit ==="
input bool   InpBasketTPEnabled          = true;
input ENUM_BASKET_TP_MODE InpBasketTPMode = BASKET_TP_MONEY;
input double InpBasketTPMoney            = 50.0;
input double InpBasketTPPercent          = 0.5;

//--- Inputs: Basket management (Phase E5)
input group "=== Basket Management (E5) ==="
input bool   InpBasketTrailEnabled       = false;
input double InpBasketTrailActivateMoney = 12.0;
input double InpBasketTrailLockPercent   = 50.0;
input bool   InpMRExitEnabled            = false;
input double InpMRExitToleranceATR       = 0.05;
input bool   InpBasketTPAdaptive         = false;
input double InpAdaptiveTPPerLevelATR    = 0.5;
input bool   InpTimeStopEnabled          = false;
input int    InpTimeStopMinutes          = 90;

//--- Inputs: Grid & risk containment (Phase E4)
input group "=== Grid & Risk (E4) ==="
input bool   InpBasketDDCapEnabled        = false;
input double InpBasketDDCapPercent        = 2.0;
input bool   InpMAEExitEnabled            = false;
input double InpMAEExitATRMult            = 4.0;
input bool   InpAdaptiveDepthEnabled      = false;
input double InpAdaptiveDepthADXThreshold = 25.0;
input int    InpAdaptiveDepthMaxTight     = 3;
input bool   InpScaledLotsEnabled         = false;
input double InpScaledLotFactor           = 0.85;

//--- Inputs: Regime gates (Phase E3)
input group "=== Regime Gates (E3) ==="
input bool   InpRegimeATRPauseEnabled       = false;
input double InpRegimeATRPauseMult          = 1.8;
input int    InpRegimeATRPauseLookback      = 20;
input bool   InpRegimeADXSlopeEnabled       = false;
input int    InpRegimeADXSlopeBars          = 3;
input bool   InpRegimeATRPercentileEnabled  = false;
input double InpRegimeATRPercentileMax      = 80.0;
input int    InpRegimeATRPercentileLookback = 100;
input bool   InpRegimeChopOnlyEnabled       = false;
input int    InpRegimeChopMinCrosses        = 3;
input int    InpRegimeChopLookback          = 20;
input bool   InpRegimeSeasonalSkipEnabled   = false;
input int    InpRegimeSkipMonthStart        = 6;
input int    InpRegimeSkipMonthEnd          = 9;

//--- Inputs: Structure & liquidity (Phase E6)
input group "=== Structure & Liquidity (E6) ==="
input bool   InpStructPDHLEnabled           = false;
input double InpStructPDHLToleranceATR      = 0.35;
input bool   InpStructSessionHLEnabled        = false;
input double InpStructSessionHLToleranceATR = 0.35;
input bool   InpStructLiqSweepEnabled       = false;
input bool   InpStructLiqSweepUsePD         = false;
input double InpStructLiqSweepMinATR        = 0.05;
input bool   InpStructRangeMidAnchorEnabled = false;
input int    InpStructRangeMidSource        = 0;

//--- Inputs: AI supervisor (Phase E8)
input group "=== AI Supervisor (E8) ==="
input bool   InpAIEnabled                 = false;
input string InpAIModelVersion            = "";
input bool   InpAIUseOnnx                 = false;  // AI-808: load ONNX from Files/AI/ (else embedded LR)
input bool   InpAIOnnxFallbackEmbedded    = true;   // AI-808: if ONNX missing, use embedded constants
input bool   InpAIMemoryEnabled           = false;
input bool   InpAIEntryContextEnabled     = false;
input bool   InpAIBasketHealthEnabled     = false;
input bool   InpAIHealthFlattenOnly       = false;  // match offline sim — no add-block / tighten / trim
input int    InpAIHealthCheckSec          = 60;     // throttle — match sim checkpoint (not every tick)
input double InpAIHealthFlattenFloatUSD   = -18.0;  // stress-flatten min float (with score)
input bool   InpAIHealthHardCapEnabled    = true;   // hard tail cap — no health score required
input double InpAIHealthHardCapUSD        = -25.0;  // multi-leg cap (open>=2, age>=120s)
input bool   InpAIHealthHardCapL1Enabled  = true;   // single-leg cap — catches SL tails
input double InpAIHealthHardCapL1USD      = -28.0;  // below ~30 pip SL (was -35, never fired)
input int    InpAIHealthHardCapL1MinSec   = 30;     // min basket age before L1 cap
input bool   InpAIHealthBasketCapEnabled  = true;   // total basket PnL cap (realized+float)
input double InpAIHealthBasketCapUSD      = -32.0;  // flatten when basket total below this
input int    InpAIHealthBasketCapMinLegs  = 1;      // 1 = includes post-partial-SL window
input bool   InpAIHealthSLCascadeEnabled  = true;   // surgical cascade on partial leg SL
input int    InpAIHealthSLCascadeMinLegs  = 2;    // only when basket had 2+ legs
input bool   InpAIHealthSLCascadeAnyPartial = false; // flatten on ANY partial SL (805o — too aggressive)
input double InpAIHealthSLCascadeLossUSD  = -9.0;   // leg deal PnL threshold (805l tail fix)
input double InpAIHealthSLCascadeStackUSD = -28.0;  // deal+float projected stack guard
input double InpAIHealthSLCascadeFloatUSD = -8.0;   // legacy float-only trigger
input bool   InpAIHealthSLCascadeUseFloat = false;  // float-only trigger off by default
input bool   InpAIRegimeEnabled           = false;
input double InpAIEntryBlockFloor         = 0.12;
input double InpAIHealthNoAddThreshold    = 55.0;
input double InpAIHealthFlattenThreshold  = 88.0;
input double InpAIRegimeTrendSkipProb     = 0.62;  // LR wire max ~0.69 — 0.85 never fired
input bool   InpAIRegimeLogScore          = true;   // log P(bad) at arm when >= 0.45
input double InpAILotMultMin              = 0.65;
input double InpAILotMultMax              = 1.00;

//--- Inputs: General
input group "=== General ==="
input ulong  InpMagicNumber              = 20260705;
input bool   InpTesterVerbose            = true;

//--- Inputs: Session / Time (Phase E1)
input group "=== Session / Time (E1) ==="
input bool   InpTimeFilterEnabled        = false;
input int    InpTradeHourStart           = 10;
input int    InpTradeHourEnd             = 13;
input bool   InpUseHourBlacklist         = false;
input string InpBlockedHours             = "9,16,18,19,21,22";
input bool   InpDayFilterEnabled         = false;
input bool   InpTradeMon                 = true;
input bool   InpTradeTue                 = true;
input bool   InpTradeWed                 = true;
input bool   InpTradeThu                 = true;
input bool   InpTradeFri                 = true;
input bool   InpTradeSat                 = false;
input bool   InpTradeSun                 = false;

//--- Inputs: Entry confirmation (Phase E2)
input group "=== Entry Confirmation (E2) ==="
input ENUM_ENTRY_FILTER InpEntryFilter   = ENTRY_FILTER_NONE;
input int    InpBBPeriod                 = 20;
input double InpBBDeviation              = 2.0;
input int    InpRSIPeriod                = 14;
input double InpRSIBuyMax                = 52.0;
input double InpRSISellMin               = 48.0;
input ENUM_TIMEFRAMES InpHTFTimeframe    = PERIOD_M15;
input int    InpHTFEMAPeriod             = 50;
input double InpHTFEMAToleranceMult      = 0.20;
input double InpEMADistanceMult          = 0.15;

//--- Inputs: Diagnostics (Phase E0)
input group "=== Diagnostics (Phase E0) ==="
input bool   InpDiagnosticsEnabled         = true;
input bool   InpDiagnosticsCSV           = true;
input string InpDiagnosticsFilePrefix    = "AAG_diag";

//--- Structs
struct SignalResult
  {
   ENUM_TRADE_BIAS bias;
   bool            ema_flat;
   bool            ema_bullish;
   bool            ema_bearish;
   double          adx;
   string          reason;
  };

struct GridContext
  {
   double          anchor;
   double          frozen_distance;
   ENUM_TRADE_BIAS bias;
   int             levels_filled;
   int             next_level;
  };

struct BasketState
  {
   ulong           tickets[];
   int             level_count;
   double          anchor;
   double          frozen_distance;
   ENUM_TRADE_BIAS bias;
   datetime        basket_start;
  };

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
double AAG_PipSize(const string symbol)
  {
   const int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits == 3 || digits == 5)
      return SymbolInfoDouble(symbol, SYMBOL_POINT) * 10.0;
   return SymbolInfoDouble(symbol, SYMBOL_POINT);
  }

double AAG_PointsToPips(const string symbol, const double points)
  {
   const double pip = AAG_PipSize(symbol);
   if(pip <= 0.0)
      return 0.0;
   return points / pip;
  }

double AAG_PipsToPoints(const string symbol, const double pips)
  {
   return pips * AAG_PipSize(symbol);
  }

double AAG_NormalizeLot(const string symbol, double lot,
                        const double min_lot, const double max_lot)
  {
   const double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   const double vmin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   const double vmax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0)
      return min_lot;

   lot = MathFloor(lot / step) * step;
   lot = MathMax(lot, MathMax(min_lot, vmin));
   lot = MathMin(lot, MathMin(max_lot, vmax));
   return NormalizeDouble(lot, 2);
  }

string AAG_GVPrefix(const string symbol, const ulong magic)
  {
   return "AAG_" + symbol + "_" + IntegerToString((long)magic);
  }

string AAG_GridStateToString(const ENUM_GRID_STATE state)
  {
   switch(state)
     {
      case GRID_STATE_IDLE:        return "IDLE";
      case GRID_STATE_ARMED:       return "ARMED";
      case GRID_STATE_GRID_ACTIVE: return "GRID_ACTIVE";
      case GRID_STATE_MANAGING:    return "MANAGING";
      case GRID_STATE_EXITING:     return "EXITING";
      case GRID_STATE_COOLDOWN:    return "COOLDOWN";
     }
   return "UNKNOWN";
  }

string AAG_BiasToString(const ENUM_TRADE_BIAS bias)
  {
   if(bias == BIAS_BUY)  return "BUY";
   if(bias == BIAS_SELL) return "SELL";
   return "NONE";
  }

//+------------------------------------------------------------------+
//| New closed bar detection                                         |
//+------------------------------------------------------------------+
class CBarTracker
  {
private:
   datetime m_last_closed_bar;

public:
                     CBarTracker() : m_last_closed_bar(0) {}

   bool              IsNewClosedBar(const string symbol, const ENUM_TIMEFRAMES tf)
     {
      const datetime closed = iTime(symbol, tf, 1);
      if(closed == 0)
         return false;
      if(closed != m_last_closed_bar)
        {
         m_last_closed_bar = closed;
         return true;
        }
      return false;
     }

   datetime          LastClosedBar() const { return m_last_closed_bar; }
  };

#endif // AAG_UTILS_MQH
