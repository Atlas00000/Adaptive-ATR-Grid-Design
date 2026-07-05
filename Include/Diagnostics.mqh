//+------------------------------------------------------------------+
//| Diagnostics.mqh — Phase E0 trade journal & aggregation (EDGE-001) |
//+------------------------------------------------------------------+
#ifndef AAG_DIAGNOSTICS_MQH
#define AAG_DIAGNOSTICS_MQH

#include "Logger.mqh"

enum ENUM_DIAG_EXIT
  {
   DIAG_EXIT_UNKNOWN = 0,
   DIAG_EXIT_SL      = 1,
   DIAG_EXIT_TP      = 2,
   DIAG_EXIT_BASKET  = 3,
   DIAG_EXIT_OTHER   = 4
  };

struct DiagOpenCtx
  {
   ulong             ticket;
   int               basket_id;
   int               level_index;
   int               levels_at_open;
   ENUM_TRADE_BIAS   bias;
   double            adx;
   double            atr;
   datetime          open_time;
   int               basket_max_levels;
  };

struct DiagClosedTrade
  {
   ulong             ticket;
   int               basket_id;
   int               level_index;
   int               levels_at_open;
   int               basket_max_levels;
   string            direction;
   int               hour;
   int               weekday;
   string            weekday_name;
   int               month;
   int               year;
   string            session_tag;
   bool              bad_hour;
   double            adx;
   double            atr;
   double            profit;
   int               hold_seconds;
   string            exit_reason;
   ENUM_DIAG_EXIT    exit_type;
   datetime          open_time;
   datetime          close_time;
  };

class CDiagnostics
  {
private:
   string            m_symbol;
   ulong             m_magic;
   bool              m_enabled;
   bool              m_csv;
   string            m_prefix;
   CLogger          *m_log;

   DiagOpenCtx       m_opens[];
   DiagClosedTrade   m_closed[];
   int               m_basket_id;
   int               m_basket_max_levels;
   string            m_pending_basket_close;

   static string     WeekdayName(const int dow)
     {
      switch(dow)
        {
         case 0: return "Sun";
         case 1: return "Mon";
         case 2: return "Tue";
         case 3: return "Wed";
         case 4: return "Thu";
         case 5: return "Fri";
         case 6: return "Sat";
        }
      return "?";
     }

   static bool       IsBadHour(const int hour)
     {
      return hour == 9 || hour == 16 ||
             hour == 18 || hour == 19 ||
             hour == 21 || hour == 22;
     }

   static string     SessionTag(const int hour)
     {
      if(hour >= 0 && hour < 8)   return "Asian";
      if(hour >= 8 && hour < 16)  return "London";
      if(hour >= 16 && hour < 22) return "NY";
      return "Late";
     }

   static string     ExitTypeToString(const ENUM_DIAG_EXIT t)
     {
      switch(t)
        {
         case DIAG_EXIT_SL:     return "SL";
         case DIAG_EXIT_TP:     return "TP";
         case DIAG_EXIT_BASKET: return "BASKET";
         case DIAG_EXIT_OTHER:  return "OTHER";
        }
      return "UNKNOWN";
     }

   static ENUM_DIAG_EXIT ReasonToExitType(const long reason)
     {
      if(reason == DEAL_REASON_SL)
         return DIAG_EXIT_SL;
      if(reason == DEAL_REASON_TP)
         return DIAG_EXIT_TP;
      if(reason == DEAL_REASON_EXPERT)
         return DIAG_EXIT_BASKET;
      return DIAG_EXIT_OTHER;
     }

   int               FindOpenIndex(const ulong ticket) const
     {
      for(int i = 0; i < ArraySize(m_opens); i++)
        {
         if(m_opens[i].ticket == ticket)
            return i;
        }
      return -1;
     }

   void              RemoveOpen(const int index)
     {
      const int n = ArraySize(m_opens);
      if(index < 0 || index >= n)
         return;
      for(int i = index; i < n - 1; i++)
         m_opens[i] = m_opens[i + 1];
      ArrayResize(m_opens, n - 1);
     }

   void              PushClosed(const DiagClosedTrade &rec)
     {
      const int n = ArraySize(m_closed);
      ArrayResize(m_closed, n + 1);
      m_closed[n] = rec;
     }

   string            TradeCsvPath() const
     {
      return m_prefix + "_trades_" + m_symbol + ".csv";
     }

   string            SummaryCsvPath() const
     {
      return m_prefix + "_summary_" + m_symbol + ".csv";
     }

   bool              WriteTradesCsv() const
     {
      const string path = TradeCsvPath();
      const int handle = FileOpen(path, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(handle == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.LogError("Diagnostics: cannot open " + path + " err=" + IntegerToString(GetLastError()));
         return false;
        }

      FileWrite(handle,
                "ticket", "basket_id", "level", "levels_at_open", "basket_max_levels",
                "direction", "hour", "weekday", "weekday_name", "month", "year",
                "session", "bad_hour", "adx", "atr", "profit", "hold_sec",
                "exit_reason", "open_time", "close_time");

      for(int i = 0; i < ArraySize(m_closed); i++)
        {
         const DiagClosedTrade r = m_closed[i];
         FileWrite(handle,
                   (string)r.ticket, (string)r.basket_id, (string)r.level_index,
                   (string)r.levels_at_open, (string)r.basket_max_levels,
                   r.direction, (string)r.hour, (string)r.weekday, r.weekday_name,
                   (string)r.month, (string)r.year, r.session_tag,
                   r.bad_hour ? "1" : "0",
                   DoubleToString(r.adx, 4), DoubleToString(r.atr, 6),
                   DoubleToString(r.profit, 2), (string)r.hold_seconds,
                   r.exit_reason, TimeToString(r.open_time), TimeToString(r.close_time));
        }

      FileClose(handle);
      return true;
     }

   void              AggregateBucket(const string label, const int &indices[],
                                     const int count,
                                     int &out_trades, int &out_wins,
                                     double &out_pl) const
     {
      out_trades = count;
      out_wins = 0;
      out_pl = 0.0;
      for(int i = 0; i < count; i++)
        {
         const int idx = indices[i];
         out_pl += m_closed[idx].profit;
         if(m_closed[idx].profit > 0.0)
            out_wins++;
        }
     }

   void              WriteSummaryCsv() const
     {
      const string path = SummaryCsvPath();
      const int handle = FileOpen(path, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(handle == INVALID_HANDLE)
         return;

      FileWrite(handle, "section", "bucket", "trades", "wins", "win_rate_pct", "total_pl");

      //--- EDGE-002: by leg level
      for(int lvl = 0; lvl <= 6; lvl++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].level_index == lvl)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "level_leg", "L" + IntegerToString(lvl),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      //--- by basket max depth
      for(int depth = 1; depth <= 6; depth++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].basket_max_levels == depth)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "basket_depth", "D" + IntegerToString(depth),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      //--- by hour
      for(int h = 0; h < 24; h++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].hour == h)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "hour", IntegerToString(h),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      //--- by weekday
      for(int d = 0; d < 7; d++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].weekday == d)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "weekday", WeekdayName(d),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      //--- by exit type
      for(int e = DIAG_EXIT_SL; e <= DIAG_EXIT_OTHER; e++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].exit_type == (ENUM_DIAG_EXIT)e)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "exit", ExitTypeToString((ENUM_DIAG_EXIT)e),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      //--- by month (EDGE-003 support)
      for(int m = 1; m <= 12; m++)
        {
         int idxs[];
         int cnt = 0;
         for(int i = 0; i < ArraySize(m_closed); i++)
           {
            if(m_closed[i].month == m)
              {
               ArrayResize(idxs, cnt + 1);
               idxs[cnt++] = i;
              }
           }
         if(cnt == 0)
            continue;
         int trades, wins;
         double pl;
         AggregateBucket("", idxs, cnt, trades, wins, pl);
         const double wr = (trades > 0) ? 100.0 * wins / trades : 0.0;
         FileWrite(handle, "month", IntegerToString(m),
                   (string)trades, (string)wins, DoubleToString(wr, 1), DoubleToString(pl, 2));
        }

      FileClose(handle);
     }

   void              PrintGateAnalysis() const
     {
      double total_loss = 0.0;
      double loss_deep_basket = 0.0;
      double loss_bad_hour = 0.0;
      int loss_count = 0;

      for(int i = 0; i < ArraySize(m_closed); i++)
        {
         if(m_closed[i].profit >= 0.0)
            continue;
         loss_count++;
         const double abs_loss = MathAbs(m_closed[i].profit);
         total_loss += abs_loss;
         if(m_closed[i].basket_max_levels >= 3)
            loss_deep_basket += abs_loss;
         if(m_closed[i].bad_hour)
            loss_bad_hour += abs_loss;
        }

      const double pct_deep = (total_loss > 0.0) ? 100.0 * loss_deep_basket / total_loss : 0.0;
      const double pct_bad  = (total_loss > 0.0) ? 100.0 * loss_bad_hour / total_loss : 0.0;
      const bool gate_pass = (pct_deep >= 60.0 || pct_bad >= 60.0);

      Print("========== AAG E0 GATE ANALYSIS (EDGE-001/002) ==========");
      Print("Closed trades logged: ", ArraySize(m_closed));
      Print("Losing trades: ", loss_count, " | Total loss $: ", DoubleToString(total_loss, 2));
      Print("Loss from baskets depth>=3: ", DoubleToString(pct_deep, 1), "% ($",
            DoubleToString(loss_deep_basket, 2), ")");
      Print("Loss from bad hours (9,16,18-19,21-22): ", DoubleToString(pct_bad, 1), "% ($",
            DoubleToString(loss_bad_hour, 2), ")");
      Print("E0 Gate (>=60% one factor): ", gate_pass ? "PASS — proceed to E1" : "INCONCLUSIVE — review CSV");
      Print("CSV trades: ", TradeCsvPath(), " (FILE_COMMON)");
      Print("CSV summary: ", SummaryCsvPath(), " (FILE_COMMON)");
      Print("=========================================================");
     }

public:
                     CDiagnostics() :
                     m_symbol(""),
                     m_magic(0),
                     m_enabled(false),
                     m_csv(true),
                     m_prefix("AAG_diag"),
                     m_log(NULL),
                     m_basket_id(0),
                     m_basket_max_levels(0),
                     m_pending_basket_close("")
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   void              Init(const string symbol, const ulong magic,
                          const bool enabled, const bool csv,
                          const string prefix)
     {
      m_symbol = symbol;
      m_magic = magic;
      m_enabled = enabled;
      m_csv = csv;
      m_prefix = prefix;
      ArrayResize(m_opens, 0);
      ArrayResize(m_closed, 0);
      m_basket_id = 0;
      m_basket_max_levels = 0;
     }

   bool              IsEnabled() const { return m_enabled; }

   void              OnBasketStart()
     {
      if(!m_enabled)
         return;
      m_basket_id++;
      m_basket_max_levels = 1;
      m_pending_basket_close = "";
     }

   void              OnLevelAdded(const int total_levels)
     {
      if(!m_enabled)
         return;
      if(total_levels > m_basket_max_levels)
         m_basket_max_levels = total_levels;
     }

   void              OnBasketClosePending(const string reason)
     {
      if(!m_enabled)
         return;
      m_pending_basket_close = reason;
     }

   void              RecordOpen(const ulong ticket, const int level_index,
                                const ENUM_TRADE_BIAS bias,
                                const double adx, const double atr,
                                const int levels_in_basket)
     {
      if(!m_enabled || ticket == 0)
         return;

      if(levels_in_basket > m_basket_max_levels)
         m_basket_max_levels = levels_in_basket;

      DiagOpenCtx ctx;
      ctx.ticket = ticket;
      ctx.basket_id = m_basket_id;
      ctx.level_index = level_index;
      ctx.levels_at_open = levels_in_basket;
      ctx.bias = bias;
      ctx.adx = adx;
      ctx.atr = atr;
      ctx.open_time = TimeCurrent();
      ctx.basket_max_levels = m_basket_max_levels;

      const int n = ArraySize(m_opens);
      ArrayResize(m_opens, n + 1);
      m_opens[n] = ctx;
     }

   void              OnTradeTransaction(const MqlTradeTransaction &trans)
     {
      if(!m_enabled)
         return;
      if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
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

      const ulong position_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      const int oi = FindOpenIndex(position_id);
      if(oi < 0)
         return;

      const DiagOpenCtx ctx = m_opens[oi];
      const datetime close_time = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      MqlDateTime dt;
      TimeToStruct(ctx.open_time, dt);

      DiagClosedTrade rec;
      rec.ticket = ctx.ticket;
      rec.basket_id = ctx.basket_id;
      rec.level_index = ctx.level_index;
      rec.levels_at_open = ctx.levels_at_open;
      rec.basket_max_levels = m_basket_max_levels;
      rec.direction = (ctx.bias == BIAS_BUY) ? "BUY" : "SELL";
      rec.hour = dt.hour;
      rec.weekday = dt.day_of_week;
      rec.weekday_name = WeekdayName(dt.day_of_week);
      rec.month = dt.mon;
      rec.year = dt.year;
      rec.session_tag = SessionTag(dt.hour);
      rec.bad_hour = IsBadHour(dt.hour);
      rec.adx = ctx.adx;
      rec.atr = ctx.atr;
      rec.profit = HistoryDealGetDouble(deal, DEAL_PROFIT) +
                   HistoryDealGetDouble(deal, DEAL_SWAP) +
                   HistoryDealGetDouble(deal, DEAL_COMMISSION);
      rec.hold_seconds = (int)(close_time - ctx.open_time);
      rec.open_time = ctx.open_time;
      rec.close_time = close_time;

      const long reason = HistoryDealGetInteger(deal, DEAL_REASON);
      rec.exit_type = ReasonToExitType(reason);
      if(m_pending_basket_close != "" && rec.exit_type == DIAG_EXIT_BASKET)
         rec.exit_reason = m_pending_basket_close;
      else
         rec.exit_reason = ExitTypeToString(rec.exit_type);

      PushClosed(rec);
      RemoveOpen(oi);
     }

   void              Flush()
     {
      if(!m_enabled)
         return;

      if(m_csv)
        {
         WriteTradesCsv();
         WriteSummaryCsv();
        }
      PrintGateAnalysis();
     }
  };

#endif // AAG_DIAGNOSTICS_MQH
