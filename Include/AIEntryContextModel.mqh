//+------------------------------------------------------------------+
//| AIEntryContextModel.mqh — AI-804 entry win scorer
//| Auto-generated — do not edit manually                             |
//+------------------------------------------------------------------+
#ifndef AAG_AIENTRYCONTEXTMODEL_MQH
#define AAG_AIENTRYCONTEXTMODEL_MQH

#define AI_ENTRY_MODEL_VERSION "AI-804_v0"
#define AI_ENTRY_FEATURE_COUNT 14

#define AIEntry_ADX 0
#define AIEntry_ATR 1
#define AIEntry_ATR_PIPS 2
#define AIEntry_ATR_PCT_100 3
#define AIEntry_HOUR 4
#define AIEntry_MINUTE_IN_SESSION 5
#define AIEntry_WEEKDAY 6
#define AIEntry_MONTH 7
#define AIEntry_BIAS_BUY 8
#define AIEntry_BAD_HOUR 9
#define AIEntry_ROLLING_WR_10 10
#define AIEntry_ROLLING_WR_20 11
#define AIEntry_ROLLING_PF_20 12
#define AIEntry_ROLLING_AVG_DD_20 13

double AIEntryImputeMedian(const int idx)
  {
   static const double m[] = {
      18.20900000, 0.00049900, 4.99000000, 0.97405190, 16.00000000, 75.00000000, 2.00000000, 6.00000000, 0.00000000, 0.00000000, 0.60000000, 0.60000000, 1.13354701, 4.66000000
   };
   return (idx >= 0 && idx < AI_ENTRY_FEATURE_COUNT) ? m[idx] : 0.0;
  }

double AIEntryCoef(const int idx)
  {
   static const double c[] = {
      -0.08122168, 0.00000872, 0.08724877, 0.27577822, -0.35863704, 0.00836271, -0.07531662, 0.01528431, -0.03647902, -0.22510424, -0.21404236, -0.41721652, -0.05188543, -0.04452064
   };
   return (idx >= 0 && idx < AI_ENTRY_FEATURE_COUNT) ? c[idx] : 0.0;
  }

double AIEntryIntercept() { return 6.59618911; }

#ifndef AISIGMOIDPROB_DEFINED
#define AISIGMOIDPROB_DEFINED
double AISigmoidProb(const double x)
  {
   if(x > 20.0)  return 1.0;
   if(x < -20.0) return 0.0;
   return 1.0 / (1.0 + MathExp(-x));
  }
#endif

double AIEntryWinProb(const double &f[])
  {
   double logit = AIEntryIntercept();
   for(int i = 0; i < AI_ENTRY_FEATURE_COUNT; i++)
     {
      double v = f[i];
      if(!MathIsValidNumber(v))
         v = AIEntryImputeMedian(i);
      logit += AIEntryCoef(i) * v;
     }
   return AISigmoidProb(logit);
  }

#endif // AAG_AIENTRYCONTEXTMODEL_MQH
