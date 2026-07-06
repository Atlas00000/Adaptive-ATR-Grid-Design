//+------------------------------------------------------------------+
//| AIModelBundle.mqh — AI-808 bundle manifest (auto-generated)       |
//+------------------------------------------------------------------+
#ifndef AAG_AIMODELBUNDLE_MQH
#define AAG_AIMODELBUNDLE_MQH

#include "Utils.mqh"
#include "AIHealthModel.mqh"
#include "AIEntryContextModel.mqh"
#include "AIRegimeModel.mqh"
#include "AIStackRiskModel.mqh"

#define AI_BUNDLE_RUNTIME_VERSION   "20260706_808"
#define AI_BUNDLE_LOCK_AI           "LOCK-AI"
#define AI_BUNDLE_LOCK_AI_804       "LOCK-AI+804"
#define AI_BUNDLE_LOCK_809          "LOCK-809"
#define AI_BUNDLE_LOCK_AI_809       "LOCK-AI+809"
#define AI_BUNDLE_EXPORT_DATE       "20260706"
#define AI_BUNDLE_PRIMARY_ID        "LOCK-AI"

#define AI_BUNDLE_HEALTH_VERSION    AI_HEALTH_MODEL_VERSION
#define AI_BUNDLE_ENTRY_VERSION     AI_ENTRY_MODEL_VERSION
#define AI_BUNDLE_REGIME_VERSION    AI_REGIME_MODEL_VERSION
#define AI_BUNDLE_STACK_VERSION     AI_STACK_RISK_MODEL_VERSION

bool AIModelVersionAccepted(const string preset_version)
  {
   if(preset_version == "" || preset_version == "AI-800")
      return true;
   if(preset_version == AI_BUNDLE_LOCK_AI)
      return true;
   if(preset_version == AI_BUNDLE_LOCK_AI_804)
      return true;
   if(preset_version == AI_BUNDLE_LOCK_809)
      return true;
   if(preset_version == AI_BUNDLE_LOCK_AI_809)
      return true;
   if(preset_version == AI_BUNDLE_RUNTIME_VERSION)
      return true;
   if(preset_version == AI_HEALTH_MODEL_VERSION)
      return true;
   if(preset_version == AI_ENTRY_MODEL_VERSION)
      return true;
   if(preset_version == AI_REGIME_MODEL_VERSION)
      return true;
   if(preset_version == AI_STACK_RISK_MODEL_VERSION)
      return true;
   return false;
  }

bool AIModelBundleMatchesToggles(const string preset_version, string &detail)
  {
   detail = "";
   if(preset_version == "" || preset_version == "AI-800")
      return true;

   if(preset_version == AI_BUNDLE_LOCK_AI || preset_version == AI_BUNDLE_RUNTIME_VERSION)
     {
      if(InpAIEntryContextEnabled)
        {
         detail = "LOCK-AI expects InpAIEntryContextEnabled=false";
         return false;
        }
      if(InpAIRegimeEnabled)
        {
         detail = "LOCK-AI expects InpAIRegimeEnabled=false";
         return false;
        }
      return true;
     }

   if(preset_version == AI_BUNDLE_LOCK_AI_804)
     {
      if(!InpAIEntryContextEnabled)
        {
         detail = "LOCK-AI+804 expects InpAIEntryContextEnabled=true";
         return false;
        }
      return true;
     }

   if(preset_version == AI_BUNDLE_LOCK_809)
     {
      if(InpAIEnabled)
        {
         detail = "LOCK-809 expects InpAIEnabled=false (geometry-only on LOCK-202)";
         return false;
        }
      if(!InpAIPhysicsStackEnabled)
        {
         detail = "LOCK-809 expects InpAIPhysicsStackEnabled=true";
         return false;
        }
      return true;
     }

   if(preset_version == AI_BUNDLE_LOCK_AI_809)
     {
      if(!InpAIEnabled)
        {
         detail = "LOCK-AI+809 expects InpAIEnabled=true";
         return false;
        }
      if(!InpAIBasketHealthEnabled || !InpAIMemoryEnabled)
        {
         detail = "LOCK-AI+809 expects 803 memory + 805p health";
         return false;
        }
      if(!InpAIPhysicsStackEnabled)
        {
         detail = "LOCK-AI+809 expects InpAIPhysicsStackEnabled=true";
         return false;
        }
      if(InpAIEntryContextEnabled || InpAIRegimeEnabled)
        {
         detail = "LOCK-AI+809 expects 804/806 off";
         return false;
        }
      return true;
     }

   return true;
  }

#endif // AAG_AIMODELBUNDLE_MQH
