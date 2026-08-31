#!/usr/bin/env python3
"""
    fx_trade_bot_v6.8.5.1 — UNIFIED CONFIG · Single config_bot.py
    Profile2/Account002 · Profile3/Account003
    ✅ All profiles in config_bot.py — NO separate profile config files
    ✅ CLI selects profile → auto-loads correct account + settings
    ✅ TREND_FILTER: Profile3=ON · Profile2=OFF — CLI can override

    Usage:
        python fx_trade_bot_v6.8.5.1.py --profile2    # default, filters OFF
        python fx_trade_bot_v6.8.5.1.py --profile3    # filters AUTO-ON
        python fx_trade_bot_v6.8.5.1.py --profile3 --timeframe H4
        python fx_trade_bot_v6.8.5.1.py --profile3 --trend-filter-enabled false
"""
import contextlib, sys, os, logging, argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np, pandas as pd

# ─── ✅ ONLY ONE CONFIG IMPORT ───
import config_bot as cfg_base
from config_bot import PROFILE_CFG

from utils.trading_core import forex_market_closed
from utils.strategy_helpers import build_strength_matrix, format_strength_ranking, get_live_prices
from telegram_message import send_telegram_message
from oandapyV20.endpoints.instruments import InstrumentsCandles
from strategy_decision import StrategyConfig, StrategyEngine, FilterMode, Direction
from data_pipeline import FeatureConfig, FeatureEngine, ModelWrapper, DataFetcher, ATRModule
from fx_trade_bot_utils import (
    pip_size, load_cooldown, get_open_position, close_position, fetch_candles,
    open_oanda_order_simple as open_oanda_order, DynamicPositionManager, load_mc_legacy,
    calculate_stop_loss,
)
from fx_trade_bot_mc import MCGenerator, MCConfig
from fx_trade_bot_ml import ensure_model
from config_oanda import api

# ─── ✅ 使用统一日志配置 ──────────────────────────────────────────────────────
from utils.logging_utils import get_logger
logger = get_logger()   # 全局 "fx_bot" 日志器，自动带文件+控制台双输出

BASE_DIR = Path(__file__).resolve().parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / "utils")])


# ─── HELPER: Profile-aware config lookup ─────────────────────────────────────
def cfg(profile_dict, key, default=None):
    """Priority: Profile-specific → config_bot base → default"""
    return profile_dict.get(key, getattr(cfg_base, key, default))


# ─── PARSE ARGS & SELECT PROFILE ─────────────────────────────────────────────
parser = argparse.ArgumentParser(description="FX Trading Bot v6.8.5.1 · Unified Config")
parser.add_argument("--profile2", action="store_true", help="Use Profile2 / Account002")
parser.add_argument("--profile3", action="store_true", help="Use Profile3 / Account003")
parser.add_argument("--profile4", action="store_true", help="Use Profile4 / Account004 · DEMO")  # ✅ ADD
parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
parser.add_argument("--trend-filter-enabled", type=str.lower, choices=["true","false","1","0"], default=None)
parser.add_argument("--confluence", action="store_true", default=None)
parser.add_argument("--no-confluence", action="store_false", dest="confluence")
parser.add_argument("--skip-mc", action="store_true")
parser.add_argument("--mc-only", action="store_true")
args = parser.parse_args()


# ─── ✅ LOAD SELECTED PROFILE — NO separate files ────────────────────────────
if args.profile4:
    PROFILE_NAME = "profile4"
elif args.profile3:
    PROFILE_NAME = "profile3"
else:
    PROFILE_NAME = "profile2"

P = PROFILE_CFG[PROFILE_NAME]  # All profile settings in ONE dict

# ─── Resolve core identity ──────────────────────────────────────────────────
OANDA_ACCOUNT_ID = cfg(P, "OANDA_ACCOUNT_ID")
PROFILE_LABEL = cfg(P, "LABEL", PROFILE_NAME.upper())
ACCOUNT_NAME = cfg(P, "ACCOUNT_NAME", "Unknown")
COOLDOWN_FILE = BASE_DIR / cfg(P, "COOLDOWN_FILE", f"cooldown_{PROFILE_NAME}.json")
RESULTS_DIR = BASE_DIR / cfg(P, "RESULTS_DIR", f"daily_results_{PROFILE_NAME}")

if not OANDA_ACCOUNT_ID or len(OANDA_ACCOUNT_ID) < 10 or "-" not in OANDA_ACCOUNT_ID:
    logger.critical(f"💥 FATAL: Invalid OANDA_ACCOUNT_ID = '{OANDA_ACCOUNT_ID}'")
    logger.critical("💥 程序终止 — 请检查 Profile4 Account ID 配置！")
    send_telegram_message(f"💥 FATAL ERROR: Invalid Account ID for {PROFILE_LABEL}")
    exit(1)  # ❌ 直接退出，不跑后面所有逻辑

logger.info(f"🔑 使用账户: {OANDA_ACCOUNT_ID}")

RESULTS_DIR.mkdir(exist_ok=True)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


# ─── ✅ TREND FILTER: Profile3=ON · Profile2=OFF — CLI can override ──────────
TREND_FILTER_ENABLED = cfg(P, "TREND_FILTER_ENABLED", False)
WEEK_EMA100_FILTER_ENABLED = cfg(P, "WEEK_EMA100_FILTER_ENABLED", False)

if args.trend_filter_enabled is not None:
    TREND_FILTER_ENABLED = args.trend_filter_enabled in ("true", "1")
    logger_info_cli = f"🔧 CLI OVERRIDE: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED}"
else:
    logger_info_cli = (f"🔍 AUTO: TREND_FILTER_ENABLED={TREND_FILTER_ENABLED} | "
                       f"WEEK_EMA100={WEEK_EMA100_FILTER_ENABLED} | profile={PROFILE_NAME}")


# ─── Resolve all strategy parameters ────────────────────────────────────────
MODE = cfg(P, "MODE", "LEVEL10")
TIMEFRAME = args.timeframe
OANDA_GRANULARITY_MAP = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}
OANDA_GRANULARITY = OANDA_GRANULARITY_MAP.get(TIMEFRAME, "H4")

MIN_CONVICTION_SCORE = cfg(P, "MIN_CONVICTION_SCORE", 30.0)
BASE_MIN_EDGE        = cfg(P, "BASE_MIN_EDGE", 0.50)
MAX_OPEN             = cfg(P, "MAX_OPEN_POSITIONS", 4)
DEFAULT_LOT_SIZE     = cfg(P, "DEFAULT_LOT_SIZE", 10000)

ATR_SL_MULT   = cfg(P, "ATR_SL_MULT", 2.0)
ATR_TP_MULT   = cfg(P, "ATR_TP_MULT", 3.0)
ATR_PERIOD    = cfg(P, "ATR_PERIOD", 14)
BASE_TP_PIPS  = cfg(P, "BASE_TP_PIPS", 50)
TP_MULT       = cfg(P, "TP_MULT", 2.0)
TP_STRONG_MULT= cfg(P, "TP_STRONG_MULT", 2.5)
MC_STRONG_THRESHOLD = cfg(P, "MC_STRONG_THRESHOLD", 0.55)
EMA_PERIOD_FAST     = cfg(P, "EMA_PERIOD_FAST", 40)
EMA_PERIOD_SLOW     = cfg(P, "EMA_PERIOD_SLOW", 80)
EMA100_BUFFER_PIPS  = cfg(P, "EMA100_BUFFER_PIPS", 30)

XGB_BULLISH_THRESHOLD  = cfg(P, "XGB_BULLISH_THRESHOLD", 0.55)
MC_BULLISH_THRESHOLD   = cfg(P, "MC_BULLISH_THRESHOLD_PCT", 55.0)
REQUIRE_STRONG_MOMENTUM= cfg(P, "REQUIRE_STRONG_MOMENTUM", False)

# Weights — auto-normalize if sum ≠ 1.0
W_S = cfg(P, "WEIGHT_STRENGTH", 0.40)
W_R = cfg(P, "WEIGHT_RSI", 0.15)
W_A = cfg(P, "WEIGHT_ADX", 0.15)
W_X = cfg(P, "WEIGHT_XGB", 0.20)
W_M = cfg(P, "WEIGHT_MC", 0.10)
_WEIGHT_SUM = W_S + W_R + W_A + W_X + W_M
if abs(_WEIGHT_SUM - 1.00) > 0.001:
    logging.warning(f"⚠️ Weight sum = {_WEIGHT_SUM:.4f} ≠ 1.00 — normalizing")
    W_S, W_R, W_A, W_X, W_M = [w / _WEIGHT_SUM for w in [W_S, W_R, W_A, W_X, W_M]]

CONSENSUS_THRESHOLD        = cfg(P, "CONSENSUS_THRESHOLD", 2)
CONSENSUS_REQUIRED_VOTES   = cfg(P, "CONSENSUS_REQUIRED_VOTES", 2)
REQUIRE_DIRECTION_CONSENSUS= cfg(P, "REQUIRE_DIRECTION_CONSENSUS", True)
MIN_STRENGTH_GAP           = cfg(P, "MIN_SCORE_GAP", 0.10)

USE_DYNAMIC_SL   = cfg(P, "USE_DYNAMIC_SL", 2)
DYNAMIC_SL_MULT = cfg(P, "DYNAMIC_SL_MULT", 1.5)

# Global base fallbacks
ALL_PAIRS          = cfg_base.ALL_PAIRS
YAHOO_TO_OANDA     = cfg_base.YAHOO_TO_OANDA
YF_INTERVAL        = cfg(P, "YF_INTERVAL", "4h")
YF_PERIOD_FULL     = cfg(P, "YF_PERIOD_FULL", "30d")
YF_PERIOD_RESAMPLE = cfg(P, "YF_PERIOD_RESAMPLE", "60d")
YF_INTERVAL_D      = cfg(P, "YF_INTERVAL_D", "1d")
PERIODS_YEAR       = cfg(P, "PERIODS_YEAR", 252)
MC_MAX_AGE_HOURS   = cfg(P, "MC_MAX_AGE_HOURS", 24)
MC_BAND_PCT        = cfg(P, "MC_BAND_PCT", 90)
SIMULATIONS        = cfg(P, "MC_SIMULATIONS", 5000)
CONFIDENCE         = MC_BAND_PCT / 100.0
TRAILING_TP        = cfg(P, "TRAILING_TP", True)
DYNAMIC_TP         = cfg(P, "DYNAMIC_TP", False)
TP_RAISE_THRESHOLD_PIPS = cfg(P, "TP_RAISE_THRESHOLD_PIPS", 15)
MIN_SL_PIPS        = cfg(P, "MIN_SL_PIPS", 35)
MIN_SL_PIPS_JPY    = cfg(P, "MIN_SL_PIPS_JPY", MIN_SL_PIPS + 10)
REMOVE_COOLDOWN    = cfg(P, "REMOVE_COOLDOWN", True)
DEBUG_MODE         = cfg(P, "DEBUG_MODE", False)
SKIP_MC            = cfg(P, "SKIP_MC", False)
MULTI_TF_CONFLUENCE= cfg(P, "MULTI_TF_CONFLUENCE", False)
CONFLUENCE_REQUIRED_TFS = cfg(P, "CONFLUENCE_REQUIRED_TFS", 2)

if args.confluence is not None:
    MULTI_TF_CONFLUENCE = args.confluence


# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / f"bot_{PROFILE_NAME}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
# logger = logging.getLogger(__name__)
# logger.info(logger_info_cli)
# logger.info(f"⚖️  {PROFILE_LABEL} WEIGHTS: S={W_S:.2f} R={W_R:.2f} A={W_A:.2f} X={W_X:.2f} M={W_M:.2f} | SUM=1.00")


# ─── Weekly EMA100 & Trend Logic ────────────────────────────────────────────
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def fetch_weekly_ema100(oanda_instrument, api):
    """Returns None if filter OFF or data invalid → filter bypassed"""
    if not WEEK_EMA100_FILTER_ENABLED:
        return None
    try:
        resp = api.request(InstrumentsCandles(
            instrument=oanda_instrument,
            params={"granularity": "W", "count": 105, "price": "M"}
        ))
        candles = resp.get("candles") or []
        if len(candles) < 100:
            logger.warning(f"⚠️ Weekly EMA100 {oanda_instrument}: only {len(candles)} candles — filter bypassed")
            return None
        closes = []
        for c in candles:
            mid = c.get("mid") or {}
            try: closes.append(float(mid["c"]))
            except: continue
        if len(closes) < 100:
            return None
        series = pd.Series(closes)
        ema100 = float(calculate_ema(series, 100).iloc[-1])
        last_close = float(closes[-1])
        if not np.isfinite(ema100) or ema100 <= 0 or last_close <= 0:
            logger.warning(f"⚠️ Weekly EMA100 invalid — filter bypassed")
            return None
        if abs(ema100 - last_close) / last_close > 0.25:
            logger.warning(f"⚠️ Weekly EMA100 implausible — filter bypassed")
            return None
        return ema100
    except Exception as e:
        logger.warning(f"⚠️ Cannot fetch Weekly EMA100: {e}")
        return None

def evaluate_trend_and_tp(profile_name, direction, mc_pct_up,
                           entry_price, pip_value, df, weekly_ema100,
                           ema_cross_filter, fast_period, slow_period,
                           base_tp_pips, mc_strong_threshold,
                           tp_mult, tp_strong_mult,
                           ema100_buffer_pips=30, timeframe="15m"):
    current_price = entry_price
    # Rule A — EMA Crossover
    if ema_cross_filter:
        ema_fast = calculate_ema(df["Close"], fast_period)
        ema_slow = calculate_ema(df["Close"], slow_period)
        fv, sv = ema_fast.iloc[-1], ema_slow.iloc[-1]
        if direction == "BUY" and not (current_price > fv and fv > sv):
            return False, 0.0, f"TREND MISALIGNED: Price>{fv:.5f}>{sv:.5f} required"
        if direction == "SELL" and not (current_price < fv and fv < sv):
            return False, 0.0, f"TREND MISALIGNED: Price<{fv:.5f}<{sv:.5f} required"
    # Rule B — Weekly EMA100 Counter-Trend Block
    if weekly_ema100 is not None:
        if direction == "BUY" and current_price < weekly_ema100:
            return False, 0.0, f"BELOW WEEKLY EMA100 {weekly_ema100:.5f}"
        if direction == "SELL" and current_price > weekly_ema100:
            return False, 0.0, f"ABOVE WEEKLY EMA100 {weekly_ema100:.5f}"
    # Smart TP
    mc_momentum = mc_pct_up / 100.0
    tp_pips = base_tp_pips * tp_strong_mult if mc_momentum >= mc_strong_threshold else base_tp_pips * tp_mult
    # EMA100 Buffer Protection
    if weekly_ema100 is not None and ema_cross_filter:
        if direction == "BUY":
            min_tp = weekly_ema100 + ema100_buffer_pips * pip_value
            min_tp_pips = (min_tp - current_price) / pip_value
            tp_pips = max(tp_pips, min_tp_pips)
        else:
            max_tp = weekly_ema100 - ema100_buffer_pips * pip_value
            min_tp_pips = (current_price - max_tp) / pip_value
            tp_pips = max(tp_pips, min_tp_pips)
    return True, tp_pips, f"TP={tp_pips:.1f}p"


# ─── MC Timeframe Config ─────────────────────────────────────────────────────
if TIMEFRAME in ("H4", "1H", "15m"):
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": YF_INTERVAL, "YF_PERIOD_FULL": YF_PERIOD_FULL,
        "YF_PERIOD_RESAMPLE": YF_PERIOD_RESAMPLE,
        "MC_LOOKBACK": cfg(P, "H4_LOOKBACK", 90),
        "MC_FORECAST": cfg(P, "H4_FORECAST", 8),
        "PERIODS_YEAR": PERIODS_YEAR * 6,
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX {TIMEFRAME} MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })
else:
    MCConfig.set_timeframe(TIMEFRAME, {
        "YF_INTERVAL": cfg(P, "YF_INTERVAL_D", "1d"),
        "YF_PERIOD_FULL": cfg(P, "YF_PERIOD_FULL_D", "120d"),
        "YF_PERIOD_RESAMPLE": cfg(P, "YF_PERIOD_RESAMPLE_D", "180d"),
        "MC_LOOKBACK": cfg(P, "DAILY_LOOKBACK", 90),
        "MC_FORECAST": cfg(P, "DAILY_FORECAST", 5),
        "PERIODS_YEAR": cfg(P, "PERIODS_YEAR_D", 252),
        "MC_REPORT_TITLE": f"[{PROFILE_LABEL}] FX DAILY MONTE CARLO",
        "RESULTS_DIR": RESULTS_DIR,
    })


# ─── Pipeline & Strategy Config ─────────────────────────────────────────────
FEAT_CFG = FeatureConfig(
    use_atr=cfg(P, "USE_ATR", True),
    atr_sl_mult=ATR_SL_MULT, atr_tp_mult=ATR_TP_MULT, atr_period=ATR_PERIOD,
    use_macd=cfg(P, "USE_MACD", True), use_rsi=cfg(P, "USE_RSI", True),
    use_adx=cfg(P, "USE_ADX", True), model_type=cfg(P, "MODEL_TYPE", "xgboost"),
    target_horizon=cfg(P, "TARGET_HORIZON", 6),
    train_lookback_bars=cfg(P, "TRAIN_LOOKBACK_BARS", 5000),
)
STRAT_CFG = StrategyConfig(
    mode=MODE, min_conviction_score=MIN_CONVICTION_SCORE, base_min_edge=BASE_MIN_EDGE,
    mc_filter_mode=FilterMode.PENALIZE, regime_filter_mode=FilterMode.OFF,
    adx_filter_mode=FilterMode.OFF, pivot_filter_mode=FilterMode.PENALIZE,
    strength_gap_filter_mode=FilterMode.PENALIZE, cooldown_filter_mode=FilterMode.BLOCK,
)

fetcher = DataFetcher(use_oanda=True, oanda_api=api, oanda_granularity=OANDA_GRANULARITY)
feat_engine = FeatureEngine(FEAT_CFG)
strat_engine = StrategyEngine(STRAT_CFG, model=None, feature_list=[])
atr_mod = ATRModule(period=ATR_PERIOD)
MODEL_PATH = BASE_DIR / "trade_model_xgb.pkl"
model_wrapper = ModelWrapper(FEAT_CFG, model_path=MODEL_PATH)
last_closed = {} if REMOVE_COOLDOWN else load_cooldown(COOLDOWN_FILE, Direction)


# ─── Helper Functions ────────────────────────────────────────────────────────
def build_top_pairs(strength_scores, all_pairs, top_n=4, min_gap=0.25):
    ranked = sorted(strength_scores.items(), key=lambda x: x[1], reverse=True)
    strongest, weakest = [ccy for ccy, _ in ranked[:top_n]], [ccy for ccy, _ in ranked[-top_n:]]
    candidates = []
    for i in range(min(top_n, len(strongest), len(weakest))):
        base, quote = strongest[i], weakest[-(i+1)]
        if base == quote: continue
        gap = strength_scores[base] - strength_scores[quote]
        if abs(gap) >= min_gap:
            symbol = f"{base}{quote}=X" if f"{base}{quote}=X" in all_pairs else f"{quote}{base}=X"
            if symbol in all_pairs: candidates.append((symbol, abs(gap), base, quote))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [p[0] for p in candidates[:top_n]], candidates

def calc_weighted_score(pair: str, gap: float, rsi_val: float, adx_val: float,
                        xgb_prob: float, mc_pct_up: float):
    """RSI-FIXED Direction-Aware Consensus — identical logic across profiles"""
    strength_dir = "BUY" if gap >= MIN_STRENGTH_GAP else "SELL" if gap <= -MIN_STRENGTH_GAP else "NEUTRAL"
    xgb_dir = "BUY" if (xgb_prob or 0.0) >= XGB_BULLISH_THRESHOLD else "SELL"
    mc_dir = "BUY" if (mc_pct_up or 50.0) >= MC_BULLISH_THRESHOLD else "SELL"
    buy_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "BUY")
    sell_votes = sum(1 for d in (strength_dir, xgb_dir, mc_dir) if d == "SELL")
    logger.info(f"🤝 {pair}: Strength={strength_dir} | XGB={xgb_dir} | MC={mc_dir} | BUY={buy_votes}/3")

    if REQUIRE_DIRECTION_CONSENSUS:
        if buy_votes >= CONSENSUS_THRESHOLD: direction = "BUY"; logger.info(f"✅ {pair}: BUY consensus ({buy_votes}/3)")
        elif sell_votes >= CONSENSUS_THRESHOLD: direction = "SELL"; logger.info(f"✅ {pair}: SELL consensus ({sell_votes}/3)")
        else: logger.info(f"⏭️ {pair}: NO CONSENSUS → SKIP"); return None, None
    else:
        direction = "BUY" if gap > 0 else "SELL"

    S = max(0.0, min(100.0, abs(gap) / 3.5 * 100.0))
    rsi = max(0.0, min(100.0, rsi_val))
    R = max(0.0, min(100.0, (50.0 - rsi) * 2.0)) if direction == "BUY" else max(0.0, min(100.0, (rsi - 50.0) * 2.0))
    adx_normalized = min(adx_val * cfg(P, "ADX_SCALE_FACTOR", 2.0), 100.0)
    A = max(0.0, min(100.0, adx_normalized))
    X = max(0.0, min(100.0, (xgb_prob or 0.0) * 100.0)) or max(0.0, min(100.0, S*0.3 + R*0.3))
    M = max(0.0, min(100.0, mc_pct_up if mc_pct_up is not None else 50.0))
    FINAL = S*W_S + R*W_R + A*W_A + X*W_X + M*W_M
    return direction, {
        "S": round(S,1), "R": round(R,1), "A": round(A,1), "X": round(X,1), "M": round(M,1),
        "FINAL": round(FINAL,1), "PASS": FINAL >= MIN_CONVICTION_SCORE, "THRESHOLD": round(MIN_CONVICTION_SCORE,1),
    }


# ─── MAIN TRADING FLOW ───────────────────────────────────────────────────────
def main():
    global model_wrapper, strat_engine
    logger.info(f"\n🤖 RUN v6.8.6 {PROFILE_LABEL} — {ACCOUNT_NAME} | "
                f"FILTERS={'ON' if TREND_FILTER_ENABLED else 'OFF'} | "
                f"EMA100_WK={'ON' if WEEK_EMA100_FILTER_ENABLED else 'OFF'} | "
                f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | MAX_OPEN={MAX_OPEN}")
    logger.info(f"🔑 OANDA Account ID: {OANDA_ACCOUNT_ID}")

    if forex_market_closed(): return

    model_wrapper, strat_engine = ensure_model(
        MODEL_PATH, FEAT_CFG, model_wrapper, strat_engine,
        fetcher, feat_engine, ALL_PAIRS, YAHOO_TO_OANDA,
        lambda k,d: cfg(P,k,d),  # ← unified lookup
    )

    # Step 1 — Currency Strength
    logger.info("[STEP 1] Currency Strength...")
    strength_scores = build_strength_matrix()
    logger.info(format_strength_ranking(strength_scores))

    USE_TOP_PAIRS_ONLY = cfg(P, "USE_TOP_PAIRS_ONLY", False)
    TOP_PAIRS_COUNT = cfg(P, "TOP_PAIRS_COUNT", 4)
    TOP_PAIRS_MIN_GAP = cfg(P, "TOP_PAIRS_MIN_GAP", 0.25)
    
    EXCLUDE_CURRENCIES = cfg(P, "EXCLUDE_CURRENCIES", [])

    if USE_TOP_PAIRS_ONLY:
        selected_pairs, _ = build_top_pairs(strength_scores, ALL_PAIRS, TOP_PAIRS_COUNT, TOP_PAIRS_MIN_GAP)
        selected_pairs = selected_pairs or ALL_PAIRS[:]
        logger.info(f"🎯 AUTO-RANK: Top {len(selected_pairs)} pairs selected")
    else:
        selected_pairs = ALL_PAIRS[:]
        logger.info(f"📋 SCAN ALL: {len(selected_pairs)} pairs")

    # ─── APPLY EXCLUSION — BOTH BRANCHES ───────────────────────────────────────
    if EXCLUDE_CURRENCIES:
        before_count = len(selected_pairs)
        selected_pairs = [p for p in selected_pairs if not any(skip in p for skip in EXCLUDE_CURRENCIES)]
        skipped = sorted(set(ALL_PAIRS) - set(selected_pairs))
        logger.info(f"🚫 EXCLUSION: Skipped {before_count - len(selected_pairs)} pairs containing {EXCLUDE_CURRENCIES}: {', '.join(skipped)}")

    # Step 2 — Fetch Data
    pair_data, weekly_ema_cache = {}, {}
    for pair in selected_pairs:
        oanda = YAHOO_TO_OANDA.get(pair)
        if not oanda: logger.warning(f"⚠️ No OANDA mapping for {pair} — skipping"); continue
        try:
            raw = fetcher.fetch(pair, oanda, count=200)
            if raw.empty: continue
            df = feat_engine.build(raw).replace([np.inf,-np.inf], np.nan).ffill().bfill().fillna(0)
            if len(df) < 5: continue
            pair_data[pair] = {
                "df": df, "oanda": oanda, "raw": raw,
                "atr": df.iloc[-1].get("atr", 0.0),
                "rsi": df.iloc[-1].get("rsi", 50.0),
                "adx": df.iloc[-1].get("adx", -1.0),
            }
            weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, api)
        except Exception as e: logger.error(f"❌ Fetch failed {pair}: {e}")
    if not pair_data:
        logger.error("No pairs have usable data. Aborting.")
        send_telegram_message(f"❌ FX BOT {PROFILE_LABEL}: No usable data")
        return

    # Step 3 — Monte Carlo
    mc_cache = {}
    SKIP_MC_RUN = args.skip_mc or SKIP_MC
    if not SKIP_MC_RUN:
        logger.info("[STEP 3] Monte Carlo Forecasts...")
        mc_gen = MCGenerator(fetcher, YAHOO_TO_OANDA, simulations=SIMULATIONS, confidence=CONFIDENCE)
        for pair in selected_pairs:
            if pair not in pair_data: continue
            mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
            if ok:
                regime = mc_data.get("regime", "")
                if REQUIRE_STRONG_MOMENTUM and "STRONG MOMENTUM" not in regime:
                    logger.info(f"⏭️ {pair}: MC regime={regime} — SKIP"); continue
                mc_cache[pair] = mc_data
                logger.info(f"🎲 MC {pair}: {regime} | P_UP={mc_data['p_up']}%")
    else:
        logger.info("[STEP 3] MC Skipped — loading legacy...")
        for pair in selected_pairs:
            mc_data, ok = load_mc_legacy(pair, RESULTS_DIR, TODAY_STR, MC_MAX_AGE_HOURS)
            if ok: mc_cache[pair] = mc_data
    if args.mc_only: return

    # Step 4 — Multi-Timeframe Confluence
    tf_confluence = {}
    if MULTI_TF_CONFLUENCE:
        logger.info("[STEP 4] Multi-Timeframe Confluence...")
        for pair in selected_pairs:
            if pair not in pair_data: continue
            dirs = []
            for gran in {"H4":"H4","1H":"H1","15m":"M15"}.values():
                with contextlib.suppress(Exception):
                    raw_tf = fetch_candles(pair_data[pair]["oanda"], gran)
                    if len(raw_tf) < 5: continue
                    sig = strat_engine.generate_signal(pair, pair_data[pair]["oanda"],
                        feat_engine.build(raw_tf), None, strength_scores, raw_tf.iloc[-1]["Close"], 1.0)
                    if sig: dirs.append(sig.action)
            buy_c, sell_c = dirs.count("BUY"), dirs.count("SELL")
            passes = buy_c >= CONFLUENCE_REQUIRED_TFS or sell_c >= CONFLUENCE_REQUIRED_TFS
            tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}
            logger.info(f"🔗 CONFLUENCE {pair}: BUY={buy_c} SELL={sell_c} → {'✅ PASS' if passes else '❌ BLOCK'}")

    # Step 5 — Dynamic Exit Manager
    logger.info("[STEP 5] Dynamic Exit Manager...")
    def close_wrap(instr): return close_position(api, OANDA_ACCOUNT_ID, instr, send_telegram_message)
    dyn_mgr = DynamicPositionManager(
        api, OANDA_ACCOUNT_ID, TIMEFRAME,
        cfg(P, "BE_TRIGGER_ATR_MULT", 1.5), cfg(P, "TRAIL_TRIGGER_ATR_MULT", 2.5),
        cfg(P, "TRAIL_ATR_MULT", 1.5), cfg(P, "MAX_HOLD_BARS", 12),
        dynamic_tp=DYNAMIC_TP, tp_raise_thresh_pips=TP_RAISE_THRESHOLD_PIPS,
        telegram_send=send_telegram_message,
    )
    oanda_level = logging.getLogger("oandapyV20").level
    logging.getLogger("oandapyV20").setLevel(logging.CRITICAL)
    dyn_mgr.update_all(pair_data, close_wrap)
    logging.getLogger("oandapyV20").setLevel(oanda_level)

    # Step 6 — Scan Open Positions
    open_pos_by_oanda, open_pos_count = {}, 0
    logger.info("🔍 Checking open positions...")
    for pair in selected_pairs:
        oanda_inst = YAHOO_TO_OANDA.get(pair)
        if not oanda_inst: continue
        pos = get_open_position(api, OANDA_ACCOUNT_ID, oanda_inst)
        open_pos_by_oanda[oanda_inst] = pos is not None
        if pos is not None:
            open_pos_count += 1
            logger.info(f"📌 OPEN POSITION: {pair} → {oanda_inst} | {pos['side'].upper()} | units={pos['units']}")
    open_list = [o.replace("_","/") for o,s in open_pos_by_oanda.items() if s]
    ready_list = [p.replace("=X","") for p in selected_pairs if not open_pos_by_oanda.get(YAHOO_TO_OANDA.get(p), False)]
    logger.info(f"📊 Open positions: {open_pos_count}/{MAX_OPEN} | OPEN: {', '.join(open_list) or 'None'} | READY: {', '.join(ready_list) or 'None'}")

    # Step 7 — Score, Trend Filter, Smart TP & Execute
    logger.info("[STEP 7] Scoring + TREND FILTER + SMART TP...")
    # _trade_lines, pip_cache, pair_parts = {}, {p: pip_size(p) for p in selected_pairs}, {p: (p[:3], p[3:].replace("=X","")) for p in selected_pairs}
    pip_cache, pair_parts = {p: pip_size(p) for p in selected_pairs}, {p: (p[:3], p[3:].replace("=X","")) for p in selected_pairs}

    all_candidates = []

    for pair in selected_pairs:
        if pair not in pair_data:
            continue
        oanda = pair_data[pair]["oanda"]
        atr_val, rsi_val, adx_val = pair_data[pair]["atr"], pair_data[pair]["rsi"], pair_data[pair]["adx"]

        # Cooldown
        if pair in last_closed:
            d, r = last_closed[pair]
            if r > 0: last_closed[pair] = (d, r-1); logger.info(f"⏳ COOLDOWN {pair}: {r-1} runs remaining — SKIP"); continue
            else:
                del last_closed[pair]

        # Already Open → SKIP DUPLICATE
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: position already open — SKIP"); continue

        # Current Price
        try:
            prices = get_live_prices(oanda)
            if prices and "bid" in prices and "ask" in prices:
                current = prices["bid"]; spread_pips = abs(prices["ask"] - prices["bid"]) / pip_cache[pair]
            else:
                raise ValueError()
        except Exception:
            current = float(pair_data[pair]["df"].iloc[-1]["Close"]); spread_pips = 1.0

        # Strength Gap
        base, quote = pair_parts[pair]
        gap = strength_scores.get(base, 0) - strength_scores.get(quote, 0)
        if abs(gap) < MIN_STRENGTH_GAP:
            logger.info(f"⏭️ {pair}: gap={abs(gap):.2f} < MIN={MIN_STRENGTH_GAP} — SKIP"); continue
        logger.info(f"📈 {pair}: gap={abs(gap):.2f} ≥ {MIN_STRENGTH_GAP} — QUALIFIED")

        # Confluence Filter
        if MULTI_TF_CONFLUENCE and not tf_confluence.get(pair, {}).get("passes", True):
            logger.info(f"🚫 {pair}: confluence fail — SKIP"); continue

        # Model & MC
        sig = strat_engine.generate_signal(pair, oanda, pair_data[pair]["df"], mc_cache.get(pair), strength_scores, current, spread_pips)
        prob_raw = getattr(sig, "model_p_up", None) or 0.0
        mc_pct_up = mc_cache.get(pair, {}).get("p_up", 50.0)

        # Score
        direction, w = calc_weighted_score(pair, gap, rsi_val, adx_val, prob_raw, mc_pct_up)
        if not (direction and w and w["PASS"]):
            if w and not w["PASS"]: logger.info(f"➖ REASON: FINAL {w['FINAL']:.1f} < {w['THRESHOLD']}")
            continue

        logger.info(f"⚖️  SCORE {pair} {direction} | S={w['S']:5.1f}×{W_S:.2f}={w['S']*W_S:4.1f}  "
                    f"R={w['R']:5.1f}×{W_R:.2f}={w['R']*W_R:4.1f}  A={w['A']:5.1f}×{W_A:.2f}={w['A']*W_A:4.1f}  "
                    f"X={w['X']:5.1f}×{W_X:.2f}={w['X']*W_X:4.1f}  M={w['M']:5.1f}×{W_M:.2f}={w['M']*W_M:4.1f}  | FINAL={w['FINAL']:5.1f}")

        # ─── TREND FILTER + SMART TP ────────────────────────────────
        weekly_ema100_price = weekly_ema_cache.get(oanda) if WEEK_EMA100_FILTER_ENABLED else None
        allow_entry, smart_tp_pips, tp_info = evaluate_trend_and_tp(
            PROFILE_NAME, direction, mc_pct_up, current, pip_cache[pair],
            pair_data[pair]["df"], weekly_ema100_price,
            ema_cross_filter=TREND_FILTER_ENABLED,
            fast_period=EMA_PERIOD_FAST, slow_period=EMA_PERIOD_SLOW,
            base_tp_pips=BASE_TP_PIPS, mc_strong_threshold=MC_STRONG_THRESHOLD,
            tp_mult=TP_MULT, tp_strong_mult=TP_STRONG_MULT,
            ema100_buffer_pips=EMA100_BUFFER_PIPS, timeframe=TIMEFRAME,
        )
        if not allow_entry: continue

        # SL & TP
        dec = 3 if "JPY" in pair else 5
        if cfg(P, "SL_USE_ZONE_HIERARCHY", True):
            try:
                h4_df = fetch_candles(api, oanda, "H4", count=5)
                if h4_df is None or len(h4_df) < 5: raise ValueError(f"insufficient H4 candles")
                h4_closed = [{"high": float(r["High"]), "low": float(r["Low"])} for _, r in h4_df.iloc[:-1].iterrows()]
                sl_price, sl_pips, skip_trade = calculate_stop_loss(direction, current, h4_closed, pip_cache[pair])
                if skip_trade: logger.warning(f"🚫 {pair}: SL distance > 200pips — ABORT"); continue
                sl_price = round(sl_price, dec)
            except Exception:
                sl_pips = max(MIN_SL_PIPS_JPY if "JPY" in pair else MIN_SL_PIPS,
                              round(atr_val / pip_cache[pair] * ATR_SL_MULT, 1))
                sl_price = round(current - sl_pips * pip_cache[pair], dec) if direction == "BUY" else round(current + sl_pips * pip_cache[pair], dec)
        else:
            sl_pips = max(MIN_SL_PIPS_JPY if "JPY" in pair else MIN_SL_PIPS,
                          round(atr_val / pip_cache[pair] * ATR_SL_MULT, 1))
            sl_price = round(current - sl_pips * pip_cache[pair], dec) if direction == "BUY" else round(current + sl_pips * pip_cache[pair], dec)

        tp_price = round(current + smart_tp_pips * pip_cache[pair], dec) if direction == "BUY" else round(current - smart_tp_pips * pip_cache[pair], dec)
        all_candidates.append((-w["FINAL"], w["FINAL"], pair, oanda, direction, current, sl_price, tp_price, dec, smart_tp_pips))

    # Execute Top Candidates
    logger.info(f"🏆 RANKED: {len(all_candidates)} passed → opening top {min(MAX_OPEN, len(all_candidates))}")
    for i, (_, score, pair, _, dir, _, _, _, _, tp_pips) in enumerate(all_candidates, 1):
        logger.info(f"   #{i} — {pair} {dir} SCORE={score:.1f} SMART-TP={tp_pips:.1f}p")

    executed_in_this_run = set()
    for _, FINAL, pair, oanda, direction, current, sl_price, tp_price, dec, tp_pips in all_candidates:
        if open_pos_by_oanda.get(oanda, False):
            logger.info(f"⏭️ {pair}: already open — SKIP")
            continue
        if oanda in executed_in_this_run:
            logger.info(f"⏭️ {pair}: already selected THIS run — SKIP")
            continue

        logger.info(f"📤 EXECUTE: {pair} {direction} | SL={sl_price:.{dec}f} | TP={tp_price:.{dec}f} | TP={tp_pips:.1f}p")
        try:
            lot = DEFAULT_LOT_SIZE
            result = open_oanda_order(
                api, OANDA_ACCOUNT_ID, oanda,
                direction, lot,
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
            )
            executed_in_this_run.add(oanda)
            if result.get("ok"):
                logger.info(f"✅ ORDER OPENED: {pair} {direction} | SL={sl_price:.{dec}f} TP={tp_price:.{dec}f}")
            else:
                logger.error(f"❌ ORDER FAILED: {pair} — {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"❌ EXCEPTION opening {pair}: {e}")

    logger.info(f"\n✅ {PROFILE_LABEL} RUN COMPLETE")


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⏹️ Interrupted by user")
    except Exception as e:
        logger.critical(f"💥 FATAL ERROR: {e}", exc_info=True)
        send_telegram_message(f"💥 FX BOT {PROFILE_LABEL} FATAL ERROR:\n{str(e)}")
