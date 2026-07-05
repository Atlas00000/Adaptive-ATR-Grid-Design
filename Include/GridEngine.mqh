//+------------------------------------------------------------------+
//| GridEngine.mqh — anchor, level prices, level triggers            |
//+------------------------------------------------------------------+
#ifndef AAG_GRIDENGINE_MQH
#define AAG_GRIDENGINE_MQH

#include "Logger.mqh"

class CGridEngine
  {
private:
   string            m_symbol;
   double            m_anchor;
   double            m_frozen_distance;
   ENUM_TRADE_BIAS   m_bias;
   CLogger          *m_log;

public:
                     CGridEngine() :
                     m_symbol(""),
                     m_anchor(0.0),
                     m_frozen_distance(0.0),
                     m_bias(BIAS_NONE),
                     m_log(NULL)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }
   void              Init(const string symbol) { m_symbol = symbol; }

   void              SetContext(const double anchor, const double frozen_distance,
                                const ENUM_TRADE_BIAS bias)
     {
      m_anchor = anchor;
      m_frozen_distance = frozen_distance;
      m_bias = bias;
      if(m_log != NULL)
         m_log.LogGrid("Context anchor=" + DoubleToString(m_anchor, _Digits) +
                       " dist=" + DoubleToString(m_frozen_distance, _Digits) +
                       " bias=" + AAG_BiasToString(m_bias));
     }

   void              Reset()
     {
      m_anchor = 0.0;
      m_frozen_distance = 0.0;
      m_bias = BIAS_NONE;
     }

   double            GetAnchor() const { return m_anchor; }
   double            GetFrozenDistance() const { return m_frozen_distance; }
   ENUM_TRADE_BIAS   GetBias() const { return m_bias; }

   double            GetLevelPrice(const int level_index) const
     {
      if(m_bias == BIAS_BUY)
         return m_anchor - (level_index * m_frozen_distance);
      if(m_bias == BIAS_SELL)
         return m_anchor + (level_index * m_frozen_distance);
      return 0.0;
     }

   int               GetNextLevelIndex(const int levels_filled) const
     {
      return levels_filled;
     }

   bool              IsPriceAtLevel(const ENUM_TRADE_BIAS bias,
                                    const int level_index,
                                    const int &filled_levels[]) const
     {
      if(level_index <= 0)
         return false;

      for(int i = 0; i < ArraySize(filled_levels); i++)
        {
         if(filled_levels[i] == level_index)
            return false;
        }

      const double level_price = GetLevelPrice(level_index);
      const double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      const double tolerance = point * 2.0;

      if(bias == BIAS_BUY)
        {
         const double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         return bid <= level_price + tolerance;
        }
      if(bias == BIAS_SELL)
        {
         const double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         return ask >= level_price - tolerance;
        }
      return false;
     }

   string            LevelComment(const int level_index) const
     {
      return "AAG|L" + IntegerToString(level_index);
     }

   int               ParseLevelFromComment(const string comment) const
     {
      const int pos = StringFind(comment, "AAG|L");
      if(pos < 0)
         return -1;
      return (int)StringToInteger(StringSubstr(comment, pos + 5));
     }
  };

#endif // AAG_GRIDENGINE_MQH
