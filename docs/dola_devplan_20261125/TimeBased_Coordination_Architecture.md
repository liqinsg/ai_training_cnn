# FX Bot — Time-Based Coordination Architecture

**Version**: 1.0 | **Date**: 2026-11-25 | **Language**: EN
**Timezone Base**: Singapore Time (SGT = UTC+8)

---

## 📑 Table of Contents

1. [Core Philosophy](#1--core-philosophy)
2. [Session Definition &amp; DST Handling](#2--session-definition--dst-handling)
3. [Profile Roles &amp; Responsibilities](#3--profile-roles--responsibilities)
4. [Phase Implementation Roadmap](#4--phase-implementation-roadmap)
5. [Key Design Principles](#5--key-design-principles)

---

## 1 — Core Philosophy

> **Trade only when real people and institutional capital are active. Stay out when it's just algorithms.**

- **00:00–09:00 SGT**: Low liquidity, algorithm-driven noise → **No new trades**
- **Asian Session (09:00–15:00)**: Direction testing only, conservative → **P3 only, light exposure**
- **European Open (15:00–20:00)**: Institutional capital enters → **Standard conditions**
- **US Overlap (20:00–00:00)**: Highest liquidity, genuine trends emerge → **Full engagement**
- **Non-farm / major news**: No special-case logic — treat as high-volatility day: raise confidence threshold + reduce position sizing

---

## 2 — Session Definition & DST Handling

### Standard Session (Winter Time, SGT = UTC+8)

| ID                | Session Name  | SGT Window   | Allowed Profiles | Confidence Bias | Lot Multiplier | Max New Per Pair |
| ----------------- | ------------- | ------------ | ---------------- | --------------- | -------------- | ---------------- |
| `deep_sleep`    | Deep Sleep    | 00:00–09:00 | None             | +0              | 0.0            | 0                |
| `asian_morning` | Asian Morning | 09:00–15:00 | P3 only          | +10.0           | 0.25           | 2                |
| `european_open` | European Open | 15:00–20:00 | P2, P4           | +0              | 0.6            | Unlimited        |
| `us_ovlp`       | US Overlap    | 20:00–00:00 | P1, P2, P4       | -5.0            | 1.0            | Unlimited        |

### Daylight Saving Time Adjustments

| Region        | Effective Period             | Shift     | Adjusted Window (SGT)                                                      |
| ------------- | ---------------------------- | --------- | -------------------------------------------------------------------------- |
| UK DST (BST)  | Last Sun Mar → Last Sun Oct | −1 hr    | European Open: **14:00–19:00**   US Overlap: **19:00–23:00** |
| US DST (EDT)  | 2nd Sun Mar → 1st Sun Nov   | −1 hr    | Follows UK adjustment                                                      |
| Asian Session | —                           | No change | 09:00–14:00 (closes 1hr earlier)                                          |

### Boundary Events

| Event ID                | Trigger Time (SGT) | Purpose                                                                |
| ----------------------- | ------------------ | ---------------------------------------------------------------------- |
| `OVERNIGHT_CLEAR`     | 08:55              | Scan overnight positions; clear low-confidence/forbidden entries       |
| `ASIAN_STOP_NEW`      | 14:30              | P3 stops opening new trades; manage existing positions only            |
| `BEFORE_EUROPE_AUDIT` | 14:50 / 15:00      | Audit Asian positions against European signals; exit early if conflict |

### Holiday & Special Market Handling

- **Primary Source**: OANDA API `tradingMode` field (`regular` / `reduced` / `closed`)
- **Fallback**: Local calendar in `config_calendar.json`
- **US extended 23-hour sessions**: Treated as `reduced` liquidity mode — no new trades outside core windows; existing positions managed normally

---

## 3 — Profile Roles & Responsibilities

| Profile                     | Primary Session                         | Role                                 | Confidence        | Positioning                             | Key Trait                                                        |
| --------------------------- | --------------------------------------- | ------------------------------------ | ----------------- | --------------------------------------- | ---------------------------------------------------------------- |
| **P3 — Scout**       | Asian Morning 09:00–15:00              | Direction testing, noise filtering   | 65+ (strict)      | Light: max 2 units/order, 2 pairs total | Patient, small drawdowns, conservative                           |
| **P2 — Main Engine** | European Open + US Overlap 15:00–00:00 | Primary execution, balanced growth   | 45+               | Standard sizing                         | Consistent, reliable baseline returns                            |
| **P4 — Defense**     | European Open + US Overlap 15:00–00:00 | Structure breakout, drawdown control | 42+               | 40% of max allocation                   | Protect capital, smooth equity curve                             |
| **P1 — Offensive**   | US Overlap 20:00–00:00                 | Trend capture, high-conviction moves | 45+ (relaxed −5) | Full allocation                         | High reward, higher volatility — only in highest-quality window |

### Cross-Session Audit Logic

> **Asian positions are NOT automatically carried into European session without verification**

| Scenario      | P3 vs P2/P4 Signal | Strength Differential | Outcome               | Recommendation                               |
| ------------- | ------------------ | --------------------- | --------------------- | -------------------------------------------- |
| ✅ Aligned    | Same direction     | ≥ 1.5                | Confirm & hold        | Keep; consider modest add                    |
| ⚠️ Weakened | Same direction     | 0.8–1.5              | Watch mode            | Move SL to breakeven                         |
| 🔴 Conflict   | Opposite direction | ≥ 2.0                | **Active exit** | Exit at small loss (−3~5p) before gap/crash |
| ⚪ Unclear    | No clear signal    | < 0.8                 | Wait                  | Re-check at 15:15                            |

---

## 4 — Phase Implementation Roadmap

| Phase             | Module                          | Objective                                                                          | Key Deliverables                                                     |
| ----------------- | ------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Phase 0** | TimeGate Session Controller     | Accurate session detection, DST & holiday handling                                 | `timegate.py`, `config_session.json`, `config_calendar.json`   |
| **Phase 1** | P3 Asian Session + SessionAudit | P3 exclusive in Asian session; pre-Europe conflict detection                       | `session_audit.py`, `config_p3_asian.json`, boundary event logic |
| **Phase 2** | Profile Voting & Consensus      | Multi-profile signal validation; conflicting signals suppressed                    | `strategy_voter.py`, voting rules & consensus thresholds           |
| **Phase 3** | Dynamic Allocation & Monitoring | Position sizing adapts to session quality & consensus strength; full audit logging | Performance dashboard; session-by-session P&L breakdown              |

---

## 5 — Key Design Principles

### 5.1 — Session First, Signals Second

> **Determine WHEN we can trade BEFORE calculating WHAT to trade.** The session gate is the hardest filter — nothing else runs if the session mask says no.

### 5.2 — Configuration-Driven, Hard-Code Minimal

- All session times, weights, thresholds in external JSON files
- Change a rule → edit config, not core logic → safer, easier to roll back

### 5.3 — Progressive & Reversible

- Each phase independently testable
- No forced upgrades — disable any module at any time
- Audit trail for every decision: **who, when, why** — fully traceable

### 5.4 — No Overreaction to News or Schedule Changes

- US 23-hour sessions, NFP volatility shifts — handled through existing market-status detection, NOT special-case code
- **Rules adapt automatically; architecture stays stable**

---

> **Final Summary**: The US moving to 23-hour trading impacts our extended-hours monitoring only — the core strategy logic remains completely sound. We trade institutional liquidity windows, not exchange clock times — and that principle hasn't changed. ✅
