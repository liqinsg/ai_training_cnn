# 【LLM 交叉审核】问题 #4：Pandas 索引越界 `single positional indexer is out-of-bounds` 修复方案

> **审核目标**：请其他老牌 LLM（如 GPT-4o、Claude 3.5 Sonnet、Gemini 1.5 Pro 等）独立评估本项目对该问题的根因分析、现有修复方案（`data_guard.py`）的正确性、完整性与风险，并指出遗漏。
>
> **本文件为「审核上下文包」，包含全部相关代码片段、日志证据与统计数据，审核者无需（也不应）假设任何未列出的信息。**

---

## 0. 审核者工作清单（请逐条回复）

在看完后文后，请针对以下 **7 个问题** 给出明确结论：

| # | 审核问题 | 期望回答格式 |
|---|----------|-------------|
| Q1 | 根因分析是否正确、完整、无遗漏？ | ✅ 正确 / ⚠️ 部分正确（补充…） / ❌ 错误（指出…） |
| Q2 | `data_guard.py` 的 API 设计是否「够用且不过度」？特别关注 `safe_iloc` 返回 `default` 而不是「夹到最近下标」—— 这个决策是否比静默取 `iloc[-1]` 更安全？ | 逐条点评 API：`safe_last / safe_iloc / safe_tail / safe_last_row / get_safe_series / has_min_bars` |
| Q3 | **接入覆盖率不足风险**：项目 128 处 `.iloc[` 调用，仅 6 个文件 `import data_guard`。是否存在「保护了 80% 路径但崩溃从剩下 20% 路径爆出」的情况？列出你认为最危险的未保护点。 | 高危文件清单 + 理由 |
| Q4 | `indicator_provider.py` L127 `latest = df.iloc[-1]` 前面的 `has_min_bars(df, 200)` 是否真正构成保护？如果 `200 <= len(df) < 201` 但 df 中间全是 NaN 怎么办？ | 保护是否坚实 / 给出改进建议 |
| Q5 | `calculate_ema_slope` 的测试（test_data_guard.py L242-255）断言「空序列返回 (None, None)」，但原日志（bot.log L115-129）里真正的崩溃点是 **「数据并非空，只是构建后某些行缺失导致取某列 iloc 失败」**。测试是否覆盖了真实崩溃模式？ | 测试充分性评价 + 缺失用例 |
| Q6 | 设计上的「静默失败风险」：所有 safe_* 在失败时只打 WARNING 并返回 None/默认值，上层若忘记检查 None 会产生 `None + float → TypeError` 或更隐蔽的 `None in dict -> N/A`（如 Prob=0.0% 问题 #5）。是否需要更「吵」的失败模式？ | 失败传播策略评审 |
| Q7 | 给出 **最终的 go/no-go 建议**：当前 `data_guard.py` 方案（v1.0）是否可以作为 P0 修复合入？如果不能，列出最小阻塞项（≤3项）。 | 🟢 GO / 🟡 CONDITIONAL GO（阻塞项） / 🔴 NO-GO（理由） |

---

## 1. 问题描述（日志证据）

### 1.1 运行时崩溃日志（节选）

**来源文件**：[bot.log](file:///home/ubuntu/projects/ai_training_cnn/bot.log#L115-L192)

```
115→2026-08-10 19:54:46,253 [ERROR] Failed to fetch/build EURUSD=X: single positional indexer is out-of-bounds
116→2026-08-10 19:54:46,253 [INFO] performing request https://api-fxpractice.oanda.com/.../GBP_USD/candles
117→2026-08-10 19:54:46,636 [ERROR] Failed to fetch/build GBPUSD=X: single positional indexer is out-of-bounds
...（所有 8 个货币对全部失败）
164→2026-08-10 19:54:52,864 [INFO] ⏭️ EURUSD=X: insufficient bars (0)
168→2026-08-10 19:54:53,169 [INFO] ⏭️ GBPUSD=X: insufficient bars (0)
...（所有 8 个货币对 bars=0）
193→2026-08-10 19:54:54,987 [INFO] No winners selected
195→➡️ No high‑probability setups found
196→2026-08-10 19:54:55,777 [INFO] ✅ Run complete
```

**后续级联影响**（同一日志 L130-157）：
- `400 Invalid value specified for 'accountID'`（#2）
- `404 Not found` `/v3/accounts/`
- 净值查询失败 → fallback 10000
- 最终 0 信号结束整轮

### 1.2 历史同类日志：profile4

**来源**：[bot_profile4.log](file:///home/ubuntu/projects/ai_training_cnn/bot_profile4.log#L87-L111)
- 8 个交易对 × 2 种查询（trades + positions）= **每轮 16 次 ERROR + 16 次 WARNING**
- 每次运行持续 4 秒的日志洪水

---

## 2. 根因分析（RCA）

### 2.1 直接原因：裸 `.iloc[-n]` 未检查长度

全项目 `.iloc[` 调用分布统计（`grep -n "\.iloc\[" --include="*.py"`）：

| 目录 | 文件数 | `.iloc[` 次数 | 已 `import data_guard` 的文件 |
|------|--------|--------------|------------------------------|
| 根目录（业务代码） | 10 | 32 | fx_trade_bot_v683.py、strategy_decision.py、fx_trade_bot_utils.py、tests_offline_slope_threshold.py |
| utils/ | 3 | 25 | indicator_provider.py（**但只用到了 has_min_bars，未替换具体 .iloc**） |
| tests/ | 3 | 30 | test_data_guard.py |
| archives/ | 7 | 41 | —（归档文件，理论不运行） |
| **合计** | **23** | **128** | **6/23 文件 = 26%** |

### 2.2 典型崩溃路径

```python
# 典型写法（未保护）：
df = fetch_candles_from_oanda(pair)   # 周末/节假日返回 0~10 行
indicators = compute_indicators(df)   # rolling(14) 产生 13 行 NaN，再 .dropna() 后更短
latest = df.iloc[-1]                  # 💥 IndexError: single positional indexer ...
prev2  = df.iloc[-2]                  # 💥 只要 df 只有 1 行就炸
ema    = ema_series.iloc[-50]         # 💥 只要 len(ema) < 50 就炸
```

### 2.3 深层原因（触发条件）

1. **周末/节假日 OANDA 返回空或极短 candles** → df 行数 < indicator 所需 warmup
2. **API 401/400 后 error fallback 路径产生 None** → 被当成 df 继续向下走
3. **rolling/ewm 产生 NaN** → `series.dropna()` 后长度再次缩短，而后续代码假设原始长度
4. **切片静默给错值**（不抛错但更危险）：`df.iloc[-200:]` 实际只拿到 5 行，计算出的 strength / RSI / slope 全是错的

---

## 3. 现有修复方案：`data_guard.py` v1.0

> **完整文件**：[data_guard.py](file:///home/ubuntu/projects/ai_training_cnn/data_guard.py)
> **测试文件**：[test_data_guard.py](file:///home/ubuntu/projects/ai_training_cnn/tests/test_data_guard.py)（运行命令：`python -m pytest tests/test_data_guard.py -q`）

### 3.1 设计原则（写在 data_guard.py 头部）

1. **数据充足时完全不介入**：不改变返回值、变量名、业务公式
2. **数据不足时只打 WARNING 日志 + 优雅返回**（None / 默认值），绝不抛异常、不中断整轮
3. **零依赖（除 pandas）**，可被任意层级安全引用
4. **`MIN_REQUIRED_BARS` 可通过环境变量覆盖**（已在 [run.env](file:///home/ubuntu/projects/ai_training_cnn/run.env#L71-L71) 配置 `MIN_REQUIRED_BARS=200`）

### 3.2 核心 API 清单

```python
# ── 1. 统一阈值 ─────────────────────────────
MIN_REQUIRED_BARS = 200   # 可环境变量覆盖

# ── 2. 最小数据量门卫 ───────────────────────
has_min_bars(data, min_bars=None, context="") -> bool
# 例：if not has_min_bars(df, 200, pair): return None

# ── 3. 安全取列（含长度+列存在性+全NaN检查） ─
get_safe_series(df, column_name, min_bars=None, context="") -> Optional[pd.Series]
# 例：close = get_safe_series(df, "Close", 200, pair)
#      if close is None: continue

# ── 4. 安全取值（替代裸 .iloc） ─────────────
safe_last(series, default=None, context="")          # 替代 series.iloc[-1]
safe_iloc(series, offset:int, default=None, context="")  # 替代 series.iloc[-n] / [n]
safe_tail(series, n:int, context="")                 # 替代 series.iloc[-n:]（夹紧长度）
safe_last_row(df, default=None, context="")          # 替代 df.iloc[-1]

# ── 5. 数值二次兜底 ─────────────────────────
to_float(value, default=None)   # None / NaN / "abc" 都不炸
```

### 3.3 关键设计决策：`safe_iloc` 越界不「夹取最近值」

```python
# data_guard.py L172-195
def safe_iloc(series, offset: int, default=None, context: str = "") -> Any:
    # ...
    if idx < -n or idx >= n:
        needed = abs(idx) if idx < 0 else idx + 1
        insufficient_bars(needed, n, context)
        return default   # ← 返回 default，而不是 return series.iloc[0] 或 iloc[-1]
    # ...
```

**理由（写在注释里 L175-177）**：
> 越界时**不静默替换成别的数据**，直接返回 default 由上层判断处理 ——
> 否则「上一根」会被错当成「上上根」，属于静默错值（比崩溃更危险）。

**请审核 Q2 重点评价此决策**：是否应该在某些场景（比如 slope 计算只差 1 根）采用「退化策略」而不是直接返回 None？

---

## 4. 接入现状 & 覆盖率缺口

### 4.1 已接入文件（4 个业务文件 + 2 个测试）

| 文件 | 接入点 | 是否替换了全部裸 `.iloc` |
|------|--------|--------------------------|
| [fx_trade_bot_v683.py](file:///home/ubuntu/projects/ai_training_cnn/fx_trade_bot_v683.py#L110-L120) | L110-120 import；L227-228 `calculate_ema_slope` 使用 safe_iloc/safe_last；L311-313 仍有裸 `float(daily_closes.iloc[-1])` | ⚠️ 部分（L227 已换，L311 未换） |
| [strategy_decision.py](file:///home/ubuntu/projects/ai_training_cnn/strategy_decision.py#L115-L119) | L116 `has_min_bars(df, 5)` 门卫 + L119 `df.iloc[-1]` | ⚠️ 有门卫但没换 `safe_last_row` |
| [fx_trade_bot_utils.py](file:///home/ubuntu/projects/ai_training_cnn/fx_trade_bot_utils.py) | import `get_safe_series, safe_last` | 未知（grep 未显示具体行） |
| [indicator_provider.py](file:///home/ubuntu/projects/ai_training_cnn/utils/indicator_provider.py#L117-L149) | L119 `has_min_bars(df, 200)` 门卫 + L127-148 大量裸 `.iloc[-1]`、`.iloc[-2]` | ❌ 有门卫但无具体 safe_* 替换 |

### 4.2 **未接入但存在高危 `.iloc` 的文件**（审核 Q3 重点）

| 文件 | 行号 | 危险调用 | 风险等级 |
|------|------|----------|---------|
| [signal_generator.py](file:///home/ubuntu/projects/ai_training_cnn/signal_generator.py) | 89 | `latest = df.iloc[-1]` | 🔴 高（无前置长度检查） |
| [signal_generator_v1.py](file:///home/ubuntu/projects/ai_training_cnn/signal_generator_v1.py) | 77 | `latest = df.iloc[-1]` | 🔴 高 |
| [fx_monte_carlo_advanced.py](file:///home/ubuntu/projects/ai_training_cnn/fx_monte_carlo_advanced.py) | 46 | `last_price = float(close.iloc[-1])` | 🔴 高 |
| [montecarlo_fx.py](file:///home/ubuntu/projects/ai_training_cnn/montecarlo_fx.py) | 57 | `S0 = float(closes.iloc[-1].item())` | 🔴 高（还 `.item()`，空时 AttributeError） |
| [fx_daily_view.py](file:///home/ubuntu/projects/ai_training_cnn/fx_daily_view.py) | 59 | `last_price = close.iloc[-1]` | 🟡 中（离线工具，但也会炸） |
| [yhfin.py](file:///home/ubuntu/projects/ai_training_cnn/yhfin.py) | 57 | `S0 = float(closes.iloc[-1])` | 🟡 中 |
| [fx_model_xgb.py](file:///home/ubuntu/projects/ai_training_cnn/fx_model_xgb.py) | 128 | `latest = X.iloc[-1:]` | 🟡 中（切片不抛错，但可能给错长度） |
| [utils/ml_confirmation.py](file:///home/ubuntu/projects/ai_training_cnn/utils/ml_confirmation.py) | 397-399 | `gross_equity.iloc[-1]`、`price.iloc[-1]`、`price.iloc[0]` | 🟡 中（回测工具，但也会中断） |
| [utils/yahoo_finance.py](file:///home/ubuntu/projects/ai_training_cnn/utils/yahoo_finance.py) | 116 | `data["Close"].iloc[-1]` | 🟡 中 |

---

## 5. 测试覆盖（已有测试用例 vs 真实崩溃模式）

### 5.1 已有测试（17 个用例）

**来源**：[test_data_guard.py](file:///home/ubuntu/projects/ai_training_cnn/tests/test_data_guard.py)

| 分组 | 用例数 | 覆盖场景 |
|------|--------|---------|
| 常量 & env | 3 | MIN_REQUIRED_BARS 默认值 200、env 解析、非法值兜底 |
| 日志格式 | 2 | 标准「数据不足：需要 N 根…」格式输出 |
| get_safe_series | 7 | None / 太短 / 缺列 / 全 NaN / 正常 / min_bars 覆盖 / MultiIndex 列 |
| safe_* 取值 | 9 | 空序列 / 正常 / 超长 lookback / 越界正索引 / safe_tail 夹紧 / 空 DataFrame / 单例 iloc[-2] |
| to_float | 1 | None / NaN / 字符串 / 整数 全不炸 |
| 业务 AST 接入 | 2 | `calculate_ema_slope` 空/短序列；`evaluate_trend_and_tp` 不足 16 根 |
| 接入点断言 | 1 | `fx_trade_bot_v683.py` 必须含 `from data_guard import` 字符串 |

### 5.2 **测试缺口（审核 Q5 重点）**

与真实崩溃日志对比，已有测试 **没有覆盖** 以下场景：

1. **`get_safe_series` 返回列后，列本身 `.dropna()` 再 `.iloc[-n]` 失败** —— 真实崩溃就是这条路：fetch 成功（>200 行）→ rolling 产生 NaN → `indicator.dropna()` 后长度 < 所需 → 仍炸
2. **列存在但整列全是 NaN 以外的半 NaN**：如前 180 行 NaN、后 20 行有效值 → `len(series)=200` 但 `dropna().len=20`
3. **MultiIndex 列 + yfinance 返回 DataFrame（而非 Series）** 这种 corner 已覆盖，但 `iloc[:, 0]` 再次 `.iloc[-1]` 的组合未测
4. **`safe_iloc` 正索引越界** 已测，但**负索引刚好等于长度**（`len=5, idx=-5`）是否走正确分支未测
5. **data_guard 自身 import 失败**：pandas 未安装？（低概率但可加 smoke test）

---

## 6. 与其他问题的耦合关联

> **提醒审核者**：问题 #4 不是孤岛，修复时需注意对其他问题的影响

| 关联问题 | 耦合点 | 风险 |
|----------|--------|------|
| **#5 Prob=0.0%** | safe_* 返回 None → 上层 `raw_prob = None if last_pred is None else last_pred[1]` → `to_float(None) → 0.0` | 修复 #4 若只返回 None 而不改进传播链路，Prob=0.0% 会更频繁出现 |
| **#7 保证金不足** | 如果 `equity = safe_last(equity_series)` 返回 None，而 `to_float(None) = 0` → 可用保证金被算成 0 → 所有单子被拒 | 需要确认 fallback 是否为「上次有效值」而非 0 |
| **#6 EMA100 过滤器 Bug** | 如果 `weekly_ema = safe_iloc(ema100, -100)` 返回 None → 上层比较逻辑产生 `1.23456 > None` → TypeError（或被更上层吞掉变成 False） | 必须有 None-aware 的比较分支 |
| **#2 AccountID 空** | AccountID 问题（完全独立模块）和 #4 可分别修复，无耦合 | 无（但两者同时出现时日志洪水会叠加） |

---

## 7. 最小迁移路径（推荐做法）

> **本方案并非一蹴而就替换全部 128 处**，而是 3 阶段渐进：

```
阶段 1（P0 = 本周）：守卫生效（目前已部分完成）
    ├── 所有对 df/series 取值前，先 has_min_bars / get_safe_series 判断
    ├── 高危 8 个文件补上 safe_* 调用替换
    └── 运行 test_data_guard.py 全部通过

阶段 2（P1 = 下周）：全面替换 .iloc
    ├── scripts/check_iloc_unprotected.py（写一个 AST 扫描，标记未走 safe_* 的 .iloc）
    ├── archives/ 之外的业务代码 57 处 .iloc 全部替换
    └── 加一条 CI：新增 .iloc 必须 review 是否可走 safe_*

阶段 3（P2 = 迭代）：None 传播 & 审计
    ├── 对每个返回 None 的路径：上层 is None 检查 & 打标准 AUDIT 日志
    ├── 统计「数据不足跳过」的比率（按 pair / 时间 / 货币对聚合）
    └── 反推 MIN_REQUIRED_BARS 是否需要调低（如从 200 → 120，保证信号产出率 ≥ 80%）
```

---

## 8. 附录：快速参考（审核者无需跳转文件）

### 8.1 真实崩溃的最小复现

由 `test_data_guard.py` L197-210 复现：

```python
# 复现 #1：空 DataFrame 直接 .iloc[-1]
empty = pd.DataFrame({"Close": []})
empty.iloc[-1]   # → IndexError: single positional indexer is out-of-bounds

# 复现 #2：只有 1 行 .iloc[-2]
one = pd.Series([1.0])
one.iloc[-2]     # → IndexError（对应 previous_high / previous_low）

# 复现 #3：rolling(14) 后长度缩短
df_short = pd.DataFrame({"Close": np.arange(10.0)})  # len=10
atr = df_short["Close"].rolling(14, min_periods=14).mean()
atr.iloc[-1]    # → 不抛错，但得到 NaN（静默错值 #1）
atr.dropna().iloc[-1]   # → IndexError（真实崩溃路径）
```

### 8.2 data_guard 的保护后效果（同一用例）

```python
safe_last_row(empty, None)       # → None（不崩，打 WARNING）
safe_iloc(one, -2, "DEF")        # → "DEF"（不崩，打 WARNING：需 2/实 1）
get_safe_series(df_short, "Close", min_bars=14)   # → None（提前挡住 rolling(14) 后为空的情况）
```

---

**END OF AUDIT PACKAGE — 请从第 0 节 Q1~Q7 开始回复审核意见。**
