#!/usr/bin/env python3
"""
    fx_trade_bot_v6.8.3.2.py — v6.8.3.2
    Multi-Profile: Profile2/Account002 · Profile3/Account003
    ✅ RSI-FIXED | Consensus | ADX Boost | Monte Carlo | SL Zone Hierarchy
    ✅ TREND FILTER: H1 EMA10 Slope + Weekly EMA100 Counter-Trend Block
    ✅ SMART TP: Profile2=×1.0/×2.0 @75%MC  |  Profile3=Fixed ×1.2
    ✅ EMA100 Buffer: 30p — TP never lands inside zone

    Usage:
        python fx_trade_bot_v6.8.3.2.py --profile2   # default
        python fx_trade_bot_v6.8.3.2.py --profile3
        python fx_trade_bot_v6.8.3.2.py --profile2 --timeframe 15m --test-trade
        python fx_trade_bot_v6.8.3.2.py --profile3 --timeframe H4 --no-test-trade
"""

import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ─── PRIMARY IMPORT: config_bot FIRST ───
import config_bot
import config

# ─── ARGPARSE: SELECT PROFILE BEFORE IMPORTING PROFILE CONFIG ───
parser = argparse.ArgumentParser(description="Forex Trade Bot v6.8.3.2")
parser.add_argument("--profile2", action="store_true", help="Use Profile2 / Account 002")
parser.add_argument("--profile3", action="store_true", help="Use Profile3 / Account 003")
parser.add_argument("--timeframe", type=str, default="15m", help="Candle timeframe: 15m, H1, H4, Daily")
parser.add_argument("--test-trade", action="store_true", help="Test mode — no real orders")
parser.add_argument("--no-test-trade", action="store_true", help="Live mode — REAL orders")
args_known, args_unknown = parser.parse_known_args()

# ─── LOAD PROFILE CONFIG ───
import importlib
if args_known.profile3:
    config_bot_fn = "config_bot_profile3"
    PROFILE_LABEL = "PROFILE3"
    ACCOUNT_NAME = "Account 003"
    COOLDOWN_FILE = Path.home() / "projects/ai_training_cnn" / "cooldown_profile3.json"
    RESULTS_DIR = Path.home() / "projects/ai_training_cnn" / "daily_results_profile3"
else:
    config_bot_fn = "config_bot_profile2"
    PROFILE_LABEL = "PROFILE2"
    ACCOUNT_NAME = "Account 002"
    COOLDOWN_FILE = Path.home() / "projects/ai_training_cnn" / "cooldown_profile2.json"
    RESULTS_DIR = Path.home() / "projects/ai_training_cnn" / "daily_results_profile2"

profile_cfg = importlib.import_module(config_bot_fn)

# ─── CENTRAL CONFIG LOOKUP ───
def cfg_bot(name, default):
    """Lookup priority: profile_cfg → config_bot → config → default"""
    return getattr(
        profile_cfg, name,
        getattr(
            config_bot, name,
            getattr(config, name, default)
        )
    )

# ─── DERIVE ACCOUNT ID FROM PROFILE ───
OANDA_ACCOUNT_ID = getattr(profile_cfg, "OANDA_ACCOUNT_ID", None)
if not OANDA_ACCOUNT_ID:
    from config_oanda import OANDA_ACCOUNT_ID as OANDA_DEFAULT
    OANDA_ACCOUNT_ID = OANDA_DEFAULT

# ─── TREND FILTER + SMART TP CONFIGURATION ────────────────────────────
TREND_TP_CONFIG = {
    "base_tp_pips":           30,
    "mc_strong_threshold":   0.75,   # ≥75% = strong momentum → Profile2 ×2 TP
    "weekly_ema_period":     100,
    "ema100_buffer_pips":     30,    # keep TP ≥30p away from Weekly EMA100

    "profile2": {
        "tp_normal_mult":     1.0,
        "tp_strong_mult":     2.0,
        "ema_period":         10,
        "slope_lookback":      5,
        "min_slope":       0.001,
    },
    "profile3": {
        "tp_mult":            1.2,
        "ema_period":         10,
        "slope_lookback":      5,
        "min_slope":       0.001,
    },
}

TREND_ALLOW_ENTRY = True
TREND_SKIP = False

# ─── TREND HELPERS ────────────────────────────────────────────────────
def calculate_ema_slope(ema_series, lookback_bars):
    """% change from lookback bars ago + current EMA level"""
    ema_now  = ema_series.iloc[-1]
    ema_prev = ema_series.iloc[-lookback_bars]
    slope_pct = (ema_now - ema_prev) / ema_prev
    return slope_pct, ema_now

def _pips_to_price(entry, direction, pips, pip_value):
    offset = pips * pip_value
    return entry + offset if direction == "long" else entry - offset

def _price_to_pips(entry, tp_price, pip_value):
    return abs(tp_price - entry) / pip_value

def evaluate_trend_and_tp(profile_name, direction, mc_momentum,
                           entry_price, pip_value,
                           h1_ema_series, weekly_ema100, current_price):
    """
    ENTRY FILTERS:
      A — H1 EMA trend alignment (price on correct side + slope ≥ min)
      B — No counter-trend vs Weekly EMA100
    TP LOGIC:
      Profile2 → ×1.0 normal / ×2.0 strong (MC ≥75%)
      Profile3 → fixed ×1.2
      Buffer 30p away from Weekly EMA100
    """
    cfg = TREND_TP_CONFIG[profile_name]
    base_pips = TREND_TP_CONFIG["base_tp_pips"]

    # --- Rule A: H1 Trend Alignment ---
    slope, ema_level = calculate_ema_slope(h1_ema_series, cfg["slope_lookback"])
    min_slope = cfg["min_slope"]

    valid_trend = True
    if direction == "long":
        if not (current_price > ema_level and slope > min_slope):
            valid_trend = False
            logger.info(f"⚠️ SKIP LONG — Price below H1 EMA{cfg['ema_period']} or slope too weak")
    else:
        if not (current_price < ema_level and slope < -min_slope):
            valid_trend = False
            logger.info(f"⚠️ SKIP SHORT — Price above H1 EMA{cfg['ema_period']} or slope too weak")

    if not valid_trend:
        return TREND_SKIP, 0.0, "H1 TREND MISALIGNED"

    # --- Rule B: No Counter-Trend vs Weekly EMA100 ---
    if direction == "long" and current_price < weekly_ema100:
        return TREND_SKIP, 0.0, "COUNTER-TREND vs WEEKLY EMA100"
    if direction == "short" and current_price > weekly_ema100:
        return TREND_SKIP, 0.0, "COUNTER-TREND vs WEEKLY EMA100"

    # --- Calculate TP ---
    if profile_name == "profile2":
        if mc_momentum >= TREND_TP_CONFIG["mc_strong_threshold"]:
            tp_pips = base_pips * cfg["tp_strong_mult"]
            tp_mode = "STRONG MOMENTUM ×2"
        else:
            tp_pips = base_pips * cfg["tp_normal_mult"]
            tp_mode = "NORMAL ×1"
    else:
        tp_pips = base_pips * cfg["tp_mult"]
        tp_mode = f"FIXED ×{cfg['tp_mult']}"

    # --- Rule C: Keep TP away from Weekly EMA100 Buffer ---
    tp_price = _pips_to_price(entry_price, direction, tp_pips, pip_value)
    buffer_dist = TREND_TP_CONFIG["ema100_buffer_pips"] * pip_value

    if abs(tp_price - weekly_ema100) < buffer_dist:
        if direction == "long":
            tp_price = weekly_ema100 + buffer_dist
        else:
            tp_price = weekly_ema100 - buffer_dist
        tp_pips = _price_to_pips(entry_price, tp_price, pip_value)
        logger.info(f"📌 TP shifted away from Weekly EMA100 → {tp_pips:.1f}p")

    logger.info(f"✅ {tp_mode} | TP = {tp_pips:.1f}p")
    return TREND_ALLOW_ENTRY, tp_pips, tp_mode


# ============================================================
# REST OF YOUR EXISTING BOT CODE CONTINUES HERE
# ============================================================
# [ Keep everything below exactly as in your working v6.8.3.1 ]
# ... imports, logging, oanda setup, main loop, etc ...
# ... where you calculate TP → replace with call above ...
