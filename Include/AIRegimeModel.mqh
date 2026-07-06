//+------------------------------------------------------------------+
//| AIRegimeModel.mqh — AI-806 bad-basket skip scorer
//| Auto-generated — do not edit manually                             |
//+------------------------------------------------------------------+
#ifndef AAG_AIREGIMEMODEL_MQH
#define AAG_AIREGIMEMODEL_MQH

#ifndef AISIGMOIDPROB_DEFINED
#define AISIGMOIDPROB_DEFINED

#define AI_REGIME_MODEL_VERSION "AI-806_v0"
#define AI_REGIME_FEATURE_COUNT 14

#define AIRegime_ADX 0
#define AIRegime_ATR 1
#define AIRegime_ATR_PIPS 2
#define AIRegime_ATR_PCT_100 3
#define AIRegime_HOUR 4
#define AIRegime_WEEKDAY 5
#define AIRegime_MONTH 6
#define AIRegime_BIAS_BUY 7
#define AIRegime_BAD_HOUR 8
#define AIRegime_ROLLING_PF_7D 9
#define AIRegime_ROLLING_WR_10 10
#define AIRegime_CONSEC_LOSSES 11
#define AIRegime_PRIOR_DAY_ATR_MAX 12
#define AIRegime_LABEL_REGIME_ROTATION 13

double AIRegimeImputeMedian(const int idx)
  {
   static const double m[] = {
      18.20900000, 0.00049900, 4.99000000, 0.97405190, 16.00000000, 2.00000000, 6.00000000, 0.00000000, 0.00000000, 0.98297872, 0.60000000, 0.00000000, 0.00000000, 0.00000000
   };
   return (idx >= 0 && idx < AI_REGIME_FEATURE_COUNT) ? m[idx] : 0.0;
  }

double AIRegimeCoef(const int idx)
  {
   static const double c[] = {
      0.07268459, -0.00000832, -0.08321871, -0.05230828, -0.48966383, 0.03966875, -0.03375058, -0.02443873, 0.31323627, -0.06842025, 0.45944261, -0.17204118, 0.00079702, -0.07943186
   };
   return (idx >= 0 && idx < AI_REGIME_FEATURE_COUNT) ? c[idx] : 0.0;
  }

double AIRegimeIntercept() { return 6.95548816; }

double AISigmoidProb(const double x)
  {
   if(x > 20.0)  return 1.0;
   if(x < -20.0) return 0.0;
   return 1.0 / (1.0 + MathExp(-x));
  }
#endif

double AIRegimeBadBasketProb(const double &f[])
  {
   double logit = AIRegimeIntercept();
   for(int i = 0; i < AI_REGIME_FEATURE_COUNT; i++)
     {
      double v = f[i];
      if(!MathIsValidNumber(v))
         v = AIRegimeImputeMedian(i);
      logit += AIRegimeCoef(i) * v;
     }
   return AISigmoidProb(logit);
  }

#endif // AAG_AIREGIMEMODEL_MQH
