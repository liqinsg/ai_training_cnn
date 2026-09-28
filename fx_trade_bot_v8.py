#!/usr/bin/env python3
"""
fx_trade_bot_v8_1 — OO Refactor (review fixes)

Fixes vs v8.0:
  1. build_config 统一收纳全部配置键；run() 内不再出现 cfg(c["P"], ...)
  2. 统一 p_fn（已收进 c 的走 c，未迁移键回退到 cfg(P)，向后兼容）
  3. 修复对账逻辑：OpenTrades 失败时跳过对账，不再用空 open_ids 把所有未平仓单标记为 SL_OR_TP_HIT
  4. 持仓统计改用一次 OpenTrades（覆盖全部货币对），修复 MAX_OPEN_POSITIONS 失效；失败时回退 per-pair 查询并告警
  5. close_wrap 接入真实 close_position（带参数防御与日志，不再是静默 no-op）
  6. 多周期共振方向判断同时兼容 Direction 枚举与 "BUY"/"SELL" 字符串
  7. 信号日志 SIGNAL_LOG 真正写入
  8. WEEK_EMA100_FILTER_ENABLED=False 时不再拉取周线 EMA（省 API、降限流风险）
  9. 清理重复/未用 import、无意义互斥组、STEP 编号、mkdir 缺 parents；EXCLUDE_PAIRS 不再被 run() 原地修改
 10. LIVE 模式下 DEFAULT_LOT_SIZE 过小时打印告警

Usage:
    python fx_trade_bot_v8_1.py -p 2
    python fx_trade_bot_v8_1.py -p 2 --debug --dry-run
"""
from __future__ import annotations

import argparse
import contextlib
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from oandapyV20.endpoints.trades import OpenTrades

from config_bot_v7 import cfg, load_profile
from config_oanda import get_oanda_profile
from data_pipeline import DataFetcher, FeatureConfig, FeatureEngine, ModelWrapper
from fx.strategy.base import TradeContext
from fx.strategy.registry import get_strategy
from fx_trade_bot_mc import MCGenerator
from fx_trade_bot_ml import ensure_model
from fx_trade_bot_utils import (
    DynamicPositionManager,
    append_to_csv,
    check_margin_available,
    close_position,
    fetch_candles,
    fetch_weekly_ema100,
    forex_market_closed_schedule as forex_market_closed,
    get_open_position,
    init_csv,
    load_cooldown,
    load_mc_legacy,
    open_oanda_order_simple as open_oanda_order,
    update_trade_on_close,
)
from strategy_decision import Direction, StrategyConfig, StrategyEngine
from telegram_message import send_telegram_message
from utils.logging_utils import get_logger
from utils.strategy_helpers import (
    build_strength_matrix,
    build_top_pairs,
    format_strength_ranking,
)

VERSION = "8.1"
logger = get_logger(__name__)

# v8.1: 这些键在 v8.0 里散落在 run() 中通过 cfg(c["P"], ...) 读取，
# 现在统一在 build_config 里收纳一次。
_HOIST_KEYS_DEFAULTS = [
    # Feature / ML
    ("USE_ATR", True),
    ("ATR_SL_MULT", 2.0),
    ("ATR_TP_MULT", 3.0),
    ("ATR_PERIOD", 14),
    ("USE_MACD", True),
    ("USE_RSI", True),
    ("USE_ADX", True),
    ("MODEL_TYPE", "xgboost"),
    ("TARGET_HORIZON", 6),
    ("TRAIN_LOOKBACK_BARS", 5000),
    # Strategy decision
    ("MODE", "LEVEL10"),
    ("MIN_CONVICTION_SCORE", 30.0),
    ("BASE_MIN_EDGE", 0.50),
    # Dynamic exit manager
    ("BE_TRIGGER_ATR_MULT", 1.5),
    ("TRAIL_TRIGGER_ATR_MULT", 2.5),
    ("TRAIL_ATR_MULT", 1.5),
    ("MAX_HOLD_BARS", 12),
    ("DYNAMIC_TP", False),
    ("TP_RAISE_THRESHOLD_PIPS", 15),
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=f"FX Trade Bot v{VERSION} · OO Refactor"
    )
    # v8.1: 原互斥组里只有 -p 一个选项，无意义，直接 required=True
    parser.add_argument("-p", "--profile", type=int, choices=[1, 2, 3, 4, 9], required=True)
    parser.add_argument("--timeframe", type=str, default="15m", choices=["15m", "1H", "H4"])
    parser.add_argument(
        "--trend-filter-enabled",
        type=str.lower,
        choices=["true", "false", "1", "0"],
        default=None,
    )
    parser.add_argument("--confluence", action="store_true", default=None)
    parser.add_argument("--no-confluence", action="store_false", dest="confluence")
    parser.add_argument("--skip-mc", action="store_true")
    parser.add_argument("--mc-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--live", action="store_true", default=False)
    parser.add_argument("--account", type=str, default=None)
    parser.add_argument(
        "--zero-strength-guard",
        type=str.lower,
        choices=["on", "off"],
        default=None,
    )
    parser.add_argument("--debug", action="store_true", default=False)
    return parser.parse_args()


def _parse_bool_arg(v):
    if v is None:
        return None
    return v in ("true", "1")


def _action_eq(a, target):
    """v8.1: 方向判断同时兼容 Direction 枚举与裸字符串。"""
    if a is target:
        return True
    if str(a) == target:
        return True
    if getattr(a, "value", None) == target:
        return True
    if getattr(a, "name", None) == target:
        return True
    return False


def build_config(args):
    profile_name = f"profile{args.profile}"
    print(f"Selected profile -> {profile_name!r}")
    P = load_profile(profile_name)
    S = P["strategy"]

    oanda_ctx = get_oanda_profile(
        profile_num=str(args.profile),
        account_override=args.account,
        env_override="live" if args.live else None,
    )
    api = oanda_ctx["api"]
    account_id = oanda_ctx["account_id"]
    is_live = oanda_ctx["is_live"]
    force_live = bool(args.live)

    dry_run_env = os.getenv("DRY_RUN", "").strip().lower() in ("true", "1", "yes")
    dry_run = args.dry_run or dry_run_env

    base_dir = Path(__file__).resolve().parent
    profile_label = S["LABEL"]
    account_name = P["account_alias"]
    results_dir = Path(S["RESULTS_DIR"])
    results_dir.mkdir(parents=True, exist_ok=True)  # v8.1: +parents=True

    trend_filter_enabled = cfg(P, "TREND_FILTER_ENABLED", False)
    parsed = _parse_bool_arg(args.trend_filter_enabled)
    if parsed is not None:
        trend_filter_enabled = parsed

    zero_strength_guard = cfg(P, "ZERO_STRENGTH_GUARD", False)
    if args.zero_strength_guard is not None:
        zero_strength_guard = (args.zero_strength_guard == "on")

    default_lot_size = int(os.getenv("DEFAULT_LOT_SIZE", cfg(P, "DEFAULT_LOT_SIZE", 10000)))
    if is_live or force_live:
        default_lot_size = int(os.getenv("DEFAULT_LOT_SIZE", 1))

    multi_tf_confluence = cfg(P, "MULTI_TF_CONFLUENCE", False)
    if args.confluence is not None:
        multi_tf_confluence = args.confluence

    oanda_granularity_map = {"15m": "M15", "1H": "H1", "H4": "H4", "D": "D"}

    c = {
        "args": args,
        "P": P,
        "S": S,
        "api": api,
        "OANDA_ACCOUNT_ID": account_id,
        "IS_LIVE": is_live,
        "FORCE_LIVE": force_live,
        "DRY_RUN": dry_run,
        "BASE_DIR": base_dir,
        "PROFILE_LABEL": profile_label,
        "PROFILE_NAME": profile_name,
        "ACCOUNT_NAME": account_name,
        "RESULTS_DIR": results_dir,
        "TODAY_STR": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "TODAY_STR_DASH": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "TREND_FILTER_ENABLED": trend_filter_enabled,
        "WEEK_EMA100_FILTER_ENABLED": cfg(P, "WEEK_EMA100_FILTER_ENABLED", False),
        "ZERO_STRENGTH_GUARD": zero_strength_guard,
        "DEFAULT_LOT_SIZE": default_lot_size,
        "MAX_OPEN_POSITIONS": cfg(P, "MAX_OPEN_POSITIONS", 4),
        "ALL_PAIRS": cfg(P, "ALL_PAIRS"),
        "YAHOO_TO_OANDA": cfg(P, "YAHOO_TO_OANDA"),
        "EXCLUDE_PAIRS": list(cfg(P, "EXCLUDE_PAIRS", []) or []),
        "TIMEFRAME": args.timeframe,
        "OANDA_GRANULARITY_MAP": oanda_granularity_map,
        "OANDA_GRANULARITY": oanda_granularity_map.get(args.timeframe, "H4"),
        "SIMULATIONS": cfg(P, "SIMULATIONS", 5000),
        "MC_BAND_PCT": cfg(P, "MC_BAND_PCT", 90),
        "MC_MAX_AGE_HOURS": cfg(P, "MC_MAX_AGE_HOURS", 24),
        "SKIP_MC": cfg(P, "SKIP_MC", False),
        "REQUIRE_STRONG_MOMENTUM": cfg(P, "REQUIRE_STRONG_MOMENTUM", False),
        "USE_TOP_PAIRS_ONLY": cfg(P, "USE_TOP_PAIRS_ONLY", True),
        "TOP_PAIRS_COUNT": cfg(P, "TOP_PAIRS_COUNT", 4),
        "TOP_PAIRS_MIN_GAP": cfg(P, "TOP_PAIRS_MIN_GAP", 0.25),
        "MULTI_TF_CONFLUENCE": multi_tf_confluence,
        "CONFLUENCE_REQUIRED_TFS": cfg(P, "CONFLUENCE_REQUIRED_TFS", 2),
        # v8.1: 移除死键 MIN_STRENGTH_GAP（原读 MIN_SCORE_GAP 且从未使用）
        "oanda_env": oanda_ctx["env"],
        "PARAM_SET": P.get("param_set", "baseline"),
    }

    # v8.1: 统一收纳原本散落在 run() 里的 cfg(c["P"], ...) 键
    for key, default in _HOIST_KEYS_DEFAULTS:
        c[key] = cfg(P, key, default)

    # v8.1: MODEL_PATH 在此处解析为绝对路径，run() 直接用
    model_path = Path(P.get("MODEL_PATH", "trade_model_xgb.pkl"))
    if not model_path.is_absolute():
        model_path = base_dir / model_path
    c["MODEL_PATH"] = model_path

    c["TRADE_LOG_PATH"] = results_dir / f"{c['TODAY_STR_DASH']}_trade_log.csv"
    c["SIGNAL_LOG_PATH"] = results_dir / f"{c['TODAY_STR_DASH']}_signal_log.csv"

    # v8.1: 统一 p_fn。已收进 c 的键走 c，策略层尚未迁移的键回退到 cfg(P)。
    def _p_fn(key, default):
        if key in c:
            return c[key]
        return cfg(c["P"], key, default)

    c["p_fn"] = _p_fn
    return c


class Engine:
    def __init__(self, c):
        self.c = c
        self.api = c["api"]
        self.account_id = c["OANDA_ACCOUNT_ID"]
        # v8.1: PARAM_SET 已收进 c
        self.strategy = get_strategy(c["PARAM_SET"], c["P"])
        self.log = logger
        self.last_closed = load_cooldown(Path(c["S"]["COOLDOWN_FILE"]), Direction)
        self._init_audit()
        self._banner()

    def _init_audit(self):
        trade_header = [
            "timestamp", "trade_id", "profile", "account", "pair", "direction",
            "entry_price", "sl_price", "tp_price",
            "score_final", "score_s", "score_r", "score_a", "score_x", "score_m",
            "pips", "profit_usd", "exit_reason", "exit_time",
        ]
        signal_header = [
            "timestamp", "profile", "account", "pair",
            "score_final", "score_s", "score_r", "score_a", "score_x", "score_m",
            "action_taken",
        ]
        init_csv(self.c["TRADE_LOG_PATH"], trade_header)
        init_csv(self.c["SIGNAL_LOG_PATH"], signal_header)

    def _banner(self):
        c = self.c
        mode = "DRY-RUN" if c["DRY_RUN"] else ("DEMO" if not c["IS_LIVE"] else "LIVE")
        print(
            f"""
============================================================
  FX TRADE BOT v{VERSION} — STARTUP
============================================================
  Profile   : {c['args'].profile} — {c['ACCOUNT_NAME']} ({c['PARAM_SET']})
  Strategy  : {self.strategy.name}
  Mode      : {mode}
  Account   : {c['OANDA_ACCOUNT_ID']}
  Env       : {c['oanda_env']}
  Lot size  : {c['DEFAULT_LOT_SIZE']}
============================================================
"""
        )
        if c["IS_LIVE"] and c["DEFAULT_LOT_SIZE"] <= 10:
            self.log.warning(
                f"LIVE mode with very small DEFAULT_LOT_SIZE={c['DEFAULT_LOT_SIZE']} "
                f"— confirm this is intended."
            )

    def _fetch_open_trades(self):
        """v8.1: 一次调用拿全部持仓；失败返回 None，调用方决定回退/跳过。"""
        try:
            return self.api.request(
                OpenTrades(accountID=self.account_id)
            ).get("trades", [])
        except Exception as e:
            self.log.warning(f"OpenTrades fetch failed: {e}")
            return None

    def _log_signal(self, sig, action):
        """v8.1: 信号日志真正落盘。"""
        c = self.c
        with contextlib.suppress(Exception):
            append_to_csv(c["SIGNAL_LOG_PATH"], {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profile": c["PROFILE_NAME"],
                "account": c["ACCOUNT_NAME"],
                "pair": getattr(sig, "oanda", getattr(sig, "pair", "")),
                "score_final": getattr(sig, "score_final", ""),
                "score_s": getattr(sig, "score_s", ""),
                "score_r": getattr(sig, "score_r", ""),
                "score_a": getattr(sig, "score_a", ""),
                "score_x": getattr(sig, "score_x", ""),
                "score_m": getattr(sig, "score_m", ""),
                "action_taken": action,
            })

    def run(self):
        c = self.c
        self.log.info(
            f"RUN v{VERSION} {c['PROFILE_LABEL']} — {c['ACCOUNT_NAME']} | "
            f"FILTERS={'ON' if c['TREND_FILTER_ENABLED'] else 'OFF'} | "
            f"DRY-RUN={'ON' if c['DRY_RUN'] else 'OFF'} | "
            f"ENV={'LIVE' if c['IS_LIVE'] else 'DEMO'} | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"MAX_OPEN={c['MAX_OPEN_POSITIONS']}"
        )

        # v8.1: 只拉一次全部持仓，对账与仓位统计复用，避免 N 次 API 调用与盲区。
        open_trades = self._fetch_open_trades()

        # ── Reconcile closed trades ──
        try:
            if c["TRADE_LOG_PATH"].exists():
                rdf = pd.read_csv(c["TRADE_LOG_PATH"], dtype={"trade_id": str})
                if open_trades is None:
                    # v8.1: 关键修复——拿不到持仓时绝不用空集继续对账，否则全部未平仓单会被误标 SL_OR_TP_HIT
                    self.log.warning("Reconciliation skipped: OpenTrades unavailable")
                else:
                    open_ids = {str(t["id"]) for t in open_trades}
                    for _, row in rdf.iterrows():
                        if pd.notna(row.get("exit_time")):
                            continue
                        tid = str(row.get("trade_id", ""))
                        if not tid or tid.startswith("DRY_RUN_"):
                            continue
                        if tid not in open_ids:
                            update_trade_on_close(
                                str(row.get("pair", "")),
                                c["TRADE_LOG_PATH"],
                                self.api,
                                self.account_id,
                                "SL_OR_TP_HIT",
                            )
        except Exception as e:
            self.log.warning(f"Reconciliation failed: {e}")

        # ── Market closed guard ──
        if not c["args"].debug and forex_market_closed():
            return
        if c["args"].debug:
            self.log.info("DEBUG MODE — market-closed guard bypassed")

        # ── STEP 0: Shared ML pipeline (一个 FeatureConfig 同时用于训练与推理) ──
        self.log.info("[STEP 0] Shared ML pipeline...")
        fc = FeatureConfig(
            use_atr=c["USE_ATR"],
            atr_sl_mult=c["ATR_SL_MULT"],
            atr_tp_mult=c["ATR_TP_MULT"],
            atr_period=c["ATR_PERIOD"],
            use_macd=c["USE_MACD"],
            use_rsi=c["USE_RSI"],
            use_adx=c["USE_ADX"],
            model_type=c["MODEL_TYPE"],
            target_horizon=c["TARGET_HORIZON"],
            train_lookback_bars=c["TRAIN_LOOKBACK_BARS"],
        )
        model_path = c["MODEL_PATH"]
        strat_cfg = StrategyConfig(
            mode=c["MODE"],
            min_conviction_score=c["MIN_CONVICTION_SCORE"],
            base_min_edge=c["BASE_MIN_EDGE"],
        )
        fetcher = DataFetcher(
            use_oanda=True,
            oanda_api=self.api,
            oanda_granularity=c["OANDA_GRANULARITY"],
        )
        feat_engine = FeatureEngine(fc)
        model_wrapper = ModelWrapper(fc, model_path=model_path)
        strat_engine = StrategyEngine(strat_cfg, model=None, feature_list=[])
        model_wrapper, strat_engine = ensure_model(
            model_path, fc, model_wrapper, strat_engine,
            fetcher, feat_engine,
            c["ALL_PAIRS"], c["YAHOO_TO_OANDA"],
            c["p_fn"],  # v8.1: 统一 p_fn
        )

        # ── STEP 1: Currency Strength ──
        self.log.info("[STEP 1] Currency Strength...")
        strength_scores = build_strength_matrix()
        self.log.info(format_strength_ranking(strength_scores))

        majors = ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]
        zero_ccys = [
            cc for cc in majors
            if cc not in strength_scores
            or strength_scores[cc] == 0.0
            or np.isnan(strength_scores[cc])
        ]
        # v8.1: 用本地变量，不原地修改 c["EXCLUDE_PAIRS"]（避免配置被副作用污染）
        excluded = list(c["EXCLUDE_PAIRS"])
        if c["ZERO_STRENGTH_GUARD"] and zero_ccys:
            self.log.warning(
                f"Zero-strength currencies: [{', '.join(zero_ccys)}] -> excluded"
            )
            excluded = sorted(set(excluded + zero_ccys))

        # ── STEP 2: Select pairs ──
        if c["USE_TOP_PAIRS_ONLY"]:
            selected_pairs, _ = build_top_pairs(
                strength_scores,
                c["ALL_PAIRS"],
                c["TOP_PAIRS_COUNT"],
                c["TOP_PAIRS_MIN_GAP"],
            )
            selected_pairs = selected_pairs or c["ALL_PAIRS"][:]
            self.log.info(f"Top {len(selected_pairs)} pairs selected")
        else:
            selected_pairs = c["ALL_PAIRS"][:]
            self.log.info(f"Scanning all {len(selected_pairs)} pairs")

        if excluded:
            before = len(selected_pairs)
            selected_pairs = [
                p for p in selected_pairs
                if not any(skip in p for skip in excluded)
            ]
            self.log.info(f"EXCLUSION: {before}->{len(selected_pairs)} pairs")

        if not selected_pairs:
            self.log.error("No pairs after exclusion — aborting")
            send_telegram_message(f"{c['PROFILE_LABEL']}: No pairs to scan")
            return

        # ── STEP 3: Fetch data ──
        self.log.info("[STEP 3] Fetch Data...")
        pair_data = {}
        weekly_ema_cache = {}
        for pair in selected_pairs:
            oanda = c["YAHOO_TO_OANDA"].get(pair)
            if not oanda:
                continue
            try:
                raw = fetcher.fetch(pair, oanda, count=200)
                if raw.empty:
                    continue
                df = (
                    feat_engine.build(raw)
                    .replace([np.inf, -np.inf], np.nan)
                    .ffill().bfill().fillna(0)
                )
                if len(df) < 5:
                    continue
                pair_data[pair] = {
                    "df": df,
                    "oanda": oanda,
                    "raw": raw,
                    "atr": float(df.iloc[-1].get("atr", 0.0)),
                    "rsi": float(df.iloc[-1].get("rsi", 50.0)),
                    "adx": float(df.iloc[-1].get("adx", -1.0)),
                }
                # v8.1: 过滤器关闭时不再拉周线 EMA，省 API
                if c["WEEK_EMA100_FILTER_ENABLED"]:
                    weekly_ema_cache[oanda] = fetch_weekly_ema100(oanda, self.api)
            except Exception as e:
                self.log.error(f"Fetch failed {pair}: {e}")

        if not pair_data:
            self.log.error("No usable data — aborting")
            send_telegram_message(f"{c['PROFILE_LABEL']}: No usable data")
            return

        # ── STEP 4: Monte Carlo ──
        mc_cache = {}
        skip_mc_run = c["args"].skip_mc or c["SKIP_MC"]
        if not skip_mc_run:
            self.log.info("[STEP 4] Monte Carlo Forecasts...")
            mc_gen = MCGenerator(
                fetcher,
                c["YAHOO_TO_OANDA"],
                simulations=c["SIMULATIONS"],
                confidence=c["MC_BAND_PCT"] / 100.0,
            )
            for pair in selected_pairs:
                if pair not in pair_data:
                    continue
                mc_data, ok = mc_gen.run_for_pair(pair, df=pair_data[pair]["raw"])
                if ok:
                    regime = mc_data.get("regime", "")
                    if c["REQUIRE_STRONG_MOMENTUM"] and "STRONG MOMENTUM" not in regime:
                        continue
                    mc_cache[pair] = mc_data
                    self.log.info(
                        f"MC {pair}: {regime} | P_UP={mc_data.get('p_up', '')}%"
                    )
        else:
            self.log.info("[STEP 4] MC skipped — loading legacy...")
            for pair in selected_pairs:
                mc_data, ok = load_mc_legacy(
                    pair, c["RESULTS_DIR"], c["TODAY_STR"], c["MC_MAX_AGE_HOURS"]
                )
                if ok:
                    mc_cache[pair] = mc_data

        if c["args"].mc_only:
            self.log.info("MC-only mode — stopping after Monte Carlo step")
            return

        # ── STEP 5: Multi-TF Confluence ──
        tf_confluence = {}
        if c["MULTI_TF_CONFLUENCE"]:
            self.log.info("[STEP 5] Multi-Timeframe Confluence...")
            for pair in selected_pairs:
                if pair not in pair_data:
                    continue
                dirs = []
                for gran in ("H4", "H1", "M15"):
                    with contextlib.suppress(Exception):
                        raw_tf = fetch_candles(pair_data[pair]["oanda"], gran)
                        if len(raw_tf) < 5:
                            continue
                        sig = strat_engine.generate_signal(
                            pair,
                            pair_data[pair]["oanda"],
                            feat_engine.build(raw_tf),
                            None,
                            strength_scores,
                            raw_tf.iloc[-1]["Close"],
                            1.0,
                        )
                        if sig:
                            dirs.append(sig.action)
                # v8.1: 兼容 Direction 枚举与字符串，避免 count("BUY") 恒为 0
                buy_c = sum(1 for a in dirs if _action_eq(a, "BUY"))
                sell_c = sum(1 for a in dirs if _action_eq(a, "SELL"))
                passes = (
                    buy_c >= c["CONFLUENCE_REQUIRED_TFS"]
                    or sell_c >= c["CONFLUENCE_REQUIRED_TFS"]
                )
                tf_confluence[pair] = {"buy": buy_c, "sell": sell_c, "passes": passes}

        # ── STEP 6: Dynamic Exit Manager ──
        self.log.info("[STEP 6] Dynamic Exit Manager...")

        def close_wrap(*args, **kwargs):
            """v8.1: 不再是静默 no-op。尝试从参数中识别 instrument 并真实平仓；
            若识别失败则打日志，便于确认 DynamicPositionManager 的回调契约。"""
            instrument = (
                kwargs.get("instrument")
                or kwargs.get("pair")
                or kwargs.get("oanda")
            )
            if not instrument and args:
                first = args[0]
                if isinstance(first, str):
                    instrument = first
                elif isinstance(first, dict):
                    instrument = (
                        first.get("instrument")
                        or first.get("pair")
                        or first.get("oanda")
                    )
            reason = kwargs.get("reason", "DYNAMIC_EXIT")
            if not instrument:
                self.log.warning(
                    f"close_wrap: cannot determine instrument; "
                    f"args={args!r} keys={list(kwargs)}"
                )
                return None
            try:
                self.log.info(f"DYNAMIC CLOSE {instrument} ({reason})")
                if not c["DRY_RUN"]:
                    # 假设 close_position(api, account_id, instrument)；若签名不同请在此调整
                    return close_position(self.api, self.account_id, instrument)
            except Exception as e:
                self.log.error(f"close_wrap failed {instrument}: {e}")
            return None

        dyn_mgr = DynamicPositionManager(
            self.api,
            self.account_id,
            c["TIMEFRAME"],
            c["BE_TRIGGER_ATR_MULT"],
            c["TRAIL_TRIGGER_ATR_MULT"],
            c["TRAIL_ATR_MULT"],
            c["MAX_HOLD_BARS"],
            dynamic_tp=c["DYNAMIC_TP"],
            tp_raise_thresh_pips=c["TP_RAISE_THRESHOLD_PIPS"],
            telegram_send=send_telegram_message,
            dry_run=c["DRY_RUN"],
        )
        dyn_mgr.update_all(pair_data, close_wrap)

        # ── STEP 7: Open positions (一次 OpenTrades，覆盖全部货币对) ──
        self.log.info("[STEP 7] Open Positions...")
        open_pos_by_oanda = {}
        if open_trades is not None:
            open_instruments = {t["instrument"] for t in open_trades}
            open_pos_count = len(open_instruments)
            for pair in selected_pairs:
                oanda = c["YAHOO_TO_OANDA"].get(pair)
                if oanda:
                    open_pos_by_oanda[oanda] = oanda in open_instruments
        else:
            # 回退：逐对查询（仅覆盖 selected_pairs，有盲区，故告警）
            self.log.warning(
                "OpenTrades unavailable — fell back to per-pair position check "
                "(selected pairs only; MAX_OPEN_POSITIONS may be undercounted)"
            )
            open_pos_count = 0
            for pair in selected_pairs:
                oanda = c["YAHOO_TO_OANDA"].get(pair)
                if not oanda:
                    continue
                pos = get_open_position(self.api, self.account_id, oanda)
                open_pos_by_oanda[oanda] = pos is not None
                if pos:
                    open_pos_count += 1

        open_slots = max(0, c["MAX_OPEN_POSITIONS"] - open_pos_count)
        self.log.info(
            f"Open: {open_pos_count}/{c['MAX_OPEN_POSITIONS']} | slots={open_slots}"
        )

        # ── STEP 8: Strategy evaluation ──
        self.log.info(f"[STEP 8] Strategy={self.strategy.name} — evaluate...")
        ctx = TradeContext(
            api=self.api,
            account_id=self.account_id,
            strength_scores=strength_scores,
            pair_data=pair_data,
            mc_cache=mc_cache,
            weekly_ema_cache=weekly_ema_cache,
            tf_confluence=tf_confluence,
            selected_pairs=selected_pairs,
            open_pos_by_oanda=open_pos_by_oanda,
            cooldown=self.last_closed,
            cfg=c["P"],
            p_fn=c["p_fn"],  # v8.1: 统一 p_fn
            strat_engine=strat_engine,
            fetcher=fetcher,
            feat_engine=feat_engine,
            open_slots_remaining=open_slots,
            log=self.log,
        )
        candidates = self.strategy.evaluate(ctx)
        self.log.info(f"Strategy returned {len(candidates)} ranked candidates")

        # ── STEP 9: Execute orders ──
        self.log.info("[STEP 9] Execute orders...")
        executed_count = 0
        executed_in_this_run = set()
        for sig in candidates:
            if executed_count >= open_slots:
                self._log_signal(sig, "SKIP_SLOT_FULL")
                continue
            if open_pos_by_oanda.get(sig.oanda, False):
                self._log_signal(sig, "SKIP_ALREADY_OPEN")
                continue
            if sig.oanda in executed_in_this_run:
                self._log_signal(sig, "SKIP_DUP_IN_RUN")
                continue

            lot = max(1, int(c["DEFAULT_LOT_SIZE"] * sig.lot_mult))
            self.log.info(
                f"EXECUTE: {sig.pair} {sig.direction} | "
                f"SL={sig.sl_price:.{sig.decimals}f} TP={sig.tp_price:.{sig.decimals}f} | "
                f"LOT={lot} (x{sig.lot_mult})"
            )

            if not c["DRY_RUN"]:
                margin_ok, margin_msg = check_margin_available(
                    self.api, self.account_id, sig.oanda, lot, sig.entry_price,
                )
                if not margin_ok:
                    self.log.warning(f"SKIP {sig.pair}: {margin_msg}")
                    self._log_signal(sig, "SKIP_MARGIN")
                    continue
                self.log.info(margin_msg)

            try:
                result = open_oanda_order(
                    self.api,
                    self.account_id,
                    sig.oanda,
                    sig.direction,
                    lot,
                    sl_price=sig.sl_price,
                    tp_price=sig.tp_price,
                    client_id=sig.oanda,
                    dry_run=c["DRY_RUN"],
                )
                if result.get("ok"):
                    executed_in_this_run.add(sig.oanda)
                    executed_count += 1
                    self.log.info(f"ORDER OPENED: {sig.pair} {sig.direction}")
                    self._log_signal(sig, "EXECUTED")
                    trade_id = result.get("trade_id") or f"DRY_RUN_{sig.oanda}"
                    append_to_csv(c["TRADE_LOG_PATH"], {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trade_id": trade_id,
                        "profile": c["PROFILE_NAME"],
                        "account": c["ACCOUNT_NAME"],
                        "pair": sig.oanda,
                        "direction": sig.direction,
                        "entry_price": round(sig.entry_price, sig.decimals),
                        "sl_price": round(sig.sl_price, sig.decimals),
                        "tp_price": round(sig.tp_price, sig.decimals),
                        "score_final": sig.score_final,
                        "score_s": sig.score_s,
                        "score_r": sig.score_r,
                        "score_a": sig.score_a,
                        "score_x": sig.score_x,
                        "score_m": sig.score_m,
                        "pips": "",
                        "profit_usd": "",
                        "exit_reason": "",
                        "exit_time": "",
                    })
                else:
                    self.log.error(
                        f"ORDER FAILED: {sig.pair} — {result.get('error', 'Unknown')}"
                    )
                    self._log_signal(sig, "ORDER_FAILED")
            except Exception as e:
                self.log.error(f"EXCEPTION opening {sig.pair}: {e}")
                self._log_signal(sig, "ORDER_EXCEPTION")

        # ── Finish ──
        self.log.info(
            f"Summary: candidates={len(candidates)} | executed={executed_count}"
        )
        self.log.info(
            f"{c['PROFILE_LABEL']} RUN COMPLETE (v{VERSION} Engine + {self.strategy.name})"
        )


if __name__ == "__main__":
    try:
        args = parse_args()
        c = build_config(args)
        Engine(c).run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}", exc_info=True)
        with contextlib.suppress(Exception):
            send_telegram_message(f"FX BOT v{VERSION} FATAL ERROR:\n{str(e)}")
