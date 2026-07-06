//+------------------------------------------------------------------+
//| BasketManager.mqh — basket tracking, TP, recovery                |
//+------------------------------------------------------------------+
#ifndef AAG_BASKETMANAGER_MQH
#define AAG_BASKETMANAGER_MQH

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include "GridEngine.mqh"
#include "ATREngine.mqh"
#include "StateMachine.mqh"
#include "Diagnostics.mqh"

class CBasketManager
  {
private:
   string            m_symbol;
   ulong             m_magic;
   ulong             m_tickets[];
   int               m_filled_levels[];
   double            m_anchor;
   double            m_frozen_distance;
   ENUM_TRADE_BIAS   m_bias;
   datetime          m_basket_start;
   double            m_trail_peak;
   bool              m_trail_armed;
   bool              m_cascade_pending;
   int               m_cascade_legs_before;
   datetime          m_cascade_trigger_time;
   CLogger          *m_log;
   CDiagnostics     *m_diag;
   CTrade            m_trade;
   CPositionInfo     m_position;

   string            GVKey(const string suffix) const
     {
      return AAG_GVPrefix(m_symbol, m_magic) + suffix;
     }

   void              SavePersistence(const ENUM_GRID_STATE state) const
     {
      GlobalVariableSet(GVKey("_anchor"), m_anchor);
      GlobalVariableSet(GVKey("_dist"), m_frozen_distance);
      GlobalVariableSet(GVKey("_bias"), (double)m_bias);
      GlobalVariableSet(GVKey("_levels"), (double)ArraySize(m_tickets));
      GlobalVariableSet(GVKey("_state"), (double)state);
      GlobalVariableSet(GVKey("_start"), (double)m_basket_start);
     }

   void              ClearPersistence() const
     {
      GlobalVariableDel(GVKey("_anchor"));
      GlobalVariableDel(GVKey("_dist"));
      GlobalVariableDel(GVKey("_bias"));
      GlobalVariableDel(GVKey("_levels"));
      GlobalVariableDel(GVKey("_state"));
      GlobalVariableDel(GVKey("_start"));
     }

   double            GetRecentCloseProfit() const
     {
      if(!HistorySelect(TimeCurrent() - 120, TimeCurrent()))
         return 0.0;

      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
        {
         const ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;
         if(HistoryDealGetString(deal, DEAL_SYMBOL) != m_symbol)
            continue;
         if(HistoryDealGetInteger(deal, DEAL_MAGIC) != (long)m_magic)
            continue;
         if(HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_OUT &&
            HistoryDealGetInteger(deal, DEAL_ENTRY) != DEAL_ENTRY_OUT_BY)
            continue;

         return HistoryDealGetDouble(deal, DEAL_PROFIT) +
                HistoryDealGetDouble(deal, DEAL_SWAP) +
                HistoryDealGetDouble(deal, DEAL_COMMISSION);
        }
      return 0.0;
     }

   double            CalcOpenFloatingPL() const
     {
      double pl = 0.0;
      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(!PositionSelectByTicket(m_tickets[i]))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if(PositionGetInteger(POSITION_MAGIC) != m_magic)
            continue;
         pl += PositionGetDouble(POSITION_PROFIT) +
               PositionGetDouble(POSITION_SWAP);
        }
      return pl;
     }

   double            CalcFloatingFromOpenTickets() const
     {
      double pl = 0.0;
      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(!PositionSelectByTicket(m_tickets[i]))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if(PositionGetInteger(POSITION_MAGIC) != (long)m_magic)
            continue;
         pl += PositionGetDouble(POSITION_PROFIT) +
               PositionGetDouble(POSITION_SWAP);
        }
      return pl;
     }

   int               CountRemainingOpenLegs() const
     {
      int n = 0;
      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(!PositionSelectByTicket(m_tickets[i]))
            continue;
         if(PositionGetString(POSITION_SYMBOL) != m_symbol)
            continue;
         if(PositionGetInteger(POSITION_MAGIC) != (long)m_magic)
            continue;
         n++;
        }
      return n;
     }

   bool              ShouldSLCascadeFromDeal(const double deal_profit,
                                             const double floating,
                                             const int legs_before_close,
                                             const int open_after) const
     {
      if(!InpAIHealthSLCascadeEnabled || !InpAIEnabled || !InpAIBasketHealthEnabled)
         return false;
      if(legs_before_close < InpAIHealthSLCascadeMinLegs)
         return false;
      if(open_after <= 0 || open_after >= legs_before_close)
         return false;
      if(deal_profit >= 0.0)
         return false;

      if(InpAIHealthSLCascadeAnyPartial)
         return true;

      if(deal_profit <= InpAIHealthSLCascadeLossUSD)
         return true;
      if(InpAIHealthSLCascadeStackUSD < 0.0 &&
         (deal_profit + floating) < InpAIHealthSLCascadeStackUSD)
         return true;
      if(InpAIHealthSLCascadeUseFloat && floating < InpAIHealthSLCascadeFloatUSD)
         return true;
      return false;
     }

   bool              TryExecuteSLCascade(CStateMachine &state,
                                         const double deal_profit,
                                         const int legs_before,
                                         const int open_after,
                                         const double floating)
     {
      if(!ShouldSLCascadeFromDeal(deal_profit, floating, legs_before, open_after))
         return false;

      if(m_log != NULL)
         m_log.LogBasket("SL cascade deal_pl=" + DoubleToString(deal_profit, 2) +
                         " float=" + DoubleToString(floating, 2) +
                         " legs=" + IntegerToString(legs_before) + "->" +
                         IntegerToString(open_after));

      CloseBasket(state, "ai_health_sl_cascade");
      ScanPositions();
      return true;
     }

   bool              TryBasketCapClose(CStateMachine &state, const int open_count,
                                       const double deal_pl_addon = 0.0)
     {
      if(!InpAIEnabled || !InpAIBasketHealthEnabled || !InpAIHealthBasketCapEnabled)
         return false;
      if(open_count < InpAIHealthBasketCapMinLegs)
         return false;

      const double total = SumBasketRealizedPnL() + deal_pl_addon +
                           CalcFloatingFromOpenTickets();
      if(total >= InpAIHealthBasketCapUSD)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("Basket cap total=" + DoubleToString(total, 2) +
                         " deal=" + DoubleToString(deal_pl_addon, 2) +
                         " open=" + IntegerToString(open_count));

      CloseBasket(state, "ai_health_basket_cap");
      ScanPositions();
      return true;
     }

   void              ScanPositions()
     {
      const int prev_count = ArraySize(m_tickets);
      ArrayResize(m_tickets, 0);
      ArrayResize(m_filled_levels, 0);

      const int total = PositionsTotal();
      for(int i = total - 1; i >= 0; i--)
        {
         if(!m_position.SelectByIndex(i))
            continue;
         if(m_position.Symbol() != m_symbol || m_position.Magic() != m_magic)
            continue;

         const ulong ticket = m_position.Ticket();
         const int size = ArraySize(m_tickets);
         ArrayResize(m_tickets, size + 1);
         m_tickets[size] = ticket;

         const int level = ParseLevelFromComment(m_position.Comment());
         const int lvl_size = ArraySize(m_filled_levels);
         ArrayResize(m_filled_levels, lvl_size + 1);
         m_filled_levels[lvl_size] = (level >= 0) ? level : size;
        }

      const int new_count = ArraySize(m_tickets);
      if(prev_count >= InpAIHealthSLCascadeMinLegs &&
         new_count > 0 && new_count < prev_count)
        {
         m_cascade_pending = true;
         m_cascade_legs_before = prev_count;
         m_cascade_trigger_time = TimeCurrent();
        }
     }

   int               ParseLevelFromComment(const string comment) const
     {
      const int pos = StringFind(comment, "AAG|L");
      if(pos < 0)
         return -1;
      return (int)StringToInteger(StringSubstr(comment, pos + 5));
     }

   void              ResetTrail()
     {
      m_trail_peak = 0.0;
      m_trail_armed = false;
     }

   double            GetTotalVolume()
     {
      double volume = 0.0;
      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(m_position.SelectByTicket(m_tickets[i]))
            volume += m_position.Volume();
        }
      return volume;
     }

   double            ATRToMoney(const double atr, const double volume) const
     {
      const double tick_size = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      const double tick_value = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      if(tick_size <= 0.0 || tick_value <= 0.0 || volume <= 0.0)
         return 0.0;
      return (atr / tick_size) * tick_value * volume;
     }

   double            SumBasketRealizedPnL() const
     {
      if(m_basket_start <= 0)
         return 0.0;

      if(!HistorySelect(m_basket_start, TimeCurrent()))
         return 0.0;

      double pl = 0.0;
      const int deals = HistoryDealsTotal();
      for(int i = 0; i < deals; i++)
        {
         const ulong deal = HistoryDealGetTicket(i);
         if(deal == 0)
            continue;
         if(HistoryDealGetString(deal, DEAL_SYMBOL) != m_symbol)
            continue;
         if(HistoryDealGetInteger(deal, DEAL_MAGIC) != (long)m_magic)
            continue;

         const long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
         if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
            continue;

         pl += HistoryDealGetDouble(deal, DEAL_PROFIT) +
               HistoryDealGetDouble(deal, DEAL_SWAP) +
               HistoryDealGetDouble(deal, DEAL_COMMISSION);
        }
      return pl;
     }

public:
                     CBasketManager() :
                     m_symbol(""),
                     m_magic(0),
                     m_anchor(0.0),
                     m_frozen_distance(0.0),
                     m_bias(BIAS_NONE),
                     m_basket_start(0),
                     m_trail_peak(0.0),
                     m_trail_armed(false),
                     m_cascade_pending(false),
                     m_cascade_legs_before(0),
                     m_cascade_trigger_time(0),
                     m_log(NULL),
                     m_diag(NULL)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }
   void              SetDiagnostics(CDiagnostics &diag) { m_diag = GetPointer(diag); }

   bool              Init(const string symbol, const ulong magic, const int slippage)
     {
      m_symbol = symbol;
      m_magic = magic;
      m_trade.SetExpertMagicNumber(magic);
      m_trade.SetDeviationInPoints(slippage);
      m_trade.SetTypeFillingBySymbol(symbol);
      return true;
     }

   bool              CloseBasket(CStateMachine &state, const string reason)
     {
      if(m_log != NULL)
         m_log.LogBasket("Exit triggered: " + reason);

      if(m_diag != NULL)
         m_diag.OnBasketClosePending(reason);

      state.SetExiting();
      CloseAll();
      return true;
     }

   void              OnTradeTransaction(const MqlTradeTransaction &trans,
                                        CStateMachine &state)
     {
      if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
         return;
      if(state.GetState() == GRID_STATE_EXITING)
         return;
      if(!state.IsBasketActive())
         return;

      const ulong deal = trans.deal;
      if(deal == 0)
         return;
      if(!HistoryDealSelect(deal))
         return;
      if(HistoryDealGetString(deal, DEAL_SYMBOL) != m_symbol)
         return;
      if(HistoryDealGetInteger(deal, DEAL_MAGIC) != (long)m_magic)
         return;

      const long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
         return;

      const int legs_before = ArraySize(m_tickets);
      const double deal_pl = HistoryDealGetDouble(deal, DEAL_PROFIT) +
                             HistoryDealGetDouble(deal, DEAL_SWAP) +
                             HistoryDealGetDouble(deal, DEAL_COMMISSION);
      const int open_after = CountRemainingOpenLegs();
      if(open_after <= 0 || open_after >= legs_before)
        {
         ScanPositions();
         return;
        }

      if(TryBasketCapClose(state, open_after, deal_pl))
        {
         m_cascade_pending = false;
         return;
        }

      if(legs_before >= InpAIHealthSLCascadeMinLegs)
        {
         const double floating = CalcFloatingFromOpenTickets();
         if(TryExecuteSLCascade(state, deal_pl, legs_before, open_after, floating))
           {
            m_cascade_pending = false;
            return;
           }
        }

      ScanPositions();
     }

   bool              ProcessPendingSLCascade(CStateMachine &state)
     {
      if(!m_cascade_pending)
         return false;
      if(state.GetState() == GRID_STATE_EXITING)
        {
         m_cascade_pending = false;
         return false;
        }
      if(!state.IsBasketActive())
        {
         m_cascade_pending = false;
         return false;
        }

      const int open_after = ArraySize(m_tickets);
      if(open_after <= 0)
        {
         m_cascade_pending = false;
         return false;
        }

      const double deal_pl = GetRecentCloseProfit();
      if(deal_pl == 0.0 && (TimeCurrent() - m_cascade_trigger_time) < 2)
         return false;

      const int legs_before = (m_cascade_legs_before > 0) ?
                              m_cascade_legs_before : (open_after + 1);
      const double floating = CalcFloatingFromOpenTickets();
      m_cascade_pending = false;
      return TryExecuteSLCascade(state, deal_pl, legs_before, open_after, floating);
     }

   void              Reset()
     {
      ArrayResize(m_tickets, 0);
      ArrayResize(m_filled_levels, 0);
      m_anchor = 0.0;
      m_frozen_distance = 0.0;
      m_bias = BIAS_NONE;
      m_basket_start = 0;
      ResetTrail();
      m_cascade_pending = false;
      m_cascade_legs_before = 0;
      m_cascade_trigger_time = 0;
      ClearPersistence();
     }

   void              StartBasket(const double anchor, const double frozen_distance,
                                 const ENUM_TRADE_BIAS bias, const ulong ticket,
                                 const int level_index, const ENUM_GRID_STATE state)
     {
      m_anchor = anchor;
      m_frozen_distance = frozen_distance;
      m_bias = bias;
      m_basket_start = TimeCurrent();
      ResetTrail();
      ArrayResize(m_tickets, 1);
      m_tickets[0] = ticket;
      ArrayResize(m_filled_levels, 1);
      m_filled_levels[0] = level_index;
      if(m_diag != NULL)
         m_diag.OnBasketStart();
      SavePersistence(state);
      if(m_log != NULL)
         m_log.LogBasket("Started anchor=" + DoubleToString(m_anchor, _Digits) +
                         " levels=1 bias=" + AAG_BiasToString(m_bias));
     }

   void              AddTicket(const ulong ticket, const int level_index,
                               const ENUM_GRID_STATE state)
     {
      const int size = ArraySize(m_tickets);
      ArrayResize(m_tickets, size + 1);
      m_tickets[size] = ticket;
      const int lvl_size = ArraySize(m_filled_levels);
      ArrayResize(m_filled_levels, lvl_size + 1);
      m_filled_levels[lvl_size] = level_index;
      if(m_diag != NULL)
         m_diag.OnLevelAdded(size + 1);
      SavePersistence(state);
      if(m_log != NULL)
         m_log.LogBasket("Added level " + IntegerToString(level_index) +
                         " total=" + IntegerToString(size + 1));
     }

   int               GetOpenCount()
     {
      ScanPositions();
      return ArraySize(m_tickets);
     }

   int               GetFilledLevels(int &levels[])
     {
      ScanPositions();
      ArrayCopy(levels, m_filled_levels);
      return ArraySize(levels);
     }

   double            GetAnchor() const { return m_anchor; }
   double            GetFrozenDistance() const { return m_frozen_distance; }
   ENUM_TRADE_BIAS   GetBias() const { return m_bias; }
   datetime          GetBasketStart() const { return m_basket_start; }

   double            GetFloatingPL()
     {
      double pl = 0.0;
      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(m_position.SelectByTicket(m_tickets[i]))
            pl += m_position.Profit() + m_position.Swap() + m_position.Commission();
        }
      return pl;
     }

   double            GetTotalBasketPnL()
     {
      return SumBasketRealizedPnL() + CalcFloatingFromOpenTickets();
     }

   bool              HasOpenPositions()
     {
      return GetOpenCount() > 0;
     }

   bool              CheckBasketTP(CStateMachine &state,
                                   const bool enabled,
                                   const ENUM_BASKET_TP_MODE mode,
                                   const double tp_money,
                                   const double tp_percent,
                                   const bool adaptive,
                                   const double adaptive_mult,
                                   CATREngine &atr_engine)
     {
      if(!enabled)
         return false;

      ScanPositions();
      if(ArraySize(m_tickets) == 0)
         return false;

      const double floating = GetFloatingPL();
      double target = tp_money;
      if(adaptive)
        {
         const int levels = ArraySize(m_tickets);
         const double volume = GetTotalVolume();
         const double atr_money = ATRToMoney(atr_engine.GetATR(), volume);
         target = levels * adaptive_mult * atr_money;
         if(target <= 0.0)
            return false;
        }
      else if(mode == BASKET_TP_PERCENT)
         target = AccountInfoDouble(ACCOUNT_EQUITY) * tp_percent / 100.0;

      if(floating < target)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("TP hit floating=" + DoubleToString(floating, 2) +
                         " target=" + DoubleToString(target, 2));

      return CloseBasket(state, adaptive ? "BASKET_TP_ADAPTIVE" : "BASKET_TP");
     }

   bool              CheckBasketTrail(CStateMachine &state,
                                      const bool enabled,
                                      const double activate_money,
                                      const double lock_percent)
     {
      if(!enabled)
         return false;

      ScanPositions();
      if(ArraySize(m_tickets) == 0)
         return false;

      const double floating = GetFloatingPL();
      if(floating > m_trail_peak)
         m_trail_peak = floating;

      if(!m_trail_armed && m_trail_peak >= activate_money)
         m_trail_armed = true;

      if(!m_trail_armed)
         return false;

      const double floor = m_trail_peak * lock_percent / 100.0;
      if(floating >= floor)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("Trail hit floating=" + DoubleToString(floating, 2) +
                         " peak=" + DoubleToString(m_trail_peak, 2) +
                         " floor=" + DoubleToString(floor, 2));

      return CloseBasket(state, "BASKET_TRAIL");
     }

   bool              CheckMRExit(CStateMachine &state,
                                 CATREngine &atr_engine,
                                 const bool enabled,
                                 const double tolerance_atr)
     {
      if(!enabled)
         return false;

      ScanPositions();
      if(ArraySize(m_tickets) == 0 || m_bias == BIAS_NONE)
         return false;

      const double ema = atr_engine.GetEMA();
      const double tol = atr_engine.GetATR() * tolerance_atr;
      if(ema <= 0.0 || tol <= 0.0)
         return false;

      const double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      const double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      bool touch = false;

      if(m_bias == BIAS_BUY)
         touch = (bid >= ema - tol);
      else if(m_bias == BIAS_SELL)
         touch = (ask <= ema + tol);

      if(!touch)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("MR EMA exit ema=" + DoubleToString(ema, _Digits) +
                         " bid=" + DoubleToString(bid, _Digits) +
                         " ask=" + DoubleToString(ask, _Digits));

      return CloseBasket(state, "BASKET_MR_EMA");
     }

   bool              CheckMAEExit(CStateMachine &state,
                                CATREngine &atr_engine,
                                const bool enabled,
                                const double atr_mult)
     {
      if(!enabled || atr_mult <= 0.0)
         return false;

      ScanPositions();
      if(ArraySize(m_tickets) == 0 || m_bias == BIAS_NONE || m_anchor <= 0.0)
         return false;

      const double adverse = atr_engine.GetATR() * atr_mult;
      if(adverse <= 0.0)
         return false;

      const double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      const double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      bool breach = false;

      if(m_bias == BIAS_BUY)
         breach = (bid <= m_anchor - adverse);
      else if(m_bias == BIAS_SELL)
         breach = (ask >= m_anchor + adverse);

      if(!breach)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("MAE exit anchor=" + DoubleToString(m_anchor, _Digits) +
                         " adverse=" + DoubleToString(adverse, _Digits));

      return CloseBasket(state, "MAE_EXIT");
     }

   bool              CheckTimeStop(CStateMachine &state,
                                 const bool enabled,
                                 const int stop_minutes)
     {
      if(!enabled || stop_minutes <= 0 || m_basket_start <= 0)
         return false;

      ScanPositions();
      if(ArraySize(m_tickets) == 0)
         return false;

      const int elapsed = (int)(TimeCurrent() - m_basket_start);
      if(elapsed < stop_minutes * 60)
         return false;

      if(m_log != NULL)
         m_log.LogBasket("Time stop elapsed=" + IntegerToString(elapsed / 60) + " min");

      return CloseBasket(state, "BASKET_TIME_STOP");
     }

   bool              CheckBasketExits(CStateMachine &state,
                                     CATREngine &atr_engine,
                                     const bool tp_enabled,
                                     const ENUM_BASKET_TP_MODE tp_mode,
                                     const double tp_money,
                                     const double tp_percent,
                                     const bool tp_adaptive,
                                     const double adaptive_mult,
                                     const bool trail_enabled,
                                     const double trail_activate,
                                     const double trail_lock_pct,
                                     const bool mr_enabled,
                                     const double mr_tol_atr,
                                     const bool time_enabled,
                                     const int time_minutes)
     {
      if(CheckTimeStop(state, time_enabled, time_minutes))
         return true;
      if(CheckBasketTrail(state, trail_enabled, trail_activate, trail_lock_pct))
         return true;
      if(CheckMRExit(state, atr_engine, mr_enabled, mr_tol_atr))
         return true;
      if(CheckBasketTP(state, tp_enabled, tp_mode, tp_money, tp_percent,
                       tp_adaptive, adaptive_mult, atr_engine))
         return true;
      return false;
     }

   void              CloseAll()
     {
      ScanPositions();
      for(int i = ArraySize(m_tickets) - 1; i >= 0; i--)
        {
         if(m_position.SelectByTicket(m_tickets[i]))
           {
            if(!m_trade.PositionClose(m_tickets[i]))
              {
               if(m_log != NULL)
                  m_log.LogError("Failed to close ticket " + IntegerToString(m_tickets[i]) +
                                 " err=" + IntegerToString(GetLastError()));
              }
           }
        }
      ScanPositions();
     }

   double            OnBasketClosed(CStateMachine &state, const int cooldown_minutes)
     {
      const double basket_pnl = SumBasketRealizedPnL();
      Reset();
      state.StartCooldown(cooldown_minutes);
      return basket_pnl;
     }

   bool              CloseBestProfitableLeg(const double min_profit)
     {
      ScanPositions();
      ulong best_ticket = 0;
      double best_pl = min_profit;

      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(!m_position.SelectByTicket(m_tickets[i]))
            continue;
         const double pl = m_position.Profit() + m_position.Swap() + m_position.Commission();
         if(pl >= best_pl)
           {
            best_pl = pl;
            best_ticket = m_tickets[i];
           }
        }

      if(best_ticket == 0)
         return false;

      if(!m_trade.PositionClose(best_ticket))
        {
         if(m_log != NULL)
            m_log.LogError("AI-805 trim failed ticket=" + IntegerToString(best_ticket));
         return false;
        }

      if(m_log != NULL)
         m_log.LogBasket("AI-805 trimmed best leg ticket=" + IntegerToString(best_ticket) +
                         " pl=" + DoubleToString(best_pl, 2));
      ScanPositions();
      return true;
     }

   bool              Recover(CStateMachine &state, CGridEngine &grid,
                           CATREngine &atr_engine)
     {
      ScanPositions();
      if(ArraySize(m_tickets) == 0)
        {
         if(GlobalVariableCheck(GVKey("_anchor")))
           {
            m_anchor = GlobalVariableGet(GVKey("_anchor"));
            m_frozen_distance = GlobalVariableGet(GVKey("_dist"));
            m_bias = (ENUM_TRADE_BIAS)(int)GlobalVariableGet(GVKey("_bias"));
            m_basket_start = (datetime)(long)GlobalVariableGet(GVKey("_start"));
            atr_engine.RestoreFrozenDistance(m_frozen_distance);
            grid.SetContext(m_anchor, m_frozen_distance, m_bias);

            const ENUM_GRID_STATE saved = (ENUM_GRID_STATE)(int)GlobalVariableGet(GVKey("_state"));
            if(saved == GRID_STATE_IDLE || saved == GRID_STATE_COOLDOWN)
               return false;
            state.RestoreState(saved, 0);
            if(m_log != NULL)
               m_log.LogBasket("Recovered from GV without open positions — reset");
            ClearPersistence();
            state.SetIdle();
            return false;
           }
         return false;
        }

      // Rebuild anchor and bias from positions
      datetime earliest = D'2099.01.01';
      m_anchor = 0.0;
      m_bias = BIAS_NONE;

      for(int i = 0; i < ArraySize(m_tickets); i++)
        {
         if(!m_position.SelectByTicket(m_tickets[i]))
            continue;

         const datetime open_time = m_position.Time();
         const double open_price = m_position.PriceOpen();
         const ENUM_POSITION_TYPE type = m_position.PositionType();

         if(type == POSITION_TYPE_BUY)
            m_bias = BIAS_BUY;
         else if(type == POSITION_TYPE_SELL)
            m_bias = BIAS_SELL;

         if(open_time < earliest)
           {
            earliest = open_time;
            m_anchor = open_price;
           }
        }

      if(GlobalVariableCheck(GVKey("_dist")))
         m_frozen_distance = GlobalVariableGet(GVKey("_dist"));
      else if(ArraySize(m_tickets) >= 2)
        {
         // Derive spacing from positions
         double prices[];
         ArrayResize(prices, ArraySize(m_tickets));
         for(int i = 0; i < ArraySize(m_tickets); i++)
           {
            if(m_position.SelectByTicket(m_tickets[i]))
               prices[i] = m_position.PriceOpen();
           }
         ArraySort(prices);
         m_frozen_distance = MathAbs(prices[1] - prices[0]);
        }
      else
        {
         m_frozen_distance = atr_engine.CalcGridDistance(InpATRMultiplier);
        }

      m_basket_start = earliest;
      ResetTrail();
      atr_engine.RestoreFrozenDistance(m_frozen_distance);
      grid.SetContext(m_anchor, m_frozen_distance, m_bias);

      ENUM_GRID_STATE restored = GRID_STATE_GRID_ACTIVE;
      if(GlobalVariableCheck(GVKey("_state")))
         restored = (ENUM_GRID_STATE)(int)GlobalVariableGet(GVKey("_state"));

      if(ArraySize(m_tickets) >= InpMaxGridLevels)
         restored = GRID_STATE_MANAGING;

      state.RestoreState(restored, 0);
      SavePersistence(restored);

      if(m_log != NULL)
         m_log.LogBasket("Recovered " + IntegerToString(ArraySize(m_tickets)) +
                         " positions anchor=" + DoubleToString(m_anchor, _Digits));

      return true;
     }

   bool              SyncAfterExternalClose(CStateMachine &state, const int cooldown_minutes,
                                            double &out_basket_pnl)
     {
      out_basket_pnl = 0.0;
      ScanPositions();
      if(ArraySize(m_tickets) == 0 && state.IsBasketActive())
        {
         if(m_log != NULL)
            m_log.LogBasket("All positions closed externally");
         out_basket_pnl = OnBasketClosed(state, cooldown_minutes);
         return true;
        }
      return false;
     }
  };

#endif // AAG_BASKETMANAGER_MQH
