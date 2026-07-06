# AAG Time Profile (LOCK-809 Demo)

**Purpose:** Avoid time-zone mistakes when running `AAG_EURUSD_M5_AI-809_physics-p45.set` on demo.

---

## 1) Canonical trading window

- EA session window is set by preset inputs:
  - `InpTradeHourStart=15`
  - `InpTradeHourEnd=17`
- This is interpreted in **broker/server time** (not Windows local time).

---

## 2) Current observed offset

From live log:

`REJECT: outside_window hour=14 allowed=15-17`

At the same moment local clock was around 15:25, so currently:

- **Server time = Local time - 1 hour** (observed on 2026-07-06).

With this offset, effective local window is:

- **Local 16:00 to 17:59** (while server is 15:00 to 16:59).

---

## 3) Daily operator checklist

1. Open **Market Watch** and enable the **Time** column.
2. Use that server clock as the source of truth.
3. Keep EA attached to `EURUSD,M5`.
4. Ensure expected init lines:
   - `Init v1.33 symbol=EURUSD tf=PERIOD_M5`
   - `AI-809 physics stack gate — model=AI-809_v0 thr=0.45`
5. Confirm you are on LOCK-809 (not LOCK-AI+809):
   - No `AI-803 performance memory active`
   - No `version=LOCK-AI+809`
6. Start/keep running before server 15:00 (recommended server 14:55).

---

## 4) If you see outside_window rejects

Example:

`REJECT: outside_window hour=14 allowed=15-17`

Interpretation:

- EA is healthy.
- Time gate is working.
- Current server hour is outside configured window.

Action:

- Wait until server hour enters 15..16.
- Do **not** change preset window if you want comparability with validated LOCK-809 results.

---

## 5) Why keep server 15–17 unchanged

- LOCK-809 validation was done on this session definition.
- Shifting hours to match local time creates a different strategy regime and breaks apples-to-apples comparison.

---

*Time profile baseline date: 2026-07-06 (YWO demo session check). Re-verify offset after DST or broker server-time changes.*
