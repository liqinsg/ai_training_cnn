# market_regime_detector.py — 完整可运行版
import numpy as np

# ─── 可配置参数 ────────────────────────────────────────────────
TREND_THRESHOLD = 0.0015   # 斜率判定阈值（按你的标的调整）
VOLATILITY_PERIOD = 14     # ATR 周期
RSI_PERIOD = 14            # RSI 周期
LOOKBACK = 20               # 回看 K 线数量

# ─── 内部计算函数 ──────────────────────────────────────────────
def calculate_trend_slope(candles):
    """计算最近 N 根 K 线收盘价线性回归斜率"""
    closes = np.array([c['close'] for c in candles[-LOOKBACK:]])
    if len(closes) < LOOKBACK:
        return 0.0
    x = np.arange(LOOKBACK)
    slope, _ = np.polyfit(x, closes, 1)
    # 归一化斜率 ≈ 相对变化/根
    return slope / np.mean(closes) if np.mean(closes) != 0 else 0.0


def calculate_atr_ratio(candles):
    """计算当前 ATR / 近期均值 → 波动率相对水平"""
    if len(candles) < VOLATILITY_PERIOD + 1:
        return 1.0
    highs = np.array([c['high'] for c in candles])
    lows = np.array([c['low'] for c in candles])
    prev_close = np.array([c['close'] for c in candles[:-1]])
    tr = np.maximum(highs[1:] - lows[1:],
                    np.maximum(np.abs(highs[1:] - prev_close),
                               np.abs(lows[1:] - prev_close)))
    atr_current = np.mean(tr[-VOLATILITY_PERIOD:])
    atr_prev = np.mean(tr[-VOLATILITY_PERIOD*2:-VOLATILITY_PERIOD]) if len(tr) >= VOLATILITY_PERIOD*2 else atr_current
    return atr_current / atr_prev if atr_prev != 0 else 1.0


def calculate_rsi(candles):
    """标准 RSI 计算"""
    if len(candles) < RSI_PERIOD + 1:
        return 50.0
    closes = np.array([c['close'] for c in candles])
    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.mean(gain[-RSI_PERIOD:])
    avg_loss = np.mean(loss[-RSI_PERIOD:])
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ─── 核心判定 ──────────────────────────────────────────────────
def detect_market_regime(candles):
    """根据最近 K 线判定当前行情类型
    返回: STRONG_TREND / RANGING / LOW_VOLATILITY / UNCERTAIN
    """
    slope = calculate_trend_slope(candles)
    volatility = calculate_atr_ratio(candles)
    rsi = calculate_rsi(candles)

    if abs(slope) > TREND_THRESHOLD and volatility > 1.2:
        return "STRONG_TREND"      # 📈 强趋势
    elif 0.8 < volatility < 1.2 and 40 < rsi < 60:
        return "RANGING"           # ⚖️ 温和震荡
    elif volatility < 0.7:
        return "LOW_VOLATILITY"    # 🧊 窄幅整理
    else:
        return "UNCERTAIN"         # ⚡ 不确定/高波动


def get_dynamic_weights(regime):
    """根据行情动态分配 4 Profile 权重"""
    weights = {
        "STRONG_TREND":   {"PF-A": 0.70, "PF-D": 0.20, "PF-B": 0.08, "PF-C": 0.02},
        "RANGING":        {"PF-D": 0.60, "PF-A": 0.25, "PF-B": 0.10, "PF-C": 0.05},
        "LOW_VOLATILITY": {"PF-C": 0.55, "PF-D": 0.25, "PF-B": 0.15, "PF-A": 0.05},
        "UNCERTAIN":      {"PF-B": 0.50, "PF-C": 0.25, "PF-D": 0.20, "PF-A": 0.05},
    }
    return weights.get(regime, weights["UNCERTAIN"])


def consensus_decision(signals, regime):
    """
    signals = {
        "PF-A": {"pass": True, "score": 0.32},
        "PF-D": {"pass": True, "score": 0.28},
        "PF-B": {"pass": False, "score": 0.15},
        "PF-C": {"pass": False, "score": 0.10},
    }
    返回: BUY / WATCH / SKIP
    """
    match regime:
        case "STRONG_TREND":
            if signals["PF-A"]["pass"]:
                return "BUY" if signals["PF-D"]["pass"] else "WATCH"

        case "RANGING":
            if signals["PF-D"]["pass"] and not signals["PF-A"]["pass"]:
                return "BUY"

        case "LOW_VOLATILITY":
            if signals["PF-C"]["pass"]:
                return "BUY"

        case "UNCERTAIN":
            if signals["PF-B"]["pass"] and signals["PF-C"]["pass"]:
                return "BUY"

    return "SKIP"


# ─── 诊断输出 ──────────────────────────────────────────────────
def get_regime_summary(candles):
    """返回详细诊断，用于日志/调试"""
    return {
        "regime": detect_market_regime(candles),
        "slope": round(calculate_trend_slope(candles), 6),
        "volatility_ratio": round(calculate_atr_ratio(candles), 2),
        "rsi": round(calculate_rsi(candles), 1),
        "weights": get_dynamic_weights(detect_market_regime(candles)),
    }


# ─── 独立测试 ──────────────────────────────────────────────────
if __name__ == "__main__":
    print("✅ Market Regime Detector — Loaded OK")
    print("-" * 50)
    print("TREND_THRESHOLD:", TREND_THRESHOLD)
    print("LOOKBACK:", LOOKBACK)
    print("Available functions:")
    print("  detect_market_regime(candles)")
    print("  get_dynamic_weights(regime)")
    print("  consensus_decision(signals, regime)")
    print("  get_regime_summary(candles)")