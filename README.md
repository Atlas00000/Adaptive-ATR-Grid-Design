# Adaptive ATR Grid (AAG)

MetaTrader 5 Expert Advisor — EURUSD M5 mean-reversion grid with ATR-adaptive spacing.

**Production preset:** `Presets/AAG_EURUSD_M5_production.set` (LOCK-202)  
**EA version:** 1.09

## Documentation

| Doc | Description |
|---|---|
| [**ai_enhance.md**](ai_enhance.md) | Phase E8 — AI supervisor programme (offline-first) |
| [**compo-report.md**](compo-report.md) | Full composition report — build & test history |
| [**system-profile.md**](system-profile.md) | System, edge, and trade profile + live metrics |
| [**Edge Discovery.md**](Edge%20Discovery.md) | Complete discovery and enhancement test log |
| [**concept.md**](concept.md) | Strategy thesis |
| [**roadmap.md**](roadmap.md) | Phase 1 implementation roadmap |
| [**Presets/README.md**](Presets/README.md) | Preset index |

## Quick start

1. Copy `AAG/` to `MQL5/Experts/AAG/`
2. Open `AAG.mqproj` in MetaEditor → compile `AAG.mq5`
3. Strategy Tester → Load `AAG_EURUSD_M5_production.set`

## Performance (LOCK-202, equity DD)

| Window | PF | Net ($200) | Equity DD |
|---|---|---|---|
| Jan–Jul 2025 | 1.93 | +$273 | 12.4% |
| Jan 2025 – Jul 2026 | 1.46 | +$623 | 23.0% |

Not live-ready on full history — see `system-profile.md` for gates.

## License

Private research project. All rights reserved.
