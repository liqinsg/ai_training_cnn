Understood perfectly — **no big-bang rewrite, no restructuring, no moving files around**. We fix issues one at a time, in-place, keeping everything working at every step. Here’s the step-by-step bug-fix plan exactly as requested.

---

## Phase 1: Immediate Critical Bug Fixes (no structure changes)

### Task 1 — Logger race condition (Critical)
**Problem:** `resolve_min_slope()` and early helpers reference `logger` before it’s created.
**Fix — in-place, no imports moved:**
```python
# === AT TOP OF FILE, BEFORE resolve_min_slope() ===
import logging as _log

# Fallback logger safe to call anywhere, anytime
_safe_log = _log.getLogger("bot_fallback")

# === THEN in resolve_min_slope() ===
def resolve_min_slope(score_gap: float, ladder: tuple) -> float:
    if score_gap < 0:
        _safe_log.warning("Negative score gap: %.4f — using floor", score_gap)
    # ... rest unchanged
```
- ✅ No moving functions
- ✅ No renaming anything else
- ✅ Works immediately

**Checklist:**
- [ ] Add fallback at module top
- [ ] Replace all `logger.warning/info/error` called before logger init → `_safe_log.xxx`
- [ ] Verify: search entire file for `logger.` above `logger = get_logger(` — update those only
- [ ] Test run: confirm no `NameError: name 'logger' is not defined`

---

### Task 2 — Look-ahead / incomplete candle audit (High)
**Goal:** Ensure we never use a partially formed candle in calculations.
**Fix pattern — add explicit closed-bar check:**
```python
# === Where EMA/price series are built ===
def get_ema_series(prices, lookback: int):
    ema = prices.ewm(span=lookback).mean()
    
    # Guard: drop incomplete/latest-unclosed candle
    if NOT_CLOSED_YET:  # define based on your fetcher
        ema = ema.iloc[:-1]
        prices = prices.iloc[:-1]
    
    ema_now = ema.iloc[-1]
    ema_prev = ema.iloc[-lookback]
    return ema_now, ema_prev
```

**Step-by-step checks:**
- [ ] Audit `fetcher.fetch()` — confirm: does it return only fully closed candles?
- [ ] Tag every `.iloc[-1]` on price/EMA series — verify it’s the last *closed* bar
- [ ] Add timestamp check: `(now - last_candle_time) >= candle_interval`
- [ ] Apply defensive slice: `series = series.iloc[:-1]` if candle not yet closed
- [ ] Log: `WARNING — using last-closed bar only; current candle incomplete`

---

### Task 3 — D-Gate naming cleanup (Low / Quick)
**Just rename variable — zero logic change:**
```python
# OLD:
d_gate_compute_direction(daily_closes)

# NEW:
d_gate_compute_direction(h1_closes)
```
- [ ] Rename `daily_closes` → `h1_closes` wherever H1 data flows
- [ ] No calculation changes
- [ ] Re-run existing tests — behaviour identical

---

## Phase 2 — Behaviour & Logic Tuning (in-place, no structure change)

### Task 4 — Cooldown scope visibility & tuning
**Goal:** See exactly what’s blocked, then optionally relax it.
**Step 4a — Add diagnostics first:**
```python
last_closed[base] = True
last_closed[quote] = True
_safe_log.info(
    "COOLDOWN_APPLIED: pair=%s → blocked_currencies: %s, %s",
    instrument, base, quote
)
```
- [ ] Add log line immediately where cooldown is set
- [ ] Run live/dry → collect: *how many symbols actually get skipped?*

**Step 4b — Add scope switch (optional, data-driven):**
```python
# From profile config — default = "currency"
COOLDOWN_SCOPE = cfg.get("COOLDOWN_SCOPE", "currency")

if COOLDOWN_SCOPE == "currency":
    last_closed[base] = True
    last_closed[quote] = True
elif COOLDOWN_SCOPE == "pair":
    last_closed[instrument] = True
```
- [ ] Add profile key `COOLDOWN_SCOPE`
- [ ] Keep current behaviour as default
- [ ] Switch to `"pair"` only after seeing evidence it’s too restrictive

---

### Task 5 — Remove config duplication (in-place)
**Pattern to fix:**
```python
# ❌ Duplicate — prone to drift
MIN_CONVICTION = cfg["MIN_CONVICTION"]
# ... 50 lines later ...
MIN_CONVICTION = P["MIN_CONVICTION"]

# ✅ Keep ONE source
MIN_CONVICTION = cfg_bot("MIN_CONVICTION")
# Then reference MIN_CONVICTION consistently — no re-assignment
```
- [ ] Search file: find all re-bindings of same config key
- [ ] Keep **one** assignment per key near top
- [ ] Remove all later re-definitions
- [ ] Verify downstream: uses the single assigned name

---

## Phase 3 — Logic Improvements (pure add-on, no rewrite)

### Task 6 — Score-proportional lot sizing
**Add logic around existing score — no change to scoring itself:**
```python
DEFAULT_LOT = cfg_bot("DEFAULT_LOT_SIZE")
SCORE_BANDS = [
    (85, 1.25),
    (75, 1.00),
    (65, 0.75),
    (0, 0.0),   # reject
]

def get_lot_multiplier(score: int) -> float:
    for threshold, mult in SCORE_BANDS:
        if score >= threshold:
            return mult
    return 0.0

# At sizing time:
multiplier = get_lot_multiplier(FINAL_SCORE)
lot_size = DEFAULT_LOT * multiplier
if multiplier == 0:
    logger.info("REJECTED: score %d below threshold", FINAL_SCORE)
    return
```
- [ ] Add band config in profile
- [ ] Run **shadow mode first** — log what lot would have been, don’t change execution
- [ ] After 1–2 weeks → enable live sizing

---

## Execution Order — Do This Sequence

| # | Task | Effort | Risk | Done |
|---|---|---|---|---|
| 1 | Logger race fix | 5 min | Zero | ⬜ |
| 2 | D-Gate rename | 2 min | Zero | ⬜ |
| 3 | Candle/leakage audit | 30 min | Medium | ⬜ |
| 4 | Config dedup (one key at a time) | 15 min | Low | ⬜ |
| 5 | Cooldown diagnostics + scope option | 15 min | Low | ⬜ |
| 6 | Score-based lot sizing (shadow first) | 20 min | Low | ⬜ |

**Rule:** After every single task → run dry-run → confirm bot still starts and runs exactly as before. No cumulative changes.

---

Pick the **first task** you want me to write the exact patched code for — I’ll output only the changed sections, ready to paste in-place without touching anything else. Which one to start with?
