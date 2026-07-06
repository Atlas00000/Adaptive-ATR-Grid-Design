//+------------------------------------------------------------------+
//| TradeManager.mqh — validation, retry, order execution              |
//+------------------------------------------------------------------+
#ifndef AAG_TRADEMANAGER_MQH
#define AAG_TRADEMANAGER_MQH

#include <Trade\Trade.mqh>
#include "RiskManager.mqh"
#include "GridEngine.mqh"
#include "BasketManager.mqh"
#include "StateMachine.mqh"
#include "Diagnostics.mqh"

class CTradeManager
  {
private:
   string            m_symbol;
   ulong             m_magic;
   int               m_slippage;
   CTrade            m_trade;
   CLogger          *m_log;
   CDiagnostics     *m_diag;

   bool              IsTransientRetcode(const uint retcode) const
     {
      return retcode == TRADE_RETCODE_REQUOTE ||
             retcode == TRADE_RETCODE_PRICE_CHANGED ||
             retcode == TRADE_RETCODE_PRICE_OFF ||
             retcode == TRADE_RETCODE_CONNECTION ||
             retcode == TRADE_RETCODE_TIMEOUT ||
             retcode == TRADE_RETCODE_TOO_MANY_REQUESTS;
     }

   bool              ValidateStops(const ENUM_TRADE_BIAS bias,
                                   const double price,
                                   const double sl,
                                   const double tp,
                                   string &reason) const
     {
      const int stops_level = (int)SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
      const double min_dist = stops_level * SymbolInfoDouble(m_symbol, SYMBOL_POINT);

      if(bias == BIAS_BUY)
        {
         if(sl > 0.0 && price - sl < min_dist)
           {
            reason = "sl_too_close";
            return false;
           }
         if(tp > 0.0 && tp - price < min_dist)
           {
            reason = "tp_too_close";
            return false;
           }
        }
      else if(bias == BIAS_SELL)
        {
         if(sl > 0.0 && sl - price < min_dist)
           {
            reason = "sl_too_close";
            return false;
           }
         if(tp > 0.0 && price - tp < min_dist)
           {
            reason = "tp_too_close";
            return false;
           }
        }
      return true;
     }

   bool              CalcSLTP(const ENUM_TRADE_BIAS bias,
                              CATREngine &atr_engine,
                              const double entry_price,
                              double &sl,
                              double &tp,
                              const double tp_atr_mult = -1.0,
                              const double lot = 0.0) const
     {
      const double tp_mult = (tp_atr_mult > 0.0) ? tp_atr_mult : InpTPATRMult;
      const double sl_dist = atr_engine.CalcSLDistance(InpSLTPMode, InpSLATRMult, InpSLFixedPips);
      const double tp_dist = atr_engine.CalcTPDistance(InpSLTPMode, tp_mult, InpTPFixedPips);

      if(bias == BIAS_BUY)
        {
         sl = entry_price - sl_dist;
         tp = entry_price + tp_dist;
        }
      else
        {
         sl = entry_price + sl_dist;
         tp = entry_price - tp_dist;
        }

      if(lot > 0.0)
         ClampSLToMaxLegLoss(bias, entry_price, lot, sl);

      sl = NormalizeDouble(sl, _Digits);
      tp = NormalizeDouble(tp, _Digits);
      return true;
     }

   void              ClampSLToMaxLegLoss(const ENUM_TRADE_BIAS bias,
                                         const double entry_price,
                                         const double lot,
                                         double &sl) const
     {
      if(!InpAIEnabled || !InpAIBasketHealthEnabled ||
         !InpAIHealthHardCapEnabled || !InpAIHealthHardCapL1Enabled)
         return;

      const double max_loss = MathAbs(InpAIHealthHardCapL1USD);
      if(max_loss <= 0.0 || lot <= 0.0 || sl <= 0.0)
         return;

      const ENUM_ORDER_TYPE otype = (bias == BIAS_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double profit = 0.0;
      if(!OrderCalcProfit(otype, m_symbol, lot, entry_price, sl, profit))
         return;
      if(profit >= -max_loss)
         return;

      const double dist = MathAbs(entry_price - sl);
      if(dist <= 0.0)
         return;

      const double ratio = max_loss / MathAbs(profit);
      const double new_dist = dist * ratio * 0.98;
      if(bias == BIAS_BUY)
         sl = NormalizeDouble(entry_price - new_dist, _Digits);
      else
         sl = NormalizeDouble(entry_price + new_dist, _Digits);
     }

   bool              SendWithRetry(const ENUM_TRADE_BIAS bias,
                                   const double lot,
                                   const double sl,
                                   const double tp,
                                   const string comment,
                                   ulong &ticket)
     {
      const int max_attempts = 3;
      for(int attempt = 0; attempt < max_attempts; attempt++)
        {
         bool ok = false;
         if(bias == BIAS_BUY)
            ok = m_trade.Buy(lot, m_symbol, 0.0, sl, tp, comment);
         else
            ok = m_trade.Sell(lot, m_symbol, 0.0, sl, tp, comment);

         const uint retcode = m_trade.ResultRetcode();
         if(m_log != NULL)
            m_log.LogTradeRetcode(retcode, (bias == BIAS_BUY ? "BUY" : "SELL"));

         if(ok && (retcode == TRADE_RETCODE_DONE || retcode == TRADE_RETCODE_PLACED))
           {
            ticket = FindPositionTicket(comment);
            return ticket > 0;
           }

         if(!IsTransientRetcode(retcode))
           {
            if(m_log != NULL)
               m_log.LogError("Fatal trade error on attempt " + IntegerToString(attempt + 1));
            return false;
           }
         Sleep(200);
        }
      return false;
     }

   ulong             FindPositionTicket(const string comment) const
     {
      ulong latest = 0;
      datetime latest_time = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         const ulong ticket = PositionGetTicket(i);
         if(ticket == 0)
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if(PositionGetInteger(POSITION_MAGIC) != m_magic)
            continue;
         if(comment != "" && PositionGetString(POSITION_COMMENT) != comment)
            continue;
         const datetime t = (datetime)PositionGetInteger(POSITION_TIME);
         if(t >= latest_time)
           {
            latest_time = t;
            latest = ticket;
           }
        }
      return latest;
     }

public:
                     CTradeManager() :
                     m_symbol(""),
                     m_magic(0),
                     m_slippage(10),
                     m_log(NULL),
                     m_diag(NULL)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }
   void              SetDiagnostics(CDiagnostics &diag) { m_diag = GetPointer(diag); }

   bool              Init(const string symbol, const ulong magic, const int slippage)
     {
      m_symbol = symbol;
      m_magic = magic;
      m_slippage = slippage;
      m_trade.SetExpertMagicNumber(magic);
      m_trade.SetDeviationInPoints(slippage);
      m_trade.SetTypeFillingBySymbol(symbol);
      return true;
     }

   bool              OpenFirstLevel(const ENUM_TRADE_BIAS bias,
                                    CATREngine &atr_engine,
                                    CRiskManager &risk,
                                    CGridEngine &grid,
                                    CBasketManager &basket,
                                    CStateMachine &state,
                                    const double grid_anchor = 0.0,
                                    const double ai_lot_mult = 1.0)
     {
      string reason = "";
      if(!risk.PreTradeCheck(InpMaxSpreadPips, reason))
        {
         if(m_log != NULL)
            m_log.LogRiskReject(reason);
         return false;
        }

      if(!atr_engine.IsDistanceFrozen())
         atr_engine.FreezeDistance(InpATRMultiplier);

      const double lot = risk.CalcLotSize(atr_engine, InpSizingMode, InpFixedLot,
                                          InpRiskPercent, InpMinLot, InpMaxLot,
                                          InpSLTPMode, InpSLATRMult, InpSLFixedPips, 0);
      const double adj_lot = AAG_NormalizeLot(m_symbol, lot * ai_lot_mult,
                                                InpMinLot, InpMaxLot);

      const double price = (bias == BIAS_BUY) ?
                           SymbolInfoDouble(m_symbol, SYMBOL_ASK) :
                           SymbolInfoDouble(m_symbol, SYMBOL_BID);

      double sl = 0.0, tp = 0.0;
      CalcSLTP(bias, atr_engine, price, sl, tp, -1.0, adj_lot);

      if(!ValidateStops(bias, price, sl, tp, reason))
        {
         if(m_log != NULL)
            m_log.LogRiskReject(reason);
         return false;
        }

      const string comment = grid.LevelComment(0);
      ulong ticket = 0;
      if(!SendWithRetry(bias, adj_lot, sl, tp, comment, ticket))
         return false;

      const double anchor = (grid_anchor > 0.0) ? grid_anchor : price;
      grid.SetContext(anchor, atr_engine.GetFrozenDistance(), bias);
      basket.StartBasket(anchor, atr_engine.GetFrozenDistance(), bias, ticket, 0,
                         GRID_STATE_GRID_ACTIVE);
      state.SetGridActive();

      if(m_diag != NULL)
         m_diag.RecordOpen(ticket, 0, bias, atr_engine.GetADX(), atr_engine.GetATR(), 1);

      if(m_log != NULL)
         m_log.LogInfo("First level opened " + AAG_BiasToString(bias) +
                       " lot=" + DoubleToString(adj_lot, 2) +
                       " anchor=" + DoubleToString(anchor, _Digits));
      return true;
     }

   bool              OpenGridLevel(const ENUM_TRADE_BIAS bias,
                                   const int level_index,
                                   CATREngine &atr_engine,
                                   CRiskManager &risk,
                                   CGridEngine &grid,
                                   CBasketManager &basket,
                                   CStateMachine &state,
                                   const double ai_lot_mult = 1.0,
                                   const double ai_tp_atr_mult = -1.0)
     {
      string reason = "";
      const int max_levels = risk.GetEffectiveMaxLevels(atr_engine, InpMaxGridLevels);
      if(!risk.CanAddLevel(basket.GetOpenCount(), max_levels,
                           InpMaxSpreadPips, basket.GetFloatingPL(), reason))
        {
         if(m_log != NULL)
            m_log.LogRiskReject(reason);
         return false;
        }

      if(!risk.PreTradeCheck(InpMaxSpreadPips, reason))
        {
         if(m_log != NULL)
            m_log.LogRiskReject(reason);
         return false;
        }

      const double lot = risk.CalcLotSize(atr_engine, InpSizingMode, InpFixedLot,
                                          InpRiskPercent, InpMinLot, InpMaxLot,
                                          InpSLTPMode, InpSLATRMult, InpSLFixedPips,
                                          level_index);
      const double adj_lot = AAG_NormalizeLot(m_symbol, lot * ai_lot_mult,
                                                InpMinLot, InpMaxLot);

      const double price = (bias == BIAS_BUY) ?
                           SymbolInfoDouble(m_symbol, SYMBOL_ASK) :
                           SymbolInfoDouble(m_symbol, SYMBOL_BID);

      double sl = 0.0, tp = 0.0;
      CalcSLTP(bias, atr_engine, price, sl, tp, ai_tp_atr_mult, adj_lot);

      if(!ValidateStops(bias, price, sl, tp, reason))
        {
         if(m_log != NULL)
            m_log.LogRiskReject(reason);
         return false;
        }

      const string comment = grid.LevelComment(level_index);
      ulong ticket = 0;
      if(!SendWithRetry(bias, adj_lot, sl, tp, comment, ticket))
         return false;

      basket.AddTicket(ticket, level_index, state.GetState());

      if(m_diag != NULL)
        {
         const int levels = basket.GetOpenCount();
         m_diag.RecordOpen(ticket, level_index, bias, atr_engine.GetADX(),
                           atr_engine.GetATR(), levels);
        }

      if(m_log != NULL)
         m_log.LogInfo("Grid level " + IntegerToString(level_index) +
                       " opened lot=" + DoubleToString(adj_lot, 2));

      if(basket.GetOpenCount() >= max_levels)
         state.SetManaging();

      return true;
     }
  };

#endif // AAG_TRADEMANAGER_MQH
