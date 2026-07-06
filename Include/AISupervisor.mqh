//+------------------------------------------------------------------+
//| AISupervisor.mqh — Phase E8 AI supervisor (LOCK-AI + AI-804 wired)  |
//+------------------------------------------------------------------+
#ifndef AAG_AISUPERVISOR_MQH
#define AAG_AISUPERVISOR_MQH

#include "ATREngine.mqh"
#include "Logger.mqh"
#include "AIHealthModel.mqh"
#include "AIRegimeModel.mqh"
#include "AIEntryContextModel.mqh"
#include "AIStackRiskModel.mqh"

#include "AIModelRuntime.mqh"

#define AI_MEMORY_WINDOW           20
#define AI_MEMORY_MIN_BASKETS      5
#define AI_MEMORY_PF_FLOOR         1.15
#define AI_MEMORY_PF_RECOVERY      1.50
#define AI_MEMORY_WR_RECOVERY      0.68
#define AI_MEMORY_THROTTLE_MULT    0.80
#define AI_MEMORY_RECOVERY_STEP    0.05
#define AI_MEMORY_MAX_LEVELS_CAP   5
#define AI_MEMORY_MAX_LEVELS_FLOOR 4
#define AI_MEMORY_LOSS_MULT        2.00
#define AI_ENTRY_BLOCK_CONF_MIN    0.90
#define AI_ENTRY_SPACING_WEAK      0.25
#define AI_ENTRY_PF_CAP            8.0    // training rolling_pf_20 max ~7.7; live uses 99 when no losses
#define AI_ENTRY_COLD_START_MED_WR 0.60
#define AI_ENTRY_COLD_START_MED_PF 1.13
#define AI_ENTRY_COLD_START_MED_DD 4.66
#define AI_HEALTH_TIGHTEN_THRESHOLD 72.0
#define AI_HEALTH_STRESS_FLATTEN_THRESHOLD 75.0
#define AI_HEALTH_TRIM_PROFIT       8.0

enum ENUM_AI_REGIME_STATE
  {
   AI_REGIME_UNKNOWN     = 0,
   AI_REGIME_COMPRESSION = 1,
   AI_REGIME_ROTATION    = 2,
   AI_REGIME_EXPANSION   = 3,
   AI_REGIME_TREND       = 4
  };

struct AIPolicy
  {
   double            lot_mult;
   int               max_levels;
   double            spacing_mult;
   double            tp_atr_mult;
   double            cooldown_mult;
   bool              allow_new_basket;
   bool              allow_add_level;
   bool              flatten_basket;
   double            entry_score;
   double            entry_confidence;
   double            health_score;
   ENUM_AI_REGIME_STATE regime_state;
   double            regime_confidence;
   string            reason;
  };

class CAISupervisor
  {
private:
   string            m_symbol;
   ENUM_TIMEFRAMES   m_tf;
   CLogger          *m_log;
   bool              m_initialized;
   CAIModelRuntime   m_runtime;
   bool              m_runtime_ok;

   double            m_basket_pnls[];
   int               m_basket_count;
   double            m_global_risk_mult;
   double            m_historical_avg_loss;
   int               m_loss_count;
   bool              m_memory_throttled;
   double            m_last_rolling_pf;
   double            m_last_rolling_wr;
   double            m_basket_adx0;
   double            m_basket_atr0;
   bool              m_health_trim_done;
   datetime          m_last_health_check;
   double            m_prior_day_atr_max;
   double            m_today_max_atr;
   int               m_last_yday;

   static bool       IsBadHourEntry(const int hour)
     {
      return hour == 9 || hour == 16 ||
             hour == 18 || hour == 19 ||
             hour == 21 || hour == 22;
     }

   static bool       IsSessionLondon(const int hour)
     {
      return hour >= 8 && hour < 16;
     }

   static bool       IsSessionNY(const int hour)
     {
      return hour >= 16 && hour < 22;
     }

   void              RecordBasketPnl(const double basket_pnl)
     {
      if(m_basket_count < AI_MEMORY_WINDOW)
        {
         ArrayResize(m_basket_pnls, m_basket_count + 1);
         m_basket_pnls[m_basket_count] = basket_pnl;
         m_basket_count++;
        }
      else
        {
         for(int i = 0; i < AI_MEMORY_WINDOW - 1; i++)
            m_basket_pnls[i] = m_basket_pnls[i + 1];
         m_basket_pnls[AI_MEMORY_WINDOW - 1] = basket_pnl;
         m_basket_count = AI_MEMORY_WINDOW;
        }

      if(basket_pnl < 0.0)
        {
         m_loss_count++;
         const double abs_loss = MathAbs(basket_pnl);
         if(m_loss_count == 1)
            m_historical_avg_loss = abs_loss;
         else
            m_historical_avg_loss += (abs_loss - m_historical_avg_loss) / (double)m_loss_count;
        }
     }

   int               ConsecutiveLosses() const
     {
      int streak = 0;
      for(int i = m_basket_count - 1; i >= 0; i--)
        {
         if(m_basket_pnls[i] < 0.0)
            streak++;
         else
            break;
        }
      return streak;
     }

   double            RollingPfRecent(const int window) const
     {
      const int n = MathMin(m_basket_count, window);
      if(n <= 0)
         return 1.0;
      double pf = 1.0;
      double wr = 0.0;
      double max_loss = 0.0;
      ComputeRolling(n, pf, wr, max_loss);
      return pf;
     }

   double            RollingWrRecent(const int window) const
     {
      const int n = MathMin(m_basket_count, window);
      if(n <= 0)
         return 0.0;
      double pf = 1.0;
      double wr = 0.0;
      double max_loss = 0.0;
      ComputeRolling(n, pf, wr, max_loss);
      return wr;
     }

   void              UpdateDailyATR(const double atr)
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      const int yday = dt.day_of_year;
      if(m_last_yday >= 0 && yday != m_last_yday)
        {
         m_prior_day_atr_max = m_today_max_atr;
         m_today_max_atr = atr;
        }
      else
        {
         if(atr > m_today_max_atr)
            m_today_max_atr = atr;
        }
      m_last_yday = yday;
     }

   double            ATRPercentile100(CATREngine &atr_engine, const double atr_now) const
     {
      const int lookback = 100;
      double atr[];
      if(!atr_engine.GetATRSeries(atr, lookback + 1) || ArraySize(atr) < lookback + 1)
         return 1.0;

      double sorted[];
      ArrayResize(sorted, lookback);
      for(int i = 0; i < lookback; i++)
         sorted[i] = atr[i + 1];

      ArraySort(sorted);
      const int mid = lookback / 2;
      const double med = sorted[mid];
      if(med <= 0.0)
         return 1.0;
      return atr_now / med;
     }

   double            RollingAvgLossRecent(const int window) const
     {
      const int n = MathMin(m_basket_count, window);
      if(n <= 0)
         return 0.0;
      double sum = 0.0;
      int cnt = 0;
      const int start = m_basket_count - n;
      for(int i = start; i < m_basket_count; i++)
        {
         if(m_basket_pnls[i] < 0.0)
           {
            sum += MathAbs(m_basket_pnls[i]);
            cnt++;
           }
        }
      return (cnt > 0) ? sum / (double)cnt : 0.0;
     }

   int               SessionMinuteInWindow(const MqlDateTime &dt) const
     {
      const int minutes = dt.hour * 60 + dt.min;
      const int start = 15 * 60;
      const int end = 17 * 60;
      const int clipped = (int)MathMax(start, MathMin(minutes, end));
      return clipped - start;
     }

   int               WeekdayPandas(const MqlDateTime &dt) const
     {
      // MQL: 0=Sun..6=Sat — training uses pandas 0=Mon..6=Sun
      return (dt.day_of_week + 6) % 7;
     }

   double            CapEntryPf(const double pf) const
     {
      if(!MathIsValidNumber(pf) || pf <= 0.0)
         return AI_ENTRY_COLD_START_MED_PF;
      return MathMin(pf, AI_ENTRY_PF_CAP);
     }

   double            EntryRollingWr10() const
     {
      if(m_basket_count < AI_MEMORY_MIN_BASKETS)
         return AI_ENTRY_COLD_START_MED_WR;
      return RollingWrRecent(10);
     }

   double            EntryRollingWr20() const
     {
      if(m_basket_count < AI_MEMORY_MIN_BASKETS)
         return AI_ENTRY_COLD_START_MED_WR;
      return RollingWrRecent(20);
     }

   double            EntryRollingPf20() const
     {
      if(m_basket_count < AI_MEMORY_MIN_BASKETS)
         return AI_ENTRY_COLD_START_MED_PF;
      return CapEntryPf(RollingPfRecent(20));
     }

   double            EntryRollingAvgDd20() const
     {
      if(m_basket_count < AI_MEMORY_MIN_BASKETS)
         return AI_ENTRY_COLD_START_MED_DD;
      const double dd = RollingAvgLossRecent(20);
      return (dd > 0.0) ? dd : AI_ENTRY_COLD_START_MED_DD;
     }

   double            EntryWinProb(const ENUM_TRADE_BIAS bias, CATREngine &atr_engine) const
     {
      const double adx = atr_engine.GetADX();
      const double atr = atr_engine.GetATR();
      const double atr_pips = atr * 10000.0;
      const double atr_pct = ATRPercentile100(atr_engine, atr);

      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);

      double f[AI_ENTRY_FEATURE_COUNT];
      f[AIEntry_ADX] = adx;
      f[AIEntry_ATR] = atr;
      f[AIEntry_ATR_PIPS] = atr_pips;
      f[AIEntry_ATR_PCT_100] = atr_pct;
      f[AIEntry_HOUR] = (double)dt.hour;
      f[AIEntry_MINUTE_IN_SESSION] = (double)SessionMinuteInWindow(dt);
      f[AIEntry_WEEKDAY] = (double)WeekdayPandas(dt);
      f[AIEntry_MONTH] = (double)dt.mon;
      f[AIEntry_BIAS_BUY] = (bias == BIAS_BUY) ? 1.0 : 0.0;
      f[AIEntry_BAD_HOUR] = IsBadHourEntry(dt.hour) ? 1.0 : 0.0;
      f[AIEntry_ROLLING_WR_10] = EntryRollingWr10();
      f[AIEntry_ROLLING_WR_20] = EntryRollingWr20();
      f[AIEntry_ROLLING_PF_20] = EntryRollingPf20();
      f[AIEntry_ROLLING_AVG_DD_20] = EntryRollingAvgDd20();

      return AIEntryWinProb(f);
     }

   void              ApplyEntryContextPolicy(AIPolicy &p, const double p_win) const
     {
      if(!MasterEnabled() || !InpAIEntryContextEnabled)
         return;

      p.entry_score = p_win;
      p.entry_confidence = MathMax(p_win, 1.0 - p_win);

      const double lot_from_edge = InpAILotMultMin +
                                   (InpAILotMultMax - InpAILotMultMin) * p_win;
      p.lot_mult = lot_from_edge;
      p.max_levels = 4 + (int)MathRound(2.0 * p_win);
      p.max_levels = (int)MathMax(4.0, MathMin((double)InpMaxGridLevels, (double)p.max_levels));
      p.spacing_mult = 1.0 + AI_ENTRY_SPACING_WEAK * (1.0 - p_win);
      p.reason = "ai_entry_context";

      if(p_win < InpAIEntryBlockFloor && p.entry_confidence >= AI_ENTRY_BLOCK_CONF_MIN)
        {
         p.allow_new_basket = false;
         p.reason = "ai_entry_block";
        }
     }

   double            BadBasketProb(const ENUM_TRADE_BIAS bias, CATREngine &atr_engine) const
     {
      const double adx = atr_engine.GetADX();
      const double atr = atr_engine.GetATR();
      const double atr_pips = atr * 10000.0;
      const double atr_pct = ATRPercentile100(atr_engine, atr);

      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);

      const double rolling_pf = RollingPfRecent(10);
      const double rolling_wr = RollingWrRecent(10);
      const int rotation = (atr_pct >= 0.90 && atr_pct <= 1.10) ? 1 : 0;

      double f[AI_REGIME_FEATURE_COUNT];
      f[AIRegime_ADX] = adx;
      f[AIRegime_ATR] = atr;
      f[AIRegime_ATR_PIPS] = atr_pips;
      f[AIRegime_ATR_PCT_100] = atr_pct;
      f[AIRegime_HOUR] = (double)dt.hour;
      f[AIRegime_WEEKDAY] = (double)dt.day_of_week;
      f[AIRegime_MONTH] = (double)dt.mon;
      f[AIRegime_BIAS_BUY] = (bias == BIAS_BUY) ? 1.0 : 0.0;
      f[AIRegime_BAD_HOUR] = IsBadHourEntry(dt.hour) ? 1.0 : 0.0;
      f[AIRegime_ROLLING_PF_7D] = rolling_pf;
      f[AIRegime_ROLLING_WR_10] = rolling_wr;
      f[AIRegime_CONSEC_LOSSES] = (double)ConsecutiveLosses();
      f[AIRegime_PRIOR_DAY_ATR_MAX] = m_prior_day_atr_max;
      f[AIRegime_LABEL_REGIME_ROTATION] = (double)rotation;

      return AIRegimeBadBasketProb(f);
     }

   double            DistAnchorATR(const double anchor, const ENUM_TRADE_BIAS bias,
                                   const double atr) const
     {
      if(anchor <= 0.0 || atr <= 0.0 || bias == BIAS_NONE)
         return 0.0;
      const double price = (bias == BIAS_BUY) ?
                           SymbolInfoDouble(m_symbol, SYMBOL_BID) :
                           SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      return MathAbs(price - anchor) / atr;
     }

   double            RuleHealthScore(const double floating_pl, const int open_count,
                                     const int seconds_open,
                                     const double dist_anchor_atr) const
     {
      double h = 0.0;
      if(floating_pl < 0.0)
         h += MathMin(45.0, MathAbs(floating_pl) * 3.0);
      if(open_count >= 2)
         h += 20.0;
      if(open_count >= 1 && floating_pl < -10.0)
         h += 15.0;
      if(seconds_open > 2400)
         h += 10.0;
      if(seconds_open > 5400)
         h += 15.0;
      if(dist_anchor_atr > 1.25)
         h += MathMin(25.0, (dist_anchor_atr - 1.0) * 15.0);
      return MathMin(100.0, h);
     }

   double            StressHealthScore(const double floating_pl, const int open_count) const
     {
      double h = 0.0;
      if(floating_pl < 0.0)
         h += MathMin(45.0, MathAbs(floating_pl) * 3.0);
      if(open_count >= 2)
         h += 20.0;
      if(open_count >= 1 && floating_pl < -10.0)
         h += 15.0;
      return MathMin(100.0, h);
     }

   double            ModelHealthScore(const double floating_pl, const int open_count,
                                      const int seconds_open, const double atr_delta,
                                      const double adx_delta,
                                      const double dist_anchor_atr) const
     {
      double f[AI_HEALTH_FEATURE_COUNT];
      f[AI_HEALTH_F_GRID_DEPTH] = (double)open_count;
      f[AI_HEALTH_F_FLOATING_PL] = floating_pl;
      f[AI_HEALTH_F_SECONDS_OPEN] = (double)seconds_open;
      f[AI_HEALTH_F_ATR_DELTA] = atr_delta;
      f[AI_HEALTH_F_ADX_DELTA] = adx_delta;
      f[AI_HEALTH_F_DIST_ANCHOR_ATR] = dist_anchor_atr;
      f[AI_HEALTH_F_MFE_SO_FAR] = MathMax(0.0, floating_pl);
      f[AI_HEALTH_F_MAE_SO_FAR] = MathMin(0.0, floating_pl);
      return AIHealthScoreFromFeatures(f);
     }

   void              ApplyHealthPolicy(AIPolicy &p, const double health_score,
                                       const int open_count, const double floating_pl,
                                       const int seconds_open) const
     {
      if(!MasterEnabled() || !InpAIBasketHealthEnabled)
         return;

      p.health_score = health_score;
      const double flatten_at = InpAIHealthFlattenThreshold;
      const double no_add_at = InpAIHealthNoAddThreshold;
      const double flatten_float = InpAIHealthFlattenFloatUSD;

      // Hard tail cap — D2 protection, no health score
      string cap_reason = "";
      if(MatchesHardCap(open_count, floating_pl, seconds_open, cap_reason))
        {
         p.flatten_basket = true;
         p.allow_add_level = false;
         p.reason = cap_reason;
         return;
        }

      if(InpAIHealthFlattenOnly)
        {
         const double stress_h = StressHealthScore(floating_pl, open_count);
         p.health_score = stress_h;
         if(stress_h > AI_HEALTH_STRESS_FLATTEN_THRESHOLD &&
            open_count >= 2 &&
            floating_pl < flatten_float &&
            seconds_open >= 120)
           {
            p.flatten_basket = true;
            p.allow_add_level = false;
            p.reason = "ai_health_flatten";
           }
         else
           {
            p.reason = "ai_health_ok";
           }
         return;
        }

      // Full policy — time/distance contribute to health score
      if(health_score > flatten_at &&
         open_count >= 2 &&
         floating_pl < flatten_float &&
         seconds_open >= 120)
        {
         p.flatten_basket = true;
         p.allow_add_level = false;
         p.reason = "ai_health_flatten";
        }
      else if(!InpAIHealthFlattenOnly && health_score > AI_HEALTH_TIGHTEN_THRESHOLD && open_count >= 2)
        {
         p.tp_atr_mult = 1.25;
         p.allow_add_level = false;
         p.reason = "ai_health_tighten";
        }
      else if(!InpAIHealthFlattenOnly && health_score > no_add_at && open_count >= 1)
        {
         p.allow_add_level = false;
         p.reason = "ai_health_no_add";
        }
      else
        {
         p.reason = "ai_health_ok";
        }
     }

   AIPolicy          NeutralPolicy() const
     {
      AIPolicy p;
      p.lot_mult = 1.0;
      p.max_levels = InpMaxGridLevels;
      p.spacing_mult = 1.0;
      p.tp_atr_mult = InpTPATRMult;
      p.cooldown_mult = 1.0;
      p.allow_new_basket = true;
      p.allow_add_level = true;
      p.flatten_basket = false;
      p.entry_score = 0.5;
      p.entry_confidence = 0.0;
      p.health_score = 0.0;
      p.regime_state = AI_REGIME_ROTATION;
      p.regime_confidence = 0.0;
      p.reason = "ai_neutral";
      return p;
     }

   bool              MasterEnabled() const
     {
      return InpAIEnabled && m_runtime_ok;
     }

   void              ResetMemoryState()
     {
      ArrayResize(m_basket_pnls, 0);
      m_basket_count = 0;
      m_global_risk_mult = 1.0;
      m_historical_avg_loss = 0.0;
      m_loss_count = 0;
      m_memory_throttled = false;
      m_last_rolling_pf = 1.0;
      m_last_rolling_wr = 0.0;
      m_basket_adx0 = 0.0;
      m_basket_atr0 = 0.0;
      m_health_trim_done = false;
      m_last_health_check = 0;
      m_prior_day_atr_max = 0.0;
      m_today_max_atr = 0.0;
      m_last_yday = -1;
     }

   void              ComputeRolling(const int n, double &pf, double &wr,
                                    double &max_loss) const
     {
      pf = 1.0;
      wr = 0.0;
      max_loss = 0.0;
      if(n <= 0)
         return;

      double wins = 0.0;
      double losses = 0.0;
      int win_count = 0;

      for(int i = 0; i < n; i++)
        {
         const double pnl = m_basket_pnls[i];
         if(pnl > 0.0)
           {
            wins += pnl;
            win_count++;
           }
         else
            losses += MathAbs(pnl);
         if(pnl < max_loss)
            max_loss = pnl;
        }

      wr = (double)win_count / (double)n;
      if(losses > 0.0)
         pf = wins / losses;
      else if(wins > 0.0)
         pf = 99.0;
     }

   void              UpdateMemoryState()
     {
      if(!InpAIMemoryEnabled)
         return;

      const int n = MathMin(m_basket_count, AI_MEMORY_WINDOW);
      if(n < AI_MEMORY_MIN_BASKETS)
        {
         m_memory_throttled = false;
         return;
        }

      double pf = 1.0;
      double wr = 0.0;
      double max_loss = 0.0;
      ComputeRolling(n, pf, wr, max_loss);
      m_last_rolling_pf = pf;
      m_last_rolling_wr = wr;

      const bool loss_spike = (m_historical_avg_loss > 0.0 &&
                               MathAbs(max_loss) > AI_MEMORY_LOSS_MULT * m_historical_avg_loss);
      const bool throttle = (pf < 1.0) || (loss_spike && pf < AI_MEMORY_PF_FLOOR);

      if(throttle)
        {
         m_global_risk_mult = MathMax(InpAILotMultMin, AI_MEMORY_THROTTLE_MULT);
         m_memory_throttled = true;
         if(m_log != NULL)
            m_log.LogInfo("AI-803 memory throttle PF=" + DoubleToString(pf, 2) +
                          " WR=" + DoubleToString(wr * 100.0, 1) + "% lot_mult=" +
                          DoubleToString(m_global_risk_mult, 2));
        }
      else if(pf > AI_MEMORY_PF_RECOVERY && wr > AI_MEMORY_WR_RECOVERY)
        {
         m_global_risk_mult = MathMin(InpAILotMultMax,
                                      m_global_risk_mult + AI_MEMORY_RECOVERY_STEP);
         m_memory_throttled = false;
         if(m_log != NULL && m_global_risk_mult < InpAILotMultMax)
            m_log.LogInfo("AI-803 memory recovery PF=" + DoubleToString(pf, 2) +
                          " lot_mult=" + DoubleToString(m_global_risk_mult, 2));
        }
      else
        {
         m_memory_throttled = false;
        }
     }

   void              ApplyMemoryPolicy(AIPolicy &p) const
     {
      if(!MasterEnabled() || !InpAIMemoryEnabled)
         return;

      if(m_memory_throttled)
        {
         p.lot_mult = MathMin(p.lot_mult, m_global_risk_mult);
         p.max_levels = MathMax(AI_MEMORY_MAX_LEVELS_FLOOR,
                                MathMin(p.max_levels,
                                        MathMin(InpMaxGridLevels, AI_MEMORY_MAX_LEVELS_CAP)));
         p.reason = "ai_memory_throttle";
        }
     }

public:
                     CAISupervisor() :
                     m_symbol(""),
                     m_tf(PERIOD_CURRENT),
                     m_log(NULL),
                     m_initialized(false),
                     m_runtime_ok(true),
                     m_basket_count(0),
                     m_global_risk_mult(1.0),
                     m_historical_avg_loss(0.0),
                     m_loss_count(0),
                     m_memory_throttled(false),
                     m_last_rolling_pf(1.0),
                     m_last_rolling_wr(0.0)
     {
      ResetMemoryState();
     }

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   bool              Init(const string symbol, const ENUM_TIMEFRAMES tf)
     {
      m_symbol = symbol;
      m_tf = tf;
      ResetMemoryState();
      m_runtime.SetLogger(*m_log);
      m_runtime_ok = m_runtime.Init();
      if(InpAIEnabled && !m_runtime_ok)
        {
         if(m_log != NULL)
            m_log.LogError("AI-808 fallback LOCK-202 — " + m_runtime.FailReason());
        }
      m_initialized = true;

      if(m_log != NULL && InpAIPhysicsStackEnabled && !MasterEnabled())
         m_log.LogInfo("AI-809 physics stack gate — model=" + AI_STACK_RISK_MODEL_VERSION +
                       " thr=" + DoubleToString(InpAIPhysicsStackThreshold, 2));

      if(m_log != NULL && MasterEnabled())
        {
         if(InpAIMemoryEnabled)
            m_log.LogInfo("AI-803 performance memory active");
         else if(InpAIBasketHealthEnabled)
           {
            m_log.LogInfo("AI-805 basket health active — model=" + AI_HEALTH_MODEL_VERSION);
            if(InpAIHealthHardCapEnabled)
               m_log.LogInfo("AI-805 hard cap L2=" + DoubleToString(InpAIHealthHardCapUSD, 1) +
                             " L1=" + (InpAIHealthHardCapL1Enabled ?
                                       DoubleToString(InpAIHealthHardCapL1USD, 1) : "off"));
            if(InpAIHealthBasketCapEnabled)
               m_log.LogInfo("AI-805 basket cap=" + DoubleToString(InpAIHealthBasketCapUSD, 1) +
                             " minLegs=" + IntegerToString(InpAIHealthBasketCapMinLegs));
            if(InpAIHealthSLCascadeEnabled)
               m_log.LogInfo("AI-805 SL cascade loss=" +
                             DoubleToString(InpAIHealthSLCascadeLossUSD, 1) +
                             " stack=" + DoubleToString(InpAIHealthSLCascadeStackUSD, 1) +
                             (InpAIHealthSLCascadeAnyPartial ? " anyPartial=1" : ""));
            if(InpAIRegimeEnabled)
               m_log.LogInfo("AI-806 regime skip prob>=" +
                             DoubleToString(InpAIRegimeTrendSkipProb, 2) +
                             " model=" + AI_REGIME_MODEL_VERSION);
            if(InpAIEntryContextEnabled)
               m_log.LogInfo("AI-804 entry context model=" + AI_ENTRY_MODEL_VERSION);
           }
         else
            m_log.LogInfo("AI supervisor E8 — sub-modules off");
         m_log.LogInfo("AI-808 runtime mode=" + m_runtime.Mode());
        }

      return true;
     }

   void              Shutdown()
     {
      m_runtime.Shutdown();
      m_initialized = false;
     }

   bool              RuntimeOk() const { return m_runtime_ok; }
   string            RuntimeMode() const { return m_runtime.Mode(); }

   bool              IsInitialized() const { return m_initialized; }

   bool              IsActive() const
     {
      if(InpAIPhysicsStackEnabled)
         return true;
      if(!MasterEnabled())
         return false;
      return InpAIMemoryEnabled || InpAIEntryContextEnabled ||
             InpAIBasketHealthEnabled || InpAIRegimeEnabled;
     }

   AIPolicy          GetNeutralPolicy() const
     {
      return NeutralPolicy();
     }

   double            GetGlobalRiskMult() const { return m_global_risk_mult; }
   bool              IsMemoryThrottled() const { return m_memory_throttled; }

   AIPolicy          EvaluateEntry(const ENUM_TRADE_BIAS bias, CATREngine &atr_engine)
     {
      AIPolicy p = NeutralPolicy();
      if(!MasterEnabled())
         return p;

      UpdateDailyATR(atr_engine.GetATR());

      if(InpAIEntryContextEnabled)
        {
         const double p_win = EntryWinProb(bias, atr_engine);
         ApplyEntryContextPolicy(p, p_win);
        }

      ApplyMemoryPolicy(p);

      return p;
     }

   bool              AllowNewBasket(const ENUM_TRADE_BIAS bias, CATREngine &atr_engine,
                                      AIPolicy &policy, string &block_reason)
     {
      policy = EvaluateEntry(bias, atr_engine);
      block_reason = "";

      if(!MasterEnabled())
         return true;

      if(!policy.allow_new_basket)
        {
         block_reason = policy.reason;
         return false;
        }

      if(InpAIRegimeEnabled)
        {
         UpdateDailyATR(atr_engine.GetATR());
         const double p_bad = BadBasketProb(bias, atr_engine);
         policy.regime_confidence = p_bad;
         policy.regime_state = AI_REGIME_ROTATION;
         if(InpAIRegimeLogScore && p_bad >= 0.45 && m_log != NULL)
            m_log.LogInfo("AI-806 regime score p=" + DoubleToString(p_bad, 3) +
                          " thr=" + DoubleToString(InpAIRegimeTrendSkipProb, 2));
         if(p_bad >= InpAIRegimeTrendSkipProb)
           {
            block_reason = "ai_regime_skip p=" + DoubleToString(p_bad, 3);
            policy.allow_new_basket = false;
            policy.reason = block_reason;
            if(m_log != NULL)
               m_log.LogRiskReject(block_reason);
            return false;
           }
        }

      return true;
     }

   AIPolicy          EvaluateBasket(const double floating_pl, const int open_count,
                                    const int seconds_open, const double anchor,
                                    const ENUM_TRADE_BIAS bias,
                                    CATREngine &atr_engine)
     {
      AIPolicy p = NeutralPolicy();
      if(!MasterEnabled())
         return p;

      ApplyMemoryPolicy(p);

      if(InpAIBasketHealthEnabled && open_count > 0)
        {
         const double adx = atr_engine.GetADX();
         const double atr = atr_engine.GetATR();
         if(open_count <= 1 || m_basket_adx0 <= 0.0)
           {
            m_basket_adx0 = adx;
            m_basket_atr0 = atr;
           }

         const double dist = DistAnchorATR(anchor, bias, atr);
         const double rule_h = RuleHealthScore(floating_pl, open_count, seconds_open, dist);
         // Rules only — exported ML model miscalibrates live features (~89 on benign L0)
         const double health = rule_h;
         ApplyHealthPolicy(p, health, open_count, floating_pl, seconds_open);
        }

      return p;
     }

   bool              ShouldTrimBestLeg(const double health_score,
                                       const int open_count) const
     {
      return InpAIBasketHealthEnabled &&
             !InpAIHealthFlattenOnly &&
             open_count >= 2 &&
             !m_health_trim_done &&
             health_score > AI_HEALTH_TIGHTEN_THRESHOLD &&
             health_score <= InpAIHealthFlattenThreshold;
     }

   bool              MatchesHardCap(const int open_count,
                                    const double floating_pl,
                                    const int seconds_open,
                                    string &reason) const
     {
      reason = "";
      if(!MasterEnabled() || !InpAIBasketHealthEnabled || !InpAIHealthHardCapEnabled)
         return false;

      if(open_count >= 2 &&
         floating_pl < InpAIHealthHardCapUSD &&
         seconds_open >= 120)
        {
         reason = "ai_health_hard_cap";
         return true;
        }

      if(InpAIHealthHardCapL1Enabled &&
         open_count >= 1 &&
         floating_pl < InpAIHealthHardCapL1USD &&
         seconds_open >= InpAIHealthHardCapL1MinSec)
        {
         reason = "ai_health_hard_cap_l1";
         return true;
        }

      return false;
     }

   bool              ShouldBasketCapFlatten(const int open_count,
                                            const double total_pnl,
                                            string &reason) const
     {
      reason = "";
      if(!MasterEnabled() || !InpAIBasketHealthEnabled || !InpAIHealthBasketCapEnabled)
         return false;
      if(open_count < InpAIHealthBasketCapMinLegs)
         return false;
      if(total_pnl < InpAIHealthBasketCapUSD)
        {
         reason = "ai_health_basket_cap";
         return true;
        }
      return false;
     }

   bool              ShouldHardCapFlatten(const int open_count,
                                          const double floating_pl,
                                          const int seconds_open,
                                          string &reason) const
     {
      return MatchesHardCap(open_count, floating_pl, seconds_open, reason);
     }

   void              MarkHealthTrimDone() { m_health_trim_done = true; }

   bool              ShouldRunHealthCheck() const
     {
      if(InpAIHealthCheckSec <= 0)
         return true;
      if(m_last_health_check <= 0)
         return true;
      return (TimeCurrent() - m_last_health_check) >= InpAIHealthCheckSec;
     }

   void              MarkHealthCheckDone()
     {
      m_last_health_check = TimeCurrent();
     }

   void              OnBasketOpened(CATREngine &atr_engine)
     {
      if(!InpAIPhysicsStackEnabled && !InpAIBasketHealthEnabled)
         return;
      m_basket_adx0 = atr_engine.GetADX();
      m_basket_atr0 = atr_engine.GetATR();
     }

   bool              ShouldBlockStackAfterL0SL(const double l0_loss_usd,
                                               const double l0_mae_usd,
                                               const double l0_mfe_usd,
                                               const datetime basket_start,
                                               const datetime l0_close_time,
                                               const ENUM_TRADE_BIAS bias,
                                               double &prob_out) const
     {
      prob_out = 0.0;
      if(!InpAIPhysicsStackEnabled)
         return false;

      const double entry_adx = (m_basket_adx0 > 0.0) ? m_basket_adx0 : 18.0;
      const double entry_atr = (m_basket_atr0 > 0.0) ? m_basket_atr0 : 0.0006;
      const double atr_pips = entry_atr * 10000.0;
      const double hold_hours = (basket_start > 0 && l0_close_time > basket_start) ?
                                (double)(l0_close_time - basket_start) / 3600.0 : 0.4;

      MqlDateTime dt;
      TimeToStruct(l0_close_time, dt);

      double f[AI_STACK_RISK_FEATURE_COUNT];
      f[AIStack_ENTRY_ADX] = entry_adx;
      f[AIStack_ENTRY_ATR] = entry_atr;
      f[AIStack_ATR_PIPS] = atr_pips;
      f[AIStack_L0_HOLD_HOURS] = hold_hours;
      f[AIStack_L0_LOSS_USD] = l0_loss_usd;
      f[AIStack_L0_MAE_USD] = l0_mae_usd;
      f[AIStack_L0_MFE_USD] = l0_mfe_usd;
      f[AIStack_L0_MAE_ATR] = MathAbs(MathMin(l0_mae_usd, 0.0)) /
                              MathMax(atr_pips * 0.1, 0.01);
      f[AIStack_HOUR] = (double)dt.hour;
      f[AIStack_WEEKDAY] = (double)WeekdayPandas(dt);
      f[AIStack_BAD_HOUR] = IsBadHourEntry(dt.hour) ? 1.0 : 0.0;
      f[AIStack_BIAS_SELL] = (bias == BIAS_SELL) ? 1.0 : 0.0;
      f[AIStack_SESSION_LONDON] = IsSessionLondon(dt.hour) ? 1.0 : 0.0;
      f[AIStack_SESSION_NY] = IsSessionNY(dt.hour) ? 1.0 : 0.0;
      f[AIStack_ROLLING_PF_20] = EntryRollingPf20();
      f[AIStack_ROLLING_WR_20] = EntryRollingWr20();
      f[AIStack_CONSEC_LOSSES] = (double)ConsecutiveLosses();

      prob_out = AIStackRiskBlockProb(f);
      return prob_out >= InpAIPhysicsStackThreshold;
     }

   void              OnBasketClosed(const double basket_pnl)
     {
      m_basket_adx0 = 0.0;
      m_basket_atr0 = 0.0;
      m_health_trim_done = false;
      m_last_health_check = 0;

      const bool track_memory = MasterEnabled() && InpAIMemoryEnabled;
      const bool track_physics = InpAIPhysicsStackEnabled;
      if(track_memory || track_physics)
         RecordBasketPnl(basket_pnl);

      if(track_memory)
         UpdateMemoryState();
     }

   void              LogBlock(const string reason) const
     {
      if(m_log != NULL)
         m_log.LogRiskReject(reason);
     }

   static string     RegimeToString(const ENUM_AI_REGIME_STATE state)
     {
      switch(state)
        {
         case AI_REGIME_COMPRESSION: return "COMPRESSION";
         case AI_REGIME_ROTATION:    return "ROTATION";
         case AI_REGIME_EXPANSION:   return "EXPANSION";
         case AI_REGIME_TREND:       return "TREND";
        }
      return "UNKNOWN";
     }
  };

#endif // AAG_AISUPERVISOR_MQH
