//+------------------------------------------------------------------+
//| ATREngine.mqh — indicator handles and frozen grid distance       |
//+------------------------------------------------------------------+
#ifndef AAG_ATRENGINE_MQH
#define AAG_ATRENGINE_MQH

#include "Logger.mqh"

class CATREngine
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   int               m_atr_handle;
   int               m_ema_handle;
   int               m_adx_handle;
   double            m_atr;
   double            m_ema;
   double            m_adx;
   double            m_frozen_distance;
   bool              m_distance_frozen;
   CLogger          *m_log;

   bool              CopyValue(const int handle, const int buffer, double &value)
     {
      double buf[];
      ArraySetAsSeries(buf, true);
      if(CopyBuffer(handle, buffer, 1, 1, buf) != 1)
         return false;
      value = buf[0];
      return MathIsValidNumber(value);
     }

public:
                     CATREngine() :
                     m_symbol(""),
                     m_tf(PERIOD_CURRENT),
                     m_atr_handle(INVALID_HANDLE),
                     m_ema_handle(INVALID_HANDLE),
                     m_adx_handle(INVALID_HANDLE),
                     m_atr(0.0),
                     m_ema(0.0),
                     m_adx(0.0),
                     m_frozen_distance(0.0),
                     m_distance_frozen(false),
                     m_log(NULL)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   bool              Init(const string symbol, const ENUM_TIMEFRAMES tf,
                        const int atr_period, const int ema_period, const int adx_period)
     {
      m_symbol = symbol;
      m_tf = tf;
      m_atr_handle = iATR(m_symbol, m_tf, atr_period);
      m_ema_handle = iMA(m_symbol, m_tf, ema_period, 0, MODE_EMA, PRICE_CLOSE);
      m_adx_handle = iADX(m_symbol, m_tf, adx_period);

      if(m_atr_handle == INVALID_HANDLE || m_ema_handle == INVALID_HANDLE ||
         m_adx_handle == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.LogError("Failed to create indicator handles");
         return false;
        }
      return true;
     }

   void              Deinit()
     {
      if(m_atr_handle != INVALID_HANDLE) IndicatorRelease(m_atr_handle);
      if(m_ema_handle != INVALID_HANDLE) IndicatorRelease(m_ema_handle);
      if(m_adx_handle != INVALID_HANDLE) IndicatorRelease(m_adx_handle);
      m_atr_handle = INVALID_HANDLE;
      m_ema_handle = INVALID_HANDLE;
      m_adx_handle = INVALID_HANDLE;
     }

   bool              Update()
     {
      if(!CopyValue(m_atr_handle, 0, m_atr))
        {
         if(m_log != NULL)
            m_log.LogError("ATR buffer copy failed");
         return false;
        }
      if(!CopyValue(m_ema_handle, 0, m_ema))
        {
         if(m_log != NULL)
            m_log.LogError("EMA buffer copy failed");
         return false;
        }
      if(!CopyValue(m_adx_handle, 0, m_adx))
        {
         if(m_log != NULL)
            m_log.LogError("ADX buffer copy failed");
         return false;
        }
      return true;
     }

   double            GetATR() const { return m_atr; }
   double            GetEMA() const { return m_ema; }
   double            GetADX() const { return m_adx; }

   double            CalcGridDistance(const double multiplier) const
     {
      return m_atr * multiplier;
     }

   double            GetFrozenDistance() const { return m_frozen_distance; }
   bool              IsDistanceFrozen() const { return m_distance_frozen; }

   void              FreezeDistance(const double multiplier)
     {
      m_frozen_distance = CalcGridDistance(multiplier);
      m_distance_frozen = true;
      if(m_log != NULL)
         m_log.LogGrid("Frozen grid distance=" + DoubleToString(m_frozen_distance, _Digits));
     }

   void              RestoreFrozenDistance(const double distance)
     {
      m_frozen_distance = distance;
      m_distance_frozen = (distance > 0.0);
     }

   void              ResetFrozenDistance()
     {
      m_frozen_distance = 0.0;
      m_distance_frozen = false;
     }

   bool              GetEMASeries(double &ema[], const int count) const
     {
      ArrayResize(ema, count);
      ArraySetAsSeries(ema, true);
      return CopyBuffer(m_ema_handle, 0, 1, count, ema) == count;
     }

   bool              GetATRSeries(double &atr[], const int count) const
     {
      ArrayResize(atr, count);
      ArraySetAsSeries(atr, true);
      return CopyBuffer(m_atr_handle, 0, 1, count, atr) == count;
     }

   bool              GetADXSeries(double &adx[], const int count) const
     {
      ArrayResize(adx, count);
      ArraySetAsSeries(adx, true);
      return CopyBuffer(m_adx_handle, 0, 1, count, adx) == count;
     }

   double            CalcSLDistance(const ENUM_SLTP_MODE mode,
                                    const double sl_atr_mult,
                                    const double sl_fixed_pips) const
     {
      if(mode == SLTP_ATR)
         return m_distance_frozen ? m_frozen_distance * (sl_atr_mult / InpATRMultiplier) :
                m_atr * sl_atr_mult;
      return AAG_PipsToPoints(m_symbol, sl_fixed_pips);
     }

   double            CalcTPDistance(const ENUM_SLTP_MODE mode,
                                    const double tp_atr_mult,
                                    const double tp_fixed_pips) const
     {
      if(mode == SLTP_ATR)
         return m_distance_frozen ? m_frozen_distance * (tp_atr_mult / InpATRMultiplier) :
                m_atr * tp_atr_mult;
      return AAG_PipsToPoints(m_symbol, tp_fixed_pips);
     }
  };

#endif // AAG_ATRENGINE_MQH
