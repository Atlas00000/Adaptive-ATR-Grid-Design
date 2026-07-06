//+------------------------------------------------------------------+
//| AIHealthModel.mqh — AI-805 exported logistic health scorer        |
//| Auto-generated — do not edit manually                             |
//+------------------------------------------------------------------+
#ifndef AAG_AIHEALTHMODEL_MQH
#define AAG_AIHEALTHMODEL_MQH

#define AI_HEALTH_MODEL_VERSION "AI-805_v0"
#define AI_HEALTH_FEATURE_COUNT 8

#define AI_HEALTH_F_GRID_DEPTH 0
#define AI_HEALTH_F_FLOATING_PL 1
#define AI_HEALTH_F_SECONDS_OPEN 2
#define AI_HEALTH_F_ATR_DELTA 3
#define AI_HEALTH_F_ADX_DELTA 4
#define AI_HEALTH_F_DIST_ANCHOR_ATR 5
#define AI_HEALTH_F_MFE_SO_FAR 6
#define AI_HEALTH_F_MAE_SO_FAR 7

double AIHealthFeatureMean(const int idx)
  {
   static const double m[] = {
      1.00000000, -8.47920000, 3700.03200000, 0.00000000, 0.00000000, 16944.68146632, 5.04346667, -8.47920000
   };
   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? m[idx] : 0.0;
  }

double AIHealthFeatureScale(const int idx)
  {
   static const double s[] = {
      1.00000000, 4.28604488, 10049.73499188, 1.00000000, 1.00000000, 5927.02568515, 3.91481340, 4.28604488
   };
   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? s[idx] : 0.0;
  }

double AIHealthCoef(const int idx)
  {
   static const double c[] = {
      0.00000000, -0.34160062, -0.01483973, 0.00000000, 0.00000000, 0.09670710, -3.73071560, -0.34160062
   };
   return (idx >= 0 && idx < AI_HEALTH_FEATURE_COUNT) ? c[idx] : 0.0;
  }

double AIHealthIntercept() { return -1.24399452; }

double AIHealthSigmoid(const double x)
  {
   if(x > 20.0)  return 1.0;
   if(x < -20.0) return 0.0;
   return 1.0 / (1.0 + MathExp(-x));
  }

double AIHealthScoreFromFeatures(const double &f[])
  {
   double logit = AIHealthIntercept();
   for(int i = 0; i < AI_HEALTH_FEATURE_COUNT; i++)
     {
      const double scale = AIHealthFeatureScale(i);
      const double z = (scale > 0.0) ? (f[i] - AIHealthFeatureMean(i)) / scale : 0.0;
      logit += AIHealthCoef(i) * z;
     }
   return 100.0 * AIHealthSigmoid(logit);
  }

#endif // AAG_AIHEALTHMODEL_MQH
