//+------------------------------------------------------------------+
//| SignalEngine.mqh — EMA slope + ADX entry gate + E2 filters       |
//+------------------------------------------------------------------+
#ifndef AAG_SIGNALENGINE_MQH
#define AAG_SIGNALENGINE_MQH

#include "ATREngine.mqh"

class CSignalEngine
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   CLogger          *m_log;

   ENUM_ENTRY_FILTER m_entry_filter;
   int               m_bb_period;
   double            m_bb_deviation;
   int               m_rsi_period;
   double            m_rsi_buy_max;
   double            m_rsi_sell_min;
   ENUM_TIMEFRAMES   m_htf_tf;
   int               m_htf_ema_period;
   double            m_htf_ema_tolerance_mult;
   double            m_ema_distance_mult;

   int               m_bb_handle;
   int               m_rsi_handle;
   int               m_htf_ema_handle;

   bool              NeedsBB() const
     {
      return m_entry_filter == ENTRY_FILTER_BB_REJECT ||
             m_entry_filter == ENTRY_FILTER_BB_RSI;
     }

   bool              NeedsRSI() const
     {
      return m_entry_filter == ENTRY_FILTER_RSI ||
             m_entry_filter == ENTRY_FILTER_BB_RSI;
     }

   bool              NeedsHTFEMA() const
     {
      return m_entry_filter == ENTRY_FILTER_HTF_EMA;
     }

   bool              CopyBand(const int buffer, const int start, const int count,
                              double &values[]) const
     {
      ArraySetAsSeries(values, true);
      return CopyBuffer(m_bb_handle, buffer, start, count, values) == count;
     }

   bool              IsEMAFlat(CATREngine &atr_engine) const
     {
      double ema[];
      if(!atr_engine.GetEMASeries(ema, 5))
         return false;
      const double slope = MathAbs(ema[0] - ema[4]);
      return slope < atr_engine.GetATR() * 0.10;
     }

   bool              IsEMABullish(CATREngine &atr_engine) const
     {
      double ema[];
      if(!atr_engine.GetEMASeries(ema, 3))
         return false;
      return ema[0] > ema[1] && ema[1] > ema[2];
     }

   bool              IsEMABearish(CATREngine &atr_engine) const
     {
      double ema[];
      if(!atr_engine.GetEMASeries(ema, 3))
         return false;
      return ema[0] < ema[1] && ema[1] < ema[2];
     }

   SignalResult      EvaluateBase(CATREngine &atr_engine, const int adx_threshold) const
     {
      SignalResult result;
      result.bias = BIAS_NONE;
      result.ema_flat = false;
      result.ema_bullish = false;
      result.ema_bearish = false;
      result.adx = atr_engine.GetADX();
      result.reason = "no_signal";

      if(result.adx >= adx_threshold)
        {
         result.reason = "adx_too_high";
         return result;
        }

      result.ema_flat = IsEMAFlat(atr_engine);
      result.ema_bullish = IsEMABullish(atr_engine);
      result.ema_bearish = IsEMABearish(atr_engine);

      if(result.ema_bullish)
        {
         result.bias = BIAS_BUY;
         result.reason = "ema_bullish";
         return result;
        }

      if(result.ema_bearish)
        {
         result.bias = BIAS_SELL;
         result.reason = "ema_bearish";
         return result;
        }

      if(result.ema_flat)
        {
         const double close_price = iClose(m_symbol, m_tf, 1);
         if(close_price >= atr_engine.GetEMA())
           {
            result.bias = BIAS_BUY;
            result.reason = "ema_flat_above";
           }
         else
           {
            result.bias = BIAS_SELL;
            result.reason = "ema_flat_below";
           }
        }

      return result;
     }

   // Wick touch lower/upper band then close back inside (enhance, not require full close outside)
   bool              PassBBReject(const ENUM_TRADE_BIAS bias) const
     {
      double upper[], lower[], middle[];
      if(!CopyBand(1, 1, 2, upper) || !CopyBand(2, 1, 2, lower) ||
         !CopyBand(0, 1, 2, middle))
         return false;

      const double close1 = iClose(m_symbol, m_tf, 1);
      const double low2 = iLow(m_symbol, m_tf, 2);
      const double high2 = iHigh(m_symbol, m_tf, 2);

      if(bias == BIAS_BUY)
         return low2 <= lower[1] && close1 > lower[0] && close1 <= middle[0];

      if(bias == BIAS_SELL)
         return high2 >= upper[1] && close1 < upper[0] && close1 >= middle[0];

      return false;
     }

   // Favour rotation: buy when not overbought, sell when not oversold
   bool              PassRSI(const ENUM_TRADE_BIAS bias) const
     {
      double rsi[];
      ArraySetAsSeries(rsi, true);
      if(CopyBuffer(m_rsi_handle, 0, 1, 1, rsi) != 1)
         return false;

      if(bias == BIAS_BUY)
         return rsi[0] <= m_rsi_buy_max;

      if(bias == BIAS_SELL)
         return rsi[0] >= m_rsi_sell_min;

      return false;
     }

   // HTF trend alignment with ATR tolerance band (soft, not strict cross)
   bool              PassHTFEMA(const ENUM_TRADE_BIAS bias, const double atr) const
     {
      double htf_ema[];
      ArraySetAsSeries(htf_ema, true);
      if(CopyBuffer(m_htf_ema_handle, 0, 1, 1, htf_ema) != 1)
         return false;

      const double htf_close = iClose(m_symbol, m_htf_tf, 1);
      const double tolerance = atr * m_htf_ema_tolerance_mult;

      if(bias == BIAS_BUY)
         return htf_close > htf_ema[0] - tolerance;

      if(bias == BIAS_SELL)
         return htf_close < htf_ema[0] + tolerance;

      return false;
     }

   // Mild stretch from EMA — avoid entries glued to the mean
   bool              PassEMADistance(CATREngine &atr_engine, const ENUM_TRADE_BIAS bias) const
     {
      const double close1 = iClose(m_symbol, m_tf, 1);
      const double ema = atr_engine.GetEMA();
      const double min_dist = atr_engine.GetATR() * m_ema_distance_mult;

      if(bias == BIAS_BUY)
         return close1 <= ema - min_dist;

      if(bias == BIAS_SELL)
         return close1 >= ema + min_dist;

      return false;
     }

   bool              PassEntryFilter(CATREngine &atr_engine, const ENUM_TRADE_BIAS bias,
                                     string &fail_reason) const
     {
      fail_reason = "";

      switch(m_entry_filter)
        {
         case ENTRY_FILTER_BB_REJECT:
            if(!PassBBReject(bias))
              {
               fail_reason = "bb_reject_fail";
               return false;
              }
            return true;

         case ENTRY_FILTER_RSI:
            if(!PassRSI(bias))
              {
               fail_reason = "rsi_fail";
               return false;
              }
            return true;

         case ENTRY_FILTER_BB_RSI:
            if(!PassBBReject(bias))
              {
               fail_reason = "bb_reject_fail";
               return false;
              }
            if(!PassRSI(bias))
              {
               fail_reason = "rsi_fail";
               return false;
              }
            return true;

         case ENTRY_FILTER_HTF_EMA:
            if(!PassHTFEMA(bias, atr_engine.GetATR()))
              {
               fail_reason = "htf_ema_fail";
               return false;
              }
            return true;

         case ENTRY_FILTER_EMA_DISTANCE:
            if(!PassEMADistance(atr_engine, bias))
              {
               fail_reason = "ema_distance_fail";
               return false;
              }
            return true;

         default:
            return true;
        }
     }

public:
                     CSignalEngine() :
                     m_symbol(""),
                     m_tf(PERIOD_CURRENT),
                     m_log(NULL),
                     m_entry_filter(ENTRY_FILTER_NONE),
                     m_bb_period(20),
                     m_bb_deviation(2.0),
                     m_rsi_period(14),
                     m_rsi_buy_max(52.0),
                     m_rsi_sell_min(48.0),
                     m_htf_tf(PERIOD_M15),
                     m_htf_ema_period(50),
                     m_htf_ema_tolerance_mult(0.20),
                     m_ema_distance_mult(0.15),
                     m_bb_handle(INVALID_HANDLE),
                     m_rsi_handle(INVALID_HANDLE),
                     m_htf_ema_handle(INVALID_HANDLE)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   bool              Init(const string symbol, const ENUM_TIMEFRAMES tf,
                          const ENUM_ENTRY_FILTER entry_filter,
                          const int bb_period, const double bb_deviation,
                          const int rsi_period, const double rsi_buy_max,
                          const double rsi_sell_min,
                          const ENUM_TIMEFRAMES htf_tf, const int htf_ema_period,
                          const double htf_ema_tolerance_mult,
                          const double ema_distance_mult)
     {
      m_symbol = symbol;
      m_tf = tf;
      m_entry_filter = entry_filter;
      m_bb_period = bb_period;
      m_bb_deviation = bb_deviation;
      m_rsi_period = rsi_period;
      m_rsi_buy_max = rsi_buy_max;
      m_rsi_sell_min = rsi_sell_min;
      m_htf_tf = htf_tf;
      m_htf_ema_period = htf_ema_period;
      m_htf_ema_tolerance_mult = htf_ema_tolerance_mult;
      m_ema_distance_mult = ema_distance_mult;

      if(NeedsBB())
        {
         m_bb_handle = iBands(m_symbol, m_tf, m_bb_period, 0, m_bb_deviation, PRICE_CLOSE);
         if(m_bb_handle == INVALID_HANDLE)
           {
            if(m_log != NULL)
               m_log.LogError("Failed to create Bollinger Bands handle");
            return false;
           }
        }

      if(NeedsRSI())
        {
         m_rsi_handle = iRSI(m_symbol, m_tf, m_rsi_period, PRICE_CLOSE);
         if(m_rsi_handle == INVALID_HANDLE)
           {
            if(m_log != NULL)
               m_log.LogError("Failed to create RSI handle");
            return false;
           }
        }

      if(NeedsHTFEMA())
        {
         m_htf_ema_handle = iMA(m_symbol, m_htf_tf, m_htf_ema_period, 0, MODE_EMA, PRICE_CLOSE);
         if(m_htf_ema_handle == INVALID_HANDLE)
           {
            if(m_log != NULL)
               m_log.LogError("Failed to create HTF EMA handle");
            return false;
           }
        }

      return true;
     }

   void              Deinit()
     {
      if(m_bb_handle != INVALID_HANDLE)
        {
         IndicatorRelease(m_bb_handle);
         m_bb_handle = INVALID_HANDLE;
        }
      if(m_rsi_handle != INVALID_HANDLE)
        {
         IndicatorRelease(m_rsi_handle);
         m_rsi_handle = INVALID_HANDLE;
        }
      if(m_htf_ema_handle != INVALID_HANDLE)
        {
         IndicatorRelease(m_htf_ema_handle);
         m_htf_ema_handle = INVALID_HANDLE;
        }
     }

   SignalResult      Evaluate(CATREngine &atr_engine, const int adx_threshold) const
     {
      SignalResult result = EvaluateBase(atr_engine, adx_threshold);

      if(result.bias == BIAS_NONE || m_entry_filter == ENTRY_FILTER_NONE)
         return result;

      string fail_reason = "";
      if(!PassEntryFilter(atr_engine, result.bias, fail_reason))
        {
         result.bias = BIAS_NONE;
         result.reason = fail_reason;
        }

      return result;
     }
  };

#endif // AAG_SIGNALENGINE_MQH
