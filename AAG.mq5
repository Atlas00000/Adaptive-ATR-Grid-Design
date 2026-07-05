//+------------------------------------------------------------------+
//|                                                          AAG.mq5 |
//|                                  Adaptive ATR Grid — Phase 1     |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, AAG"
#property link      "https://www.mql5.com"
#property version   "1.08"
#property strict

#include "Include/Utils.mqh"
#include "Include/Logger.mqh"
#include "Include/Diagnostics.mqh"
#include "Include/ATREngine.mqh"
#include "Include/SignalEngine.mqh"
#include "Include/GridEngine.mqh"
#include "Include/StateMachine.mqh"
#include "Include/RiskManager.mqh"
#include "Include/BasketManager.mqh"
#include "Include/TradeManager.mqh"
#include "Include/RegimeGate.mqh"
#include "Include/StructureGate.mqh"

//--- Module instances
CLogger         g_logger;
CBarTracker     g_bars;
CDiagnostics    g_diag;
CATREngine      g_atr;
CSignalEngine   g_signal;
CGridEngine     g_grid;
CStateMachine   g_state;
CRiskManager    g_risk;
CBasketManager  g_basket;
CTradeManager   g_trade;
CRegimeGate     g_regime;
CStructureGate  g_structure;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_logger.Init("AAG", InpTesterVerbose);
   g_logger.LogInfo("Init v1.08 symbol=" + _Symbol + " tf=" + EnumToString(_Period));

   g_diag.SetLogger(g_logger);
   g_diag.Init(_Symbol, InpMagicNumber, InpDiagnosticsEnabled,
               InpDiagnosticsCSV, InpDiagnosticsFilePrefix);

   g_risk.SetLogger(g_logger);
   g_risk.Init(_Symbol);

   g_regime.SetLogger(g_logger);
   g_regime.Init(_Symbol, _Period);

   g_structure.SetLogger(g_logger);
   g_structure.Init(_Symbol, _Period);

   g_atr.SetLogger(g_logger);
   if(!g_atr.Init(_Symbol, _Period, InpATRPeriod, InpEMAPeriod, InpADXPeriod))
     {
      g_logger.LogError("ATREngine init failed");
      return INIT_FAILED;
     }

   g_signal.SetLogger(g_logger);
   if(!g_signal.Init(_Symbol, _Period, InpEntryFilter,
                     InpBBPeriod, InpBBDeviation,
                     InpRSIPeriod, InpRSIBuyMax, InpRSISellMin,
                     InpHTFTimeframe, InpHTFEMAPeriod, InpHTFEMAToleranceMult,
                     InpEMADistanceMult))
     {
      g_logger.LogError("SignalEngine init failed");
      return INIT_FAILED;
     }

   g_grid.SetLogger(g_logger);
   g_grid.Init(_Symbol);

   g_state.SetLogger(g_logger);

   g_basket.SetLogger(g_logger);
   g_basket.SetDiagnostics(g_diag);
   if(!g_basket.Init(_Symbol, InpMagicNumber, InpSlippagePoints))
      return INIT_FAILED;

   g_trade.SetLogger(g_logger);
   g_trade.SetDiagnostics(g_diag);
   if(!g_trade.Init(_Symbol, InpMagicNumber, InpSlippagePoints))
      return INIT_FAILED;

   if(g_basket.Recover(g_state, g_grid, g_atr))
      g_logger.LogInfo("Basket state recovered on init");
   else
      g_state.SetIdle();

   if(InpDiagnosticsEnabled)
      g_logger.LogInfo("Diagnostics E0 enabled — CSV prefix=" + InpDiagnosticsFilePrefix);

   if(InpEntryFilter != ENTRY_FILTER_NONE)
      g_logger.LogInfo("Entry filter E2 active — mode=" + IntegerToString((int)InpEntryFilter));

   if(InpBasketTrailEnabled || InpMRExitEnabled || InpBasketTPAdaptive || InpTimeStopEnabled)
      g_logger.LogInfo("Basket management E5 active");

   if(InpBasketDDCapEnabled || InpMAEExitEnabled || InpAdaptiveDepthEnabled || InpScaledLotsEnabled)
      g_logger.LogInfo("Grid & risk E4 active");

   if(InpRegimeATRPauseEnabled || InpRegimeADXSlopeEnabled || InpRegimeATRPercentileEnabled ||
      InpRegimeChopOnlyEnabled || InpRegimeSeasonalSkipEnabled)
      g_logger.LogInfo("Regime gates E3 active");

   if(g_structure.IsActive())
      g_logger.LogInfo("Structure filters E6 active");

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   g_diag.Flush();
   g_signal.Deinit();
   g_atr.Deinit();
   g_logger.LogInfo("Deinit reason=" + IntegerToString(reason));
  }

//+------------------------------------------------------------------+
//| Trade transaction — EDGE-001 close tagging                       |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   g_diag.OnTradeTransaction(trans);
  }

//+------------------------------------------------------------------+
//| Process grid level additions (every tick)                        |
//+------------------------------------------------------------------+
void ProcessGridLevels()
  {
   const ENUM_GRID_STATE state = g_state.GetState();
   if(state != GRID_STATE_GRID_ACTIVE)
      return;

   const ENUM_TRADE_BIAS bias = g_basket.GetBias();
   if(bias == BIAS_NONE)
      return;

   int filled[];
   g_basket.GetFilledLevels(filled);
   const int open_count = g_basket.GetOpenCount();
   const int max_levels = MathMin(g_risk.GetEffectiveMaxLevels(g_atr, InpMaxGridLevels),
                                  InpMaxOpenTrades);
   const int next_level = g_grid.GetNextLevelIndex(open_count);

   if(open_count >= max_levels)
     {
      g_state.SetManaging();
      return;
     }

   if(!g_grid.IsPriceAtLevel(bias, next_level, filled))
      return;

   string reason = "";
   if(!g_risk.CanAddLevel(open_count, max_levels, InpMaxSpreadPips,
                          g_basket.GetFloatingPL(), reason))
     {
      g_risk.LogReject(reason);
      return;
     }

   g_trade.OpenGridLevel(bias, next_level, g_atr, g_risk, g_grid, g_basket, g_state);
  }

//+------------------------------------------------------------------+
//| Process signal and first entry (new closed bar only)             |
//+------------------------------------------------------------------+
void ProcessSignals()
  {
   if(!g_state.CanEvaluateSignal())
      return;

   if(!g_atr.Update())
      return;

   SignalResult sig = g_signal.Evaluate(g_atr, InpADXThreshold);
   g_logger.LogSignal(sig);

   if(sig.bias == BIAS_NONE)
     {
      if(g_state.GetState() == GRID_STATE_ARMED)
         g_state.SetIdle();
      return;
     }

   string regime_reason = "";
   if(!g_regime.AllowNewBasket(g_atr, regime_reason))
     {
      g_regime.LogBlock(regime_reason);
      return;
     }

   string struct_reason = "";
   if(!g_structure.AllowNewBasket(sig.bias, g_atr, struct_reason))
     {
      g_structure.LogBlock(struct_reason);
      return;
     }

   string reason = "";
   if(!g_risk.CanOpenNewBasket(g_state, InpMaxSpreadPips, InpEquityFloorPercent,
                               sig.bias, InpTradePermission, reason))
     {
      g_risk.LogReject(reason);
      return;
     }

   if(!g_risk.IsBiasAllowed(sig.bias, InpTradePermission))
     {
      g_risk.LogReject("direction_not_allowed");
      return;
     }

   if(g_state.GetState() == GRID_STATE_IDLE)
      g_state.SetArmed(sig.bias);

   if(g_state.GetState() == GRID_STATE_ARMED)
     {
      if(g_state.GetArmedBias() != sig.bias && g_state.GetArmedBias() != BIAS_NONE)
        {
         g_state.SetArmed(sig.bias);
        }
      g_trade.OpenFirstLevel(sig.bias, g_atr, g_risk, g_grid, g_basket, g_state,
                            g_structure.ResolveGridAnchor(
                               (sig.bias == BIAS_BUY) ?
                               SymbolInfoDouble(_Symbol, SYMBOL_ASK) :
                               SymbolInfoDouble(_Symbol, SYMBOL_BID)));
     }
  }

//+------------------------------------------------------------------+
//| Trade management every tick                                      |
//+------------------------------------------------------------------+
void ProcessTradeManagement()
  {
   g_state.UpdateCooldown();

   if(g_state.GetState() == GRID_STATE_EXITING)
     {
      if(!g_basket.HasOpenPositions())
        {
         g_basket.OnBasketClosed(g_state, InpCooldownMinutes);
         g_atr.ResetFrozenDistance();
         g_grid.Reset();
        }
      return;
     }

   if(g_state.IsBasketActive())
     {
      g_atr.Update();

      if(g_basket.CheckMAEExit(g_state, g_atr, InpMAEExitEnabled, InpMAEExitATRMult))
         return;

      if(g_basket.CheckBasketExits(g_state, g_atr,
                                   InpBasketTPEnabled, InpBasketTPMode,
                                   InpBasketTPMoney, InpBasketTPPercent,
                                   InpBasketTPAdaptive, InpAdaptiveTPPerLevelATR,
                                   InpBasketTrailEnabled, InpBasketTrailActivateMoney,
                                   InpBasketTrailLockPercent,
                                   InpMRExitEnabled, InpMRExitToleranceATR,
                                   InpTimeStopEnabled, InpTimeStopMinutes))
         return;

      g_basket.SyncAfterExternalClose(g_state, InpCooldownMinutes);

      if(g_state.GetState() == GRID_STATE_MANAGING ||
         g_state.GetState() == GRID_STATE_GRID_ACTIVE)
        {
         if(!g_basket.HasOpenPositions())
           {
            g_basket.OnBasketClosed(g_state, InpCooldownMinutes);
            g_atr.ResetFrozenDistance();
            g_grid.Reset();
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   ProcessTradeManagement();
   ProcessGridLevels();

   if(!g_bars.IsNewClosedBar(_Symbol, _Period))
      return;

   ProcessSignals();
  }
//+------------------------------------------------------------------+
