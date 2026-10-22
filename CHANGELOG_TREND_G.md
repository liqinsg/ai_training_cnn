
# 🚀 趋势因子 G — 上线执行 + 验证闭环 + 迭代计划

## 一、最终版配置文件（直接替换）

这是**4套Profile全部补全G、D_GATE全开、权重归一化=1.0**的完整JSON，直接覆盖即可：

```json
{
  "version": "6.8.5-G",
  "meta": {
    "note": "Trend-G integrated: 4 profiles with G factor | D_GATE all enabled | py_compile passed",
    "source": "config_profile.json + config_bot.py + fx_trade_bot_v685_2.py",
    "updated": "2026-10-22"
  },
  "global": {
    "feature_settings": {
      "USE_ATR": true,
      "ATR_SL_MULT": 2.0,
      "ATR_TP_MULT": 3.0,
      "ATR_PERIOD": 14,
      "USE_MACD": true,
      "USE_RSI": true,
      "USE_ADX": true,
      "PREFER_YAHOO_DATA": true
    },
    "ml_settings": {
      "MODEL_TYPE": "xgboost",
      "TARGET_HORIZON": 6,
      "TRAIN_LOOKBACK_BARS": 1500,
      "XGB_BULLISH_THRESHOLD": 0.55
    },
    "timeframe": {
      "MODE": "LEVEL10",
      "YF_INTERVAL": "4h",
      "YF_PERIOD_FULL": "30d",
      "YF_PERIOD_RESAMPLE": "60d",
      "YF_INTERVAL_D": "1d",
      "YF_PERIOD_FULL_D": "120d",
      "YF_PERIOD_RESAMPLE_D": "180d",
      "PERIODS_YEAR_D": 252
    },
    "monte_carlo": {
      "MC_REPORT_TITLE": "FX H4 MONTE CARLO",
      "MC_REPORT_TITLE_D": "FX DAILY MONTE CARLO",
      "MC_MAX_AGE_HOURS": 24,
      "MC_SIMULATIONS": 5000,
      "MC_CONFIDENCE": 0.90,
      "SKIP_MC": false,
      "H4_LOOKBACK": 90,
      "H4_FORECAST": 8,
      "DAILY_LOOKBACK": 90,
      "DAILY_FORECAST": 5,
      "MC_BAND_PCT": 90,
      "MC_SIGNIFICANT_PCT": 60,
      "MC_MOMENTUM_BAND": 0.001
    },
    "risk_trade": {
      "DEFAULT_LOT_SIZE": 10000,
      "SL_MIN_PIPS": 25,
      "SL_MIN_PIPS_JPY": 35,
      "SL_BUFFER_PIPS": 25,
      "SL_MIN_DISTANCE_PIPS": 20,
      "SL_FALLBACK_FIXED_PIPS": 35,
      "SL_USE_ZONE_HIERARCHY": true,
      "SL_H4_LOOKBACK_BARS": 6,
      "SL_H8_LOOKBACK_BARS": 4,
      "SL_DAILY_LOOKBACK_BARS": 2,
      "SL_PAIR_FLOOR_OVERRIDES__NO_DGATE": {
        "GBPJPY=X": 50
      },
      "SL_PAIR_FLOOR_OVERRIDES__DGATE": {}
    },
    "tp_trailing": {
      "DYNAMIC_TP": false,
      "TRAILING_TP": false,
      "TRAILING_SL": false,
      "TP_RAISE_THRESHOLD_PIPS": 15,
      "BE_TRIGGER_ATR_MULT": 1.5,
      "TRAIL_TRIGGER_ATR_MULT": 2.5,
      "TRAIL_ATR_MULT": 1.5,
      "MAX_HOLD_BARS": 12
    },
    "confluence_filter": {
      "MULTI_TF_CONFLUENCE": false,
      "CONFLUENCE_REQUIRED_TFS": 2,
      "STRENGTH_SIGNAL_BLOCK_THRESHOLD": 0.80,
      "REQUIRE_DIRECTION_CONSENSUS": true,
      "CONSENSUS_THRESHOLD": 2,
      "ENFORCE_LONGS_SHORTS": true,
      "MIN_PER_SIDE": 1,
      "MAX_RATIO": 0.75,
      "PREFER_BALANCED": true,
      "TREND_FILTER_ENABLED": false,
      "WEEK_EMA100_FILTER_ENABLED": false,
      "RSI_DIRECTION_AWARE": true,
      "SLOPE_DIAG": false
    },
    "adx_logic": {
      "ADX_SCALE_FACTOR": 2.0,
      "ADX_FLOOR_ENABLED": true,
      "ADX_MIN_SCORE": 20.0,
      "ADX_BOOST_ENABLED": true,
      "ADX_BOOST_THRESHOLD": 30.0,
      "ADX_BOOST_VALUE": 10.0
    },
    "d_gate_base": {
      "D_GATE_BUFFER_PCT": 0.15,
      "D_GATE_SHADOW": false,
      "D_GATE_CONFIRM": "2H1",
      "D_GATE_EMA_FAST": 20,
      "D_GATE_EMA_SLOW": 50
    },
    "ranking_cooldown": {
      "REMOVE_COOLDOWN": false,
      "DEBUG_MODE": false,
      "USE_TOP_PAIRS_ONLY": false,
      "TOP_PAIRS_COUNT": 5,
      "TOP_PAIRS_MIN_GAP": 1.5,
      "MIN_CONVICTION_SCORE_FALLBACK": 30.0,
      "MIN_CONVICTION_SCORE_ALT": 45.0,
      "COOLDOWN_HOURS_AFTER_TP": 2.0
    },
    "validation": {
      "CONFIG_VALIDATION_ENABLED": true,
      "CONFIG_TOLERANCE": 0.005
    }
  },
  "profile_defaults": {
    "MIN_GAP": 0.25,
    "D_GATE_BUFFER_PCT": 0.15,
    "D_GATE_CONFIRM": "2H1",
    "MAX_ENTRIES_THIS_RUN": 3,
    "TRAIL_ATR_MULT": 2.0,
    "MAX_HOLD_BARS": 48,
    "USE_TOP_PAIRS_ONLY": true
  },
  "profiles": {
    "1": {
      "NAME": "PF-A Trend-Focused + G",
      "WEIGHTS": {
        "S": 0.55,
        "R": 0.10,
        "G": 0.10,
        "A": 0.05,
        "X": 0.12,
        "M": 0.08
      },
      "TREND_G_ENABLED": true,
      "TREND_G_ADX_MODULATION": false,
      "SKIP_MC": false,
      "MIN_CONVICTION": 50.0,
      "MIN_GAP": 0.25,
      "MIN_SLOPE": 0.0010,
      "D_GATE_ENABLED": true,
      "MAX_OPEN": 3,
      "TOP_N": 3,
      "ACCOUNT_SUFFIX": "001",
      "account_id_demo": "101-003-39389016-001",
      "account_id_live": "001-003-21515688-001"
    },
    "2": {
      "NAME": "PF-B Balanced + G",
      "WEIGHTS": {
        "S": 0.45,
        "R": 0.15,
        "G": 0.10,
        "A": 0.10,
        "X": 0.12,
        "M": 0.08
      },
      "TREND_G_ENABLED": true,
      "TREND_G_ADX_MODULATION": true,
      "SKIP_MC": false,
      "MIN_CONVICTION": 45.0,
      "MIN_GAP": 0.25,
      "MIN_SLOPE": 0.0007,
      "D_GATE_ENABLED": true,
      "MAX_OPEN": 3,
      "TOP_N": 3,
      "ACCOUNT_SUFFIX": "002",
      "account_id_demo": "101-003-39389016-002",
      "account_id_live": "001-003-21515688-002",
      "TRAILING_TP": false
    },
    "3": {
      "NAME": "PF-C Conservative + G",
      "WEIGHTS": {
        "S": 0.35,
        "R": 0.20,
        "G": 0.08,
        "A": 0.17,
        "X": 0.12,
        "M": 0.08
      },
      "TREND_G_ENABLED": true,
      "TREND_G_ADX_MODULATION": true,
      "SKIP_MC": false,
      "MIN_CONVICTION": 55.0,
      "MIN_GAP": 0.25,
      "MIN_SLOPE": 0.0003,
      "D_GATE_ENABLED": true,
      "D_GATE_BUFFER_PCT": 0.15,
      "D_GATE_CONFIRM": "2H1",
      "MAX_OPEN": 2,
      "TOP_N": 2,
      "ACCOUNT_SUFFIX": "003",
      "account_id_demo": "101-003-39389016-003",
      "account_id_live": "001-003-21515688-003"
    },
    "4": {
      "NAME": "PF-D Structure/D-Gate + G",
      "WEIGHTS": {
        "S": 0.35,
        "R": 0.10,
        "G": 0.15,
        "A": 0.10,
        "X": 0.20,
        "M": 0.10
      },
      "TREND_G_ENABLED": true,
      "TREND_G_ADX_MODULATION": true,
      "SKIP_MC": false,
      "MIN_CONVICTION": 42.0,
      "MIN_GAP": 0.25,
      "MIN_SLOPE": 0.0003,
      "D_GATE_ENABLED": true,
      "D_GATE_BUFFER_PCT": 0.15,
      "D_GATE_CONFIRM": "2H1",
      "MAX_OPEN": 3,
      "TOP_N": 3,
      "ACCOUNT_SUFFIX": "004",
      "account_id_demo": "101-003-39389016-004",
      "account_id_live": "001-003-21515688-004",
      "TP_MULTIPLIER": 1.0
    }
  }
}
```

---

## 二、部署执行清单（复制粘贴即可）

```bash
# 1. 干净备份
cp config_profile.json config_profile.json.bak_20261022_trendG_final
cp fx_trade_bot_v685_2.py fx_trade_bot_v685_2.py.bak_20261022
cp config_bot.py config_bot.py.bak_20261022

# 2. 写入新JSON
cat > config_profile.json << 'JSONEOF'
← 上面整段JSON →
JSONEOF

# 3. 格式校验
python -c "import json; json.load(open('config_profile.json')); print('✅ JSON valid')"

# 4. 语法编译确认
python -m py_compile config_bot.py fx_trade_bot_v685_2.py && echo "✅ py_compile passed"

# 5. 权重自检（config_bot内置校验）
python -c "
from config_bot import load_config, validate_weights
cfg = load_config('config_profile.json')
ok = True
for pid, p in cfg['profiles'].items():
    w = p['WEIGHTS']
    s = sum(w.values())
    status = '✅' if abs(s-1.0) < 0.005 else '❌'
    print(f'{status} Profile {pid}: sum={s:.4f} — {p[\"NAME\"]}')
    if abs(s-1.0) >= 0.005: ok = False
print('All OK' if ok else 'ERROR: weight sum mismatch')
"

# 6. Dry-run 试运行（Profile 4）
python fx_trade_bot_v685_2.py --profile 4 --dry-run
# 预期输出：
# ✅ TREND_G_ENABLED = True, W_G = 0.15
# ✅ TREND_G_ADX_MODULATION = True
# ✅ G Score computed: XX.XX (ADX modulated: YY.YY)
# ✅ Final score = ... (G contribution shown)
```

---

## 三、G 计算代码对照确认（直接核对现有代码）

`fx_trade_bot_v685_2.py` 约 1498–1525 行：

```python
def compute_trend_g(closes, adx_value=None):
    """
    趋势因子 G — EMA排列方向 + 结构对齐 + ADX调制
    返回: score ∈ [0, 100]
    依赖全局模块级参数：D_GATE_EMA_FAST / D_GATE_EMA_SLOW
    """
    ema_fast = calculate_ema(closes, D_GATE_EMA_FAST)   # =20 ✅ 全局可见
    ema_slow = calculate_ema(closes, D_GATE_EMA_SLOW)   # =50 ✅ 全局可见

    # 方向与强度
    diff = (ema_fast[-1] - ema_slow[-1]) / ema_slow[-1]

    # 对齐判定：在调用方结合信号方向 is_buy/is_sell
    raw_score = float(np.clip(abs(diff) * 500, 0, 100))

    # 背离惩罚（调用方应用）
    # if aligned: G = raw_score else: G = raw_score * 0.2

    # ADX 置信调制
    if TREND_G_ADX_MODULATION and adx_value is not None:
        conf = float(np.clip(adx_value / 50.0, 0.2, 1.0))
        raw_score *= conf

    return raw_score
```

**调用点（约 2265–2278 行）**：

```python
# --- G Factor ---
if TREND_G_ENABLED and W_G > 0:
    g_raw = compute_trend_g(df.Close, adx_value=current_adx)
    # 方向对齐检查
    ema_diff = ema_fast[-1] - ema_slow[-1]
    aligned = (ema_diff > 0 and direction == "BUY") or \
              (ema_diff < 0 and direction == "SELL")
    G = g_raw if aligned else g_raw * 0.2
    contrib_G = G * W_G
    log_parts.append(f"G={G:.2f}(w={W_G:.2f}, +{contrib_G:.2f})")
else:
    G = 0.0
    contrib_G = 0.0

# Final weighted score
final = (S*W_S + R*W_R + G*W_G + A*W_A + X*W_X + M*W_M)
```

---

## 四、回测 & 观测方案

### 基线对照

| 版本               | 说明                                                |
| ------------------ | --------------------------------------------------- |
| Baseline（v6.8.4） | Profile4: S=0.45,R=0.10,A=0.15,X=0.20,M=0.10 / G=0  |
| New（v6.8.5-G）    | Profile4: S=0.35,R=0.10,G=0.15,A=0.10,X=0.20,M=0.10 |

### 核心观测指标

- **G 贡献占比** = `(contrib_G / final_score)` 均值 & 分位数
- **ADX 分区表现**：ADX>30（强趋势）vs ADX<20（震荡）分别统计胜率/盈亏比
- **背离过滤效果**：被打 20% 折扣的信号 vs 正常信号 的盈亏对比
- **整体绩效**：Sharpe、MaxDD、Win Rate、Profit Factor、Avg Trade

### 动态权重进阶（下一迭代方向）

```python
# 伪代码：按ADX门限动态分配权重
if ADX > 30:    # 强趋势 → 提G降RSI
    W_G, W_R, W_S = 0.20, 0.05, 0.30
elif ADX < 20:  # 震荡 → 提RSI降G
    W_G, W_R, W_S = 0.05, 0.15, 0.35
else:           # 混合 → 默认值
    W_G, W_R, W_S = 0.15, 0.10, 0.35
```

---

## 五、交付确认清单 ✅

- [X] JSON 4 Profile 全部补G / D_GATE 全开 / sum=1.0
- [X] `config_bot.py` 读取+归一化+自检
- [X] 主程序启动加载 + 互锁保护
- [X] G 计算函数（复用 D_GATE EMA 周期，ADX 调制）
- [X] 方向对齐/背离惩罚逻辑
- [X] 日志明细输出
- [X] `py_compile` 通过
- [X] 变量作用域确认（D_GATE_EMA_* 全局可见）
- [X] 向后兼容：旧配置自动退化为5因子

---

**现在直接执行「部署执行清单」即可上线运行 Profile 1–4。建议先用 Profile 4 跑模拟盘 7–14 天对比基线，确认 G 贡献正向后逐步扩至其他 Profile。**
