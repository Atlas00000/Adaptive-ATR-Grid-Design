//+------------------------------------------------------------------+
//| StateMachine.mqh — grid lifecycle states                         |
//+------------------------------------------------------------------+
#ifndef AAG_STATEMACHINE_MQH
#define AAG_STATEMACHINE_MQH

#include "Logger.mqh"

class CStateMachine
  {
private:
   ENUM_GRID_STATE   m_state;
   ENUM_TRADE_BIAS   m_armed_bias;
   datetime          m_cooldown_until;
   CLogger          *m_log;

public:
                     CStateMachine() :
                     m_state(GRID_STATE_IDLE),
                     m_armed_bias(BIAS_NONE),
                     m_cooldown_until(0),
                     m_log(NULL)
     {}

   void              SetLogger(CLogger &log) { m_log = GetPointer(log); }

   ENUM_GRID_STATE   GetState() const { return m_state; }
   ENUM_TRADE_BIAS   GetArmedBias() const { return m_armed_bias; }
   datetime          GetCooldownUntil() const { return m_cooldown_until; }

   void              SetState(const ENUM_GRID_STATE state)
     {
      if(m_state == state)
         return;
      if(m_log != NULL)
         m_log.LogInfo("State " + AAG_GridStateToString(m_state) + " -> " +
                       AAG_GridStateToString(state));
      m_state = state;
     }

   void              SetIdle()
     {
      m_armed_bias = BIAS_NONE;
      SetState(GRID_STATE_IDLE);
     }

   void              SetArmed(const ENUM_TRADE_BIAS bias)
     {
      m_armed_bias = bias;
      SetState(GRID_STATE_ARMED);
     }

   void              SetGridActive()
     {
      SetState(GRID_STATE_GRID_ACTIVE);
     }

   void              SetManaging()
     {
      SetState(GRID_STATE_MANAGING);
     }

   void              SetExiting()
     {
      SetState(GRID_STATE_EXITING);
     }

   void              StartCooldown(const int cooldown_minutes)
     {
      m_cooldown_until = TimeCurrent() + cooldown_minutes * 60;
      SetState(GRID_STATE_COOLDOWN);
      if(m_log != NULL)
         m_log.LogInfo("Cooldown until " + TimeToString(m_cooldown_until));
     }

   void              RestoreState(const ENUM_GRID_STATE state, const datetime cooldown_until)
     {
      m_state = state;
      m_cooldown_until = cooldown_until;
      if(m_log != NULL)
         m_log.LogInfo("Restored state " + AAG_GridStateToString(m_state));
     }

   bool              IsCooldownActive() const
     {
      if(m_state != GRID_STATE_COOLDOWN)
         return false;
      return TimeCurrent() < m_cooldown_until;
     }

   void              UpdateCooldown()
     {
      if(m_state == GRID_STATE_COOLDOWN && TimeCurrent() >= m_cooldown_until)
        {
         m_cooldown_until = 0;
         SetIdle();
        }
     }

   bool              CanEvaluateSignal() const
     {
      return m_state == GRID_STATE_IDLE || m_state == GRID_STATE_ARMED;
     }

   bool              IsBasketActive() const
     {
      return m_state == GRID_STATE_GRID_ACTIVE ||
             m_state == GRID_STATE_MANAGING ||
             m_state == GRID_STATE_EXITING;
     }
  };

#endif // AAG_STATEMACHINE_MQH
