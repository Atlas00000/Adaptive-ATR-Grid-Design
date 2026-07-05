//+------------------------------------------------------------------+
//| RegimeGate.mqh — Phase E3 regime & volatility gates              |
//+------------------------------------------------------------------+
#ifndef AAG_REGIMEGATE_MQH
#define AAG_REGIMEGATE_MQH

#include "ATREngine.mqh"
#include "Logger.mqh"

class CRegimeGate
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   CLogger          *m_log;

   bool              IsSeasonalSkip() const
     {
      if(!InpRegimeSeasonalSkipEnabled)
         return false;

      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      const int start = MathMax(1, MathMin(12, InpRegimeSkipMonthStart));
      const int end = MathMax(1, MathMin(12, InpRegimeSkipMonthEnd));

      if(start <= end)
         return (dt.mon >= start && dt.mon <= end);

      return (dt.mon >= start || dt.mon <= end);
     }

   bool              IsATRPause(CATREngine &atr_engine) const
     {
      if(!InpRegimeATRPauseEnabled)
         return false;

      const int lookback = MathMax(2, InpRegimeATRPauseLookback);
      double atr[];
      if(!atr_engine.GetATRSeries(atr, lookback + 1))
         return false;

      double sum = 0.0;
      for(int i = 1; i <= lookback; i++)
         sum += atr[i];

      const double avg = sum / lookback;
      if(avg <= 0.0)
         return false;

      return atr[0] > avg * InpRegimeATRPauseMult;
     }

   bool              IsADXSlopeRising(CATREngine &atr_engine) const
     {
      if(!InpRegimeADXSlopeEnabled)
         return false;

      const int bars = MathMax(2, InpRegimeADXSlopeBars);
      double adx[];
      if(!atr_engine.GetADXSeries(adx, bars + 1))
         return false;

      for(int i = 0; i < bars; i++)
        {
         if(adx[i] <= adx[i + 1])
            return false;
        }
      return true;
     }

   bool              IsATRAbovePercentile(CATREngine &atr_engine) const
     {
      if(!InpRegimeATRPercentileEnabled)
         return false;

      const int lookback = MathMax(20, InpRegimeATRPercentileLookback);
      double atr[];
      if(!atr_engine.GetATRSeries(atr, lookback))
         return false;

      double sorted[];
      ArrayResize(sorted, lookback);
      ArrayCopy(sorted, atr);
      ArraySort(sorted);

      const int idx = (int)MathFloor((lookback - 1) * InpRegimeATRPercentileMax / 100.0);
      const double threshold = sorted[MathMax(0, MathMin(lookback - 1, idx))];
      return atr[0] > threshold;
     }

   int               CountEMACrosses(CATREngine &atr_engine, const int lookback) const
     {
      double ema[];
      if(!atr_engine.GetEMASeries(ema, lookback))
         return 0;

      int crosses = 0;
      for(int i = 0; i < lookback - 1; i++)
        {
         const double c1 = iClose(m_symbol, m_tf, 1 + i);
         const double c2 = iClose(m_symbol, m_tf, 2 + i);
         const double side1 = c1 - ema[i];
         const double side2 = c2 - ema[i + 1];
         if(side1 * side2 < 0.0)
            crosses++;
        }
      return crosses;
     }

   bool              PassesChopGate(CATREngine &atr_engine) const
     {
      if(!InpRegimeChopOnlyEnabled)
         return true;

      const int lookback = MathMax(5, InpRegimeChopLookback);
      const int crosses = CountEMACrosses(atr_engine, lookback);
      return crosses >= InpRegimeChopMinCrosses;
     }

public:
                     CRegimeGate() : m_symbol(""), m_tf(PERIOD_CURRENT), m_log(NULL) {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }
   void              Init(const string symbol, const ENUM_TIMEFRAMES tf)
     {
      m_symbol = symbol;
      m_tf = tf;
     }

   bool              AllowNewBasket(CATREngine &atr_engine, string &reason) const
     {
      reason = "";

      if(IsSeasonalSkip())
        {
         reason = "regime_seasonal_skip";
         return false;
        }

      if(IsATRPause(atr_engine))
        {
         reason = "regime_atr_pause";
         return false;
        }

      if(IsADXSlopeRising(atr_engine))
        {
         reason = "regime_adx_slope";
         return false;
        }

      if(IsATRAbovePercentile(atr_engine))
        {
         reason = "regime_atr_percentile";
         return false;
        }

      if(!PassesChopGate(atr_engine))
        {
         reason = "regime_chop_fail";
         return false;
        }

      return true;
     }

   void              LogBlock(const string reason) const
     {
      if(m_log != NULL)
         m_log.LogRiskReject(reason);
     }
  };

#endif // AAG_REGIMEGATE_MQH
