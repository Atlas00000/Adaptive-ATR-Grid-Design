//+------------------------------------------------------------------+
//| Logger.mqh — structured logging                                  |
//+------------------------------------------------------------------+
#ifndef AAG_LOGGER_MQH
#define AAG_LOGGER_MQH

#include "Utils.mqh"

class CLogger
  {
private:
   string            m_prefix;
   bool              m_tester_verbose;

public:
                     CLogger() : m_prefix("AAG"), m_tester_verbose(true) {}

   void              Init(const string ea_name, const bool tester_verbose)
     {
      m_prefix = ea_name;
      m_tester_verbose = tester_verbose;
     }

   void              LogDebug(const string msg) const
     {
      if(!m_tester_verbose)
         return;
      Print(m_prefix, " [DEBUG] ", msg);
     }

   void              LogInfo(const string msg) const
     {
      Print(m_prefix, " [INFO] ", msg);
     }

   void              LogError(const string msg) const
     {
      Print(m_prefix, " [ERROR] ", msg);
     }

   void              LogSignal(const SignalResult &sig) const
     {
      if(!m_tester_verbose)
         return;
      Print(m_prefix, " [SIGNAL] bias=", AAG_BiasToString(sig.bias),
            " adx=", DoubleToString(sig.adx, 2),
            " flat=", sig.ema_flat,
            " bull=", sig.ema_bullish,
            " bear=", sig.ema_bearish,
            " reason=", sig.reason);
     }

   void              LogGrid(const string msg) const
     {
      if(!m_tester_verbose)
         return;
      Print(m_prefix, " [GRID] ", msg);
     }

   void              LogBasket(const string msg) const
     {
      Print(m_prefix, " [BASKET] ", msg);
     }

   void              LogRiskReject(const string reason) const
     {
      Print(m_prefix, " [RISK] REJECT: ", reason);
     }

   void              LogTradeRetcode(const uint retcode, const string action) const
     {
      Print(m_prefix, " [TRADE] ", action, " retcode=", retcode,
            " (", GetRetcodeDescription(retcode), ")");
     }

   static string     GetRetcodeDescription(const uint retcode)
     {
      switch(retcode)
        {
         case TRADE_RETCODE_REQUOTE:           return "REQUOTE";
         case TRADE_RETCODE_REJECT:            return "REJECT";
         case TRADE_RETCODE_CANCEL:            return "CANCEL";
         case TRADE_RETCODE_PLACED:            return "PLACED";
         case TRADE_RETCODE_DONE:              return "DONE";
         case TRADE_RETCODE_DONE_PARTIAL:      return "DONE_PARTIAL";
         case TRADE_RETCODE_ERROR:             return "ERROR";
         case TRADE_RETCODE_TIMEOUT:           return "TIMEOUT";
         case TRADE_RETCODE_INVALID:           return "INVALID";
         case TRADE_RETCODE_INVALID_VOLUME:    return "INVALID_VOLUME";
         case TRADE_RETCODE_INVALID_PRICE:     return "INVALID_PRICE";
         case TRADE_RETCODE_INVALID_STOPS:     return "INVALID_STOPS";
         case TRADE_RETCODE_TRADE_DISABLED:    return "TRADE_DISABLED";
         case TRADE_RETCODE_MARKET_CLOSED:     return "MARKET_CLOSED";
         case TRADE_RETCODE_NO_MONEY:          return "NO_MONEY";
         case TRADE_RETCODE_PRICE_CHANGED:     return "PRICE_CHANGED";
         case TRADE_RETCODE_PRICE_OFF:         return "PRICE_OFF";
         case TRADE_RETCODE_INVALID_EXPIRATION: return "INVALID_EXPIRATION";
         case TRADE_RETCODE_ORDER_CHANGED:     return "ORDER_CHANGED";
         case TRADE_RETCODE_TOO_MANY_REQUESTS: return "TOO_MANY_REQUESTS";
         case TRADE_RETCODE_NO_CHANGES:        return "NO_CHANGES";
         case TRADE_RETCODE_SERVER_DISABLES_AT: return "SERVER_DISABLES_AT";
         case TRADE_RETCODE_CLIENT_DISABLES_AT: return "CLIENT_DISABLES_AT";
         case TRADE_RETCODE_LOCKED:            return "LOCKED";
         case TRADE_RETCODE_FROZEN:            return "FROZEN";
         case TRADE_RETCODE_CONNECTION:        return "CONNECTION";
         case TRADE_RETCODE_ONLY_REAL:         return "ONLY_REAL";
         case TRADE_RETCODE_LIMIT_ORDERS:      return "LIMIT_ORDERS";
         case TRADE_RETCODE_LIMIT_VOLUME:      return "LIMIT_VOLUME";
         case TRADE_RETCODE_POSITION_CLOSED:   return "POSITION_CLOSED";
         case TRADE_RETCODE_INVALID_FILL:      return "INVALID_FILL";
         case TRADE_RETCODE_CLOSE_ORDER_EXIST: return "CLOSE_ORDER_EXIST";
         case TRADE_RETCODE_LIMIT_POSITIONS:   return "LIMIT_POSITIONS";
        }
      return "UNKNOWN";
     }
  };

#endif // AAG_LOGGER_MQH
