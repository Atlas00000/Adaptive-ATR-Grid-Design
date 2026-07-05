//+------------------------------------------------------------------+
//| StructureGate.mqh — Phase E6 structure & liquidity filters       |
//+------------------------------------------------------------------+
#ifndef AAG_STRUCTUREGATE_MQH
#define AAG_STRUCTUREGATE_MQH

#include "ATREngine.mqh"
#include "Logger.mqh"

class CStructureGate
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   CLogger          *m_log;

   bool              GetPriorDayHL(double &high, double &low) const
     {
      high = iHigh(m_symbol, PERIOD_D1, 1);
      low = iLow(m_symbol, PERIOD_D1, 1);
      return high > 0.0 && low > 0.0 && high >= low;
     }

   datetime          SessionStartToday() const
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      dt.hour = InpTradeHourStart;
      dt.min = 0;
      dt.sec = 0;
      return StructToTime(dt);
     }

   bool              GetSessionHL(double &high, double &low) const
     {
      const datetime start = SessionStartToday();
      const int start_bar = iBarShift(m_symbol, m_tf, start, true);
      if(start_bar < 1)
         return false;

      const int high_idx = iHighest(m_symbol, m_tf, MODE_HIGH, start_bar, 1);
      const int low_idx = iLowest(m_symbol, m_tf, MODE_LOW, start_bar, 1);
      if(high_idx < 0 || low_idx < 0)
         return false;

      high = iHigh(m_symbol, m_tf, high_idx);
      low = iLow(m_symbol, m_tf, low_idx);
      return high >= low;
     }

   bool              PassPDHLBoundary(const ENUM_TRADE_BIAS bias, const double close_price,
                                      const double atr) const
     {
      if(!InpStructPDHLEnabled)
         return true;

      double pdh, pdl;
      if(!GetPriorDayHL(pdh, pdl))
         return false;

      const double tol = atr * InpStructPDHLToleranceATR;

      if(bias == BIAS_BUY)
         return close_price <= pdl + tol;

      if(bias == BIAS_SELL)
         return close_price >= pdh - tol;

      return false;
     }

   bool              PassSessionHLBoundary(const ENUM_TRADE_BIAS bias, const double close_price,
                                           const double atr) const
     {
      if(!InpStructSessionHLEnabled)
         return true;

      double sh, sl;
      if(!GetSessionHL(sh, sl))
         return false;

      const double tol = atr * InpStructSessionHLToleranceATR;

      if(bias == BIAS_BUY)
         return close_price <= sl + tol;

      if(bias == BIAS_SELL)
         return close_price >= sh - tol;

      return false;
     }

   bool              PassLiqSweep(const ENUM_TRADE_BIAS bias, const double atr) const
     {
      if(!InpStructLiqSweepEnabled)
         return true;

      double level_high, level_low;
      if(InpStructLiqSweepUsePD)
        {
         if(!GetPriorDayHL(level_high, level_low))
            return false;
        }
      else
        {
         if(!GetSessionHL(level_high, level_low))
            return false;
        }

      const double sweep = atr * InpStructLiqSweepMinATR;
      const double close1 = iClose(m_symbol, m_tf, 1);
      const double high2 = iHigh(m_symbol, m_tf, 2);
      const double low2 = iLow(m_symbol, m_tf, 2);

      if(bias == BIAS_BUY)
        {
         const double level = level_low;
         return low2 < level - sweep && close1 > level;
        }

      if(bias == BIAS_SELL)
        {
         const double level = level_high;
         return high2 > level + sweep && close1 < level;
        }

      return false;
     }

public:
                     CStructureGate() : m_symbol(""), m_tf(PERIOD_CURRENT), m_log(NULL) {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   void              Init(const string symbol, const ENUM_TIMEFRAMES tf)
     {
      m_symbol = symbol;
      m_tf = tf;
     }

   bool              IsActive() const
     {
      return InpStructPDHLEnabled || InpStructSessionHLEnabled ||
             InpStructLiqSweepEnabled || InpStructRangeMidAnchorEnabled;
     }

   bool              AllowNewBasket(const ENUM_TRADE_BIAS bias, CATREngine &atr_engine,
                                    string &reason) const
     {
      reason = "";
      if(bias == BIAS_NONE)
         return false;

      const double close_price = iClose(m_symbol, m_tf, 1);
      const double atr = atr_engine.GetATR();
      if(atr <= 0.0)
         return false;

      if(!PassPDHLBoundary(bias, close_price, atr))
        {
         reason = "struct_pdh_l_fail";
         return false;
        }

      if(!PassSessionHLBoundary(bias, close_price, atr))
        {
         reason = "struct_session_hl_fail";
         return false;
        }

      if(!PassLiqSweep(bias, atr))
        {
         reason = "struct_liq_sweep_fail";
         return false;
        }

      return true;
     }

   double            ResolveGridAnchor(const double entry_price) const
     {
      if(!InpStructRangeMidAnchorEnabled)
         return entry_price;

      double high, low;
      if(InpStructRangeMidSource == 1)
        {
         if(!GetPriorDayHL(high, low))
            return entry_price;
        }
      else
        {
         if(!GetSessionHL(high, low))
            return entry_price;
        }

      return NormalizeDouble((high + low) / 2.0, _Digits);
     }

   void              LogBlock(const string reason) const
     {
      if(m_log != NULL)
         m_log.LogRiskReject(reason);
     }
  };

#endif // AAG_STRUCTUREGATE_MQH
