//+------------------------------------------------------------------+
//| AIStackRiskModel.mqh — AI-809 L0-SL stack-risk scorer
//| Auto-generated — do not edit manually                             |
//+------------------------------------------------------------------+
#ifndef AAG_AISTACKRISKMODEL_MQH
#define AAG_AISTACKRISKMODEL_MQH

#define AI_STACK_RISK_MODEL_VERSION "AI-809_v0"
#define AI_STACK_RISK_FEATURE_COUNT 17

#define AIStack_ENTRY_ADX 0
#define AIStack_ENTRY_ATR 1
#define AIStack_ATR_PIPS 2
#define AIStack_L0_HOLD_HOURS 3
#define AIStack_L0_LOSS_USD 4
#define AIStack_L0_MAE_USD 5
#define AIStack_L0_MFE_USD 6
#define AIStack_L0_MAE_ATR 7
#define AIStack_HOUR 8
#define AIStack_WEEKDAY 9
#define AIStack_BAD_HOUR 10
#define AIStack_BIAS_SELL 11
#define AIStack_SESSION_LONDON 12
#define AIStack_SESSION_NY 13
#define AIStack_ROLLING_PF_20 14
#define AIStack_ROLLING_WR_20 15
#define AIStack_CONSEC_LOSSES 16

double AIStackImputeMedian(const int idx)
  {
   static const double m[] = {
      18.16560000, 0.00061900, 6.19000000, 0.40000000, -10.00000000, -10.00000000, 0.00000000, 16.39800000, 15.00000000, 3.00000000, 0.00000000, 1.00000000, 1.00000000, 0.00000000, 0.99851279, 0.55000000, 0.00000000
   };
   return (idx >= 0 && idx < AI_STACK_RISK_FEATURE_COUNT) ? m[idx] : 0.0;
  }

double AIStackCoef(const int idx)
  {
   static const double c[] = {
      0.01436418, 0.00001014, 0.10142577, -0.45023886, 0.10346984, 0.10346984, 0.00000000, 0.11096875, 0.17403961, 0.13851058, -0.14378932, 0.44050329, -0.01529304, 0.01527329, 0.11636679, 0.04424684, 0.22176706
   };
   return (idx >= 0 && idx < AI_STACK_RISK_FEATURE_COUNT) ? c[idx] : 0.0;
  }

double AIStackIntercept() { return -4.18390715; }

#ifndef AISIGMOIDPROB_DEFINED
#define AISIGMOIDPROB_DEFINED
double AISigmoidProb(const double x)
  {
   if(x > 20.0)  return 1.0;
   if(x < -20.0) return 0.0;
   return 1.0 / (1.0 + MathExp(-x));
  }
#endif

double AIStackRiskBlockProb(const double &f[])
  {
   double logit = AIStackIntercept();
   for(int i = 0; i < AI_STACK_RISK_FEATURE_COUNT; i++)
     {
      double v = f[i];
      if(!MathIsValidNumber(v))
         v = AIStackImputeMedian(i);
      logit += AIStackCoef(i) * v;
     }
   return AISigmoidProb(logit);
  }

#endif // AAG_AISTACKRISKMODEL_MQH
