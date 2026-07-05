//+------------------------------------------------------------------+
//| RiskManager.mqh — spread, cooldown, limits, sizing, session      |
//+------------------------------------------------------------------+
#ifndef AAG_RISKMANAGER_MQH
#define AAG_RISKMANAGER_MQH

#include "ATREngine.mqh"
#include "StateMachine.mqh"

class CRiskManager
  {
private:
   string            m_symbol;
   CLogger          *m_log;

   bool              IsHourInList(const int hour, const string list) const
     {
      if(list == "")
         return false;
      string parts[];
      const int n = StringSplit(list, ',', parts);
      for(int i = 0; i < n; i++)
        {
         string part = parts[i];
         StringTrimLeft(part);
         StringTrimRight(part);
         if((int)StringToInteger(part) == hour)
            return true;
        }
      return false;
     }

   bool              IsWeekdayAllowed(const int day_of_week) const
     {
      switch(day_of_week)
        {
         case 0: return InpTradeSun;
         case 1: return InpTradeMon;
         case 2: return InpTradeTue;
         case 3: return InpTradeWed;
         case 4: return InpTradeThu;
         case 5: return InpTradeFri;
         case 6: return InpTradeSat;
        }
      return true;
     }

   bool              CheckSession(string &reason) const
     {
      if(!InpTimeFilterEnabled && !InpDayFilterEnabled && !InpUseHourBlacklist)
         return true;

      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);

      if(InpDayFilterEnabled && !IsWeekdayAllowed(dt.day_of_week))
        {
         reason = "day_blocked dow=" + IntegerToString(dt.day_of_week);
         return false;
        }

      if(InpUseHourBlacklist && IsHourInList(dt.hour, InpBlockedHours))
        {
         reason = "hour_blacklist=" + IntegerToString(dt.hour);
         return false;
        }

      if(InpTimeFilterEnabled)
        {
         const int start = MathMax(0, MathMin(23, InpTradeHourStart));
         const int end = MathMax(0, MathMin(23, InpTradeHourEnd));
         if(start <= end)
           {
            if(dt.hour < start || dt.hour > end)
              {
               reason = "outside_window hour=" + IntegerToString(dt.hour) +
                        " allowed=" + IntegerToString(start) + "-" + IntegerToString(end);
               return false;
              }
           }
         else
           {
            if(dt.hour < start && dt.hour > end)
              {
               reason = "outside_window hour=" + IntegerToString(dt.hour);
               return false;
              }
           }
        }

      return true;
     }

   bool              CheckSpread(const double max_spread_pips, string &reason) const
     {
      const double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      const double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      const double spread_points = ask - bid;
      const double spread_pips = AAG_PointsToPips(m_symbol, spread_points);
      if(spread_pips > max_spread_pips)
        {
         reason = "spread=" + DoubleToString(spread_pips, 1) + " pips";
         return false;
        }
      return true;
     }

   bool              CheckEquityFloor(const double floor_percent, string &reason) const
     {
      const double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(balance <= 0.0)
         return true;
      const double pct = (equity / balance) * 100.0;
      if(pct < floor_percent)
        {
         reason = "equity_floor=" + DoubleToString(pct, 1) + "%";
         return false;
        }
      return true;
     }

public:
                     CRiskManager() : m_symbol(""), m_log(NULL) {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }
   void              Init(const string symbol) { m_symbol = symbol; }

   bool              IsBiasAllowed(const ENUM_TRADE_BIAS bias,
                                   const ENUM_TRADE_PERMISSION permission) const
     {
      if(bias == BIAS_BUY && permission == TRADE_SELL_ONLY)
         return false;
      if(bias == BIAS_SELL && permission == TRADE_BUY_ONLY)
         return false;
      return true;
     }

   bool              CanOpenNewBasket(CStateMachine &state,
                                      const double max_spread_pips,
                                      const double equity_floor_percent,
                                      const ENUM_TRADE_BIAS bias,
                                      const ENUM_TRADE_PERMISSION permission,
                                      string &reason) const
     {
      if(state.IsCooldownActive())
        {
         reason = "cooldown_active";
         return false;
        }
      if(state.GetState() == GRID_STATE_COOLDOWN)
        {
         reason = "cooldown_active";
         return false;
        }
      if(!IsBiasAllowed(bias, permission))
        {
         reason = "direction_not_allowed";
         return false;
        }
      string session_reason = "";
      if(!CheckSession(session_reason))
        {
         reason = session_reason;
         return false;
        }
      string spread_reason = "";
      if(!CheckSpread(max_spread_pips, spread_reason))
        {
         reason = spread_reason;
         return false;
        }
      string equity_reason = "";
      if(!CheckEquityFloor(equity_floor_percent, equity_reason))
        {
         reason = equity_reason;
         return false;
        }
      return true;
     }

   bool              CanAddLevel(const int open_count, const int max_levels,
                               const double max_spread_pips,
                               const double basket_floating_pl,
                               string &reason) const
     {
      if(open_count >= max_levels)
        {
         reason = "max_levels_reached";
         return false;
        }
      string session_reason = "";
      if(!CheckSession(session_reason))
        {
         reason = session_reason;
         return false;
        }
      string spread_reason = "";
      if(!CheckSpread(max_spread_pips, spread_reason))
        {
         reason = spread_reason;
         return false;
        }
      if(InpBasketDDCapEnabled && basket_floating_pl < 0.0)
        {
         const double equity = AccountInfoDouble(ACCOUNT_EQUITY);
         const double cap = equity * InpBasketDDCapPercent / 100.0;
         if(cap > 0.0 && -basket_floating_pl >= cap)
           {
            reason = "basket_dd_cap";
            return false;
           }
        }
      return true;
     }

   int               GetEffectiveMaxLevels(CATREngine &atr_engine,
                                           const int default_max) const
     {
      if(!InpAdaptiveDepthEnabled)
         return default_max;
      if(atr_engine.GetADX() >= InpAdaptiveDepthADXThreshold)
         return MathMax(1, MathMin(default_max, InpAdaptiveDepthMaxTight));
      return default_max;
     }

   bool              PreTradeCheck(const double max_spread_pips, string &reason) const
     {
      string session_reason = "";
      if(!CheckSession(session_reason))
        {
         reason = session_reason;
         return false;
        }
      string spread_reason = "";
      if(!CheckSpread(max_spread_pips, spread_reason))
        {
         reason = spread_reason;
         return false;
        }
      string equity_reason = "";
      if(!CheckEquityFloor(InpEquityFloorPercent, equity_reason))
        {
         reason = equity_reason;
         return false;
        }
      return true;
     }

   double            CalcLotSize(CATREngine &atr_engine,
                                 const ENUM_SIZING_MODE sizing_mode,
                                 const double fixed_lot,
                                 const double risk_percent,
                                 const double min_lot,
                                 const double max_lot,
                                 const ENUM_SLTP_MODE sltp_mode,
                                 const double sl_atr_mult,
                                 const double sl_fixed_pips,
                                 const int level_index = 0) const
     {
      double lot = 0.0;
      if(sizing_mode == SIZING_FIXED_LOT)
         lot = fixed_lot;
      else
        {
         const double sl_distance = atr_engine.CalcSLDistance(sltp_mode, sl_atr_mult, sl_fixed_pips);
         if(sl_distance <= 0.0)
            lot = min_lot;
         else
           {
            const double tick_size = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
            const double tick_value = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
            if(tick_size <= 0.0 || tick_value <= 0.0)
               lot = min_lot;
            else
              {
               const double risk_money = AccountInfoDouble(ACCOUNT_EQUITY) * risk_percent / 100.0;
               const double loss_per_lot = (sl_distance / tick_size) * tick_value;
               lot = (loss_per_lot <= 0.0) ? min_lot : risk_money / loss_per_lot;
              }
           }
        }

      if(InpScaledLotsEnabled && level_index > 0 && InpScaledLotFactor > 0.0)
         lot *= MathPow(InpScaledLotFactor, level_index);

      return AAG_NormalizeLot(m_symbol, lot, min_lot, max_lot);
     }

   void              LogReject(const string reason) const
     {
      if(m_log != NULL)
         m_log.LogRiskReject(reason);
     }
  };

#endif // AAG_RISKMANAGER_MQH
