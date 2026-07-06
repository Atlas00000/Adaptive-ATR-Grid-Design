//+------------------------------------------------------------------+
//| AIModelRuntime.mqh — AI-808 model load / version / ONNX path      |
//+------------------------------------------------------------------+
#ifndef AAG_AIMODELRUNTIME_MQH
#define AAG_AIMODELRUNTIME_MQH

#include "Logger.mqh"
#include "AIHealthModel.mqh"
#include "AIEntryContextModel.mqh"
#include "AIRegimeModel.mqh"
#include "AIModelBundle.mqh"

#define AI_ONNX_DIR            "AI\\"
#define AI_ONNX_HEALTH         "AI\\basket_health_v0.onnx"
#define AI_ONNX_ENTRY          "AI\\entry_context_v0.onnx"
#define AI_ONNX_REGIME         "AI\\regime_v0.onnx"

class CAIModelRuntime
  {
private:
   CLogger          *m_log;
   bool              m_ready;
   bool              m_use_onnx;
   bool              m_onnx_health;
   bool              m_onnx_entry;
   bool              m_onnx_regime;
   long              m_handle_health;
   long              m_handle_entry;
   long              m_handle_regime;
   string            m_mode;
   string            m_fail_reason;

   void              ReleaseOnnx()
     {
      if(m_handle_health != INVALID_HANDLE)
        {
         OnnxRelease(m_handle_health);
         m_handle_health = INVALID_HANDLE;
        }
      if(m_handle_entry != INVALID_HANDLE)
        {
         OnnxRelease(m_handle_entry);
         m_handle_entry = INVALID_HANDLE;
        }
      if(m_handle_regime != INVALID_HANDLE)
        {
         OnnxRelease(m_handle_regime);
         m_handle_regime = INVALID_HANDLE;
        }
      m_onnx_health = false;
      m_onnx_entry = false;
      m_onnx_regime = false;
     }

   bool              TryLoadOnnx(const string rel_path, long &handle, const string label)
     {
      handle = INVALID_HANDLE;
      if(!FileIsExist(rel_path, FILE_COMMON))
         return false;

      ResetLastError();
      handle = OnnxCreate(rel_path, ONNX_DEFAULT);
      if(handle == INVALID_HANDLE)
        {
         if(m_log != NULL)
            m_log.LogError("AI-808 ONNX load failed " + label +
                           " err=" + IntegerToString(GetLastError()));
         return false;
        }
      if(m_log != NULL)
         m_log.LogInfo("AI-808 ONNX loaded " + label + " path=" + rel_path);
      return true;
     }

   bool              ValidateEmbeddedModels(string &detail)
     {
      detail = "";
      if(InpAIBasketHealthEnabled)
        {
         if(StringLen(AI_HEALTH_MODEL_VERSION) <= 0)
           {
            detail = "health model version missing";
            return false;
           }
        }
      if(InpAIEntryContextEnabled)
        {
         if(StringLen(AI_ENTRY_MODEL_VERSION) <= 0)
           {
            detail = "entry model version missing";
            return false;
           }
        }
      if(InpAIRegimeEnabled)
        {
         if(StringLen(AI_REGIME_MODEL_VERSION) <= 0)
           {
            detail = "regime model version missing";
            return false;
           }
        }
      return true;
     }

   bool              ValidatePresetVersion(string &detail)
     {
      detail = "";
      if(InpAIModelVersion == "" || InpAIModelVersion == "AI-800")
         return true;

      if(!AIModelVersionAccepted(InpAIModelVersion))
        {
         detail = "unknown preset version " + InpAIModelVersion +
                  " (expected " + AI_BUNDLE_LOCK_AI + " or " +
                  AI_BUNDLE_RUNTIME_VERSION + ")";
         return false;
        }

      if(!AIModelBundleMatchesToggles(InpAIModelVersion, detail))
         return false;

      return true;
     }

   bool              LoadOnnxModels()
     {
      m_onnx_health = false;
      m_onnx_entry = false;
      m_onnx_regime = false;

      if(InpAIBasketHealthEnabled)
         m_onnx_health = TryLoadOnnx(AI_ONNX_HEALTH, m_handle_health, "health");
      if(InpAIEntryContextEnabled)
         m_onnx_entry = TryLoadOnnx(AI_ONNX_ENTRY, m_handle_entry, "entry");
      if(InpAIRegimeEnabled)
         m_onnx_regime = TryLoadOnnx(AI_ONNX_REGIME, m_handle_regime, "regime");

      const bool need_health = InpAIBasketHealthEnabled;
      const bool need_entry = InpAIEntryContextEnabled;
      const bool need_regime = InpAIRegimeEnabled;

      if(need_health && !m_onnx_health)
         return false;
      if(need_entry && !m_onnx_entry)
         return false;
      if(need_regime && !m_onnx_regime)
         return false;

      return true;
     }

public:
                     CAIModelRuntime() :
                     m_log(NULL),
                     m_ready(false),
                     m_use_onnx(false),
                     m_onnx_health(false),
                     m_onnx_entry(false),
                     m_onnx_regime(false),
                     m_handle_health(INVALID_HANDLE),
                     m_handle_entry(INVALID_HANDLE),
                     m_handle_regime(INVALID_HANDLE),
                     m_mode("disabled"),
                     m_fail_reason("")
     {
     }

                    ~CAIModelRuntime()
     {
      ReleaseOnnx();
     }

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   bool              Init()
     {
      m_ready = false;
      m_use_onnx = InpAIUseOnnx;
      m_mode = "embedded";
      m_fail_reason = "";
      ReleaseOnnx();

      if(!InpAIEnabled)
        {
         m_ready = true;
         m_mode = "disabled";
         return true;
        }

      string detail = "";
      if(!ValidatePresetVersion(detail))
        {
         m_fail_reason = detail;
         if(m_log != NULL)
            m_log.LogError("AI-808 version gate FAIL — " + detail);
         return false;
        }

      if(!ValidateEmbeddedModels(detail))
        {
         m_fail_reason = detail;
         if(m_log != NULL)
            m_log.LogError("AI-808 embedded model FAIL — " + detail);
         return false;
        }

      if(m_use_onnx)
        {
         if(LoadOnnxModels())
           {
            m_mode = "onnx";
            m_ready = true;
            if(m_log != NULL)
               m_log.LogInfo("AI-808 runtime OK mode=onnx version=" + InpAIModelVersion);
            return true;
           }
         if(InpAIOnnxFallbackEmbedded)
           {
            m_mode = "embedded";
            m_use_onnx = false;
            if(m_log != NULL)
               m_log.LogInfo("AI-808 ONNX unavailable — fallback embedded constants");
           }
         else
           {
            m_fail_reason = "ONNX load failed and fallback disabled";
            if(m_log != NULL)
               m_log.LogError("AI-808 " + m_fail_reason);
            return false;
           }
        }

      m_ready = true;
      if(m_log != NULL)
         m_log.LogInfo("AI-808 runtime OK mode=embedded version=" +
                       (InpAIModelVersion == "" ? AI_BUNDLE_RUNTIME_VERSION : InpAIModelVersion) +
                       " health=" + AI_HEALTH_MODEL_VERSION +
                       " entry=" + AI_ENTRY_MODEL_VERSION +
                       " regime=" + AI_REGIME_MODEL_VERSION);
      return true;
     }

   void              Shutdown()
     {
      ReleaseOnnx();
      m_ready = false;
     }

   bool              IsReady() const { return m_ready; }
   bool              UsesOnnx() const { return m_use_onnx; }
   string            Mode() const { return m_mode; }
   string            FailReason() const { return m_fail_reason; }

   bool              HasOnnxHealth() const { return m_onnx_health; }
   bool              HasOnnxEntry() const { return m_onnx_entry; }
   bool              HasOnnxRegime() const { return m_onnx_regime; }
  };

#endif // AAG_AIMODELRUNTIME_MQH
