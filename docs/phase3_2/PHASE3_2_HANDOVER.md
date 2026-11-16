# Phase 3.2 — 交班文档（Handover）

**Date:** 2026-11-15
**For:** 明天的下一个 session（接手人）
**Repo:** `/home/ubuntu/projects/ai_training_cnn`
**Branch / HEAD:** `v2026c` / `152cfcc`（`phase3.2`），工作树 clean
**上一 session 的授权范围:** L1 + L2-A + L2-B + L3（owner 已「全部授权」）

> 本文档只做「状态交接 + 明日任务书」，不引入新的技术决策，不替代 01–05 决策记录。

---

## 0. 30 秒版

Phase 3.2 已推进到 **Step5（L2-B）完成 + L3 实现接线完成**，但 **Step6（Candidate Freeze）与 Step7（交接）未完成**。
唯一硬门槛是 **P1/P2 train-inference parity 尚未运行**（Doc 05 prerequisite 8）。
**明天的任务顺序：先完成任务 1（P1/P2 parity），再完成任务 b（DEFER 候选正式裁决）。**

---

## 1. 原始目标与治理模型（不要跑偏）

- 目标：建立一套**新的、可复现、可验证的 Feature Contract**；**不是**修复旧模型兼容性。
- 原则（owner 原话）：**旧模型的历史包袱可以正式结束，但证据链和状态记录不能被抹掉。**
- 治理层级：`L1 流程` → `L2-A (Step1–3 输入/日历/特征/实验协议)` → `L2-B (Step5 证据后运行配置)` → `L3 (Step8–9 实现接线)`。
- 执行链：`Step0 → Step0.1 → Step1(IC) → Step2(FD) → Step3(实验授权) → Step4(离线实验) → Step5(RC) → Step6(冻结) → Step7(交接)`。
- 记录方式：**只追加新状态，不改旧文**；不把未批准值写成已生效。

参考：[PHASE3_2_REVISION_PLAN.md](PHASE3_2_REVISION_PLAN.md)（v0.3 + §14.1 授权台账）。

---

## 2. 已完成（含冻结值速查）

### 2.1 治理与决策
| 文档 | 状态 |
|---|---|
| [01_INPUT_CONTRACT_OWNER_DECISION.md](01_INPUT_CONTRACT_OWNER_DECISION.md) | IC-01..08 全部 APPROVED |
| [02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md](02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md) | FD-01..09 APPROVED（含 §3.1 ECDF 并列敏感定性） |
| [03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md](03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md) | L2-A 实验授权 APPROVED |
| [04_RUNTIME_CONFIGURATION_DECISIONS.md](04_RUNTIME_CONFIGURATION_DECISIONS.md) | RC-01..11 APPROVED |
| [05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md](05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md) | **TEMPLATE — NOT FROZEN**（未完成） |
| [PHASE3_2_CALENDAR_CONTRACT.md](PHASE3_2_CALENDAR_CONTRACT.md) | v0.2，OANDA 证据已落定 |

### 2.2 冻结取值（接手前先记住）
- **Timeframe:** M15。
- **Timestamp（IC-02 / RC-03）:** **candle-OPEN（start）**；来源 OANDA REST-V20 Instrument Definitions（`time` = "The start time of the candlestick"）。
- **Incomplete candle（IC-04）:** 排除最新未完成 candle；权威信号 = OANDA `complete` 字段。（现代码用的是时间流逝启发式 → 已记录为 deviation。）
- **IC-06:** 整批拒绝（whole-batch rejection），不做部分填充。
- **ATR / RSI / ADX:** Wilder，`n=14`；ADX seed 规则见 Doc 02 §3（seed@t=n、首个 ADX seed@t=2n−1、break→保留 TR/+DM/−DM→reseed）。
- **MACD:** EMA，`12/26/9`，`adjust=False`，首值 seed。
- **RSI slope:** `rsi_slope_45m = RSI[t] - RSI[t-3]`。
- **ECDF:** `atr_ecdf_50bar` = 尾部 50 个有效 ATR 的**inclusive-rank**（`<=`）；并列敏感定性为 R 类固有行为（Doc 02 §3.1）。
- **vol 缩放:** `sqrt(p)`（语义已变更）；命名 `horizon_vol_3h/6h/12h` ↔ window 12/24/48。
- **FD-07:** Volume 两特征 **EXCLUDE**（`vol_sma_ratio` / `vol_trend` 的 volume 语义不可靠）。
- **RC-02:** **production history length = 800 bars**（L2-B，证据 = Step4 收敛报告）。
- **RC-11:** 钉 `tzdata==2026.5` + `pytz==2026.1`；FAIL CLOSED。
- **Calendar:** 周开 周日 17:05 NY / 周收 周五 16:59 NY；16:59–17:05 有 6 分钟日中断（DOCUMENTED NOT VERIFIED）；TRY/NZD 差异存在但覆盖 UNRESOLVED；gap classifier 目前**只批准周末 gap**，其余 fail closed。
- **候选分布:** 37 = 4 `ACCEPTABLE AS-IS` + 19 `REDEFINE` + 14 `DEFER` + 0 `EXCLUDE`。

### 2.3 实现与实验
| 产物 | 说明 |
|---|---|
| [`ml/feature_contract.py`](../../ml/feature_contract.py) | 新契约**唯一实现**（33 列 `ORDERED_FEATURES`，冻结参数 `ATR_N=14, RSI_N=14, ADX_N=14, MACD 12/26/9, ECDF_WINDOW=50, ATR_SMA_N=14, ATR_RATIO_N=28`；`validate_candles` 整批拒绝；无赋值型 fallback） |
| [`tests/test_feature_contract.py`](../../tests/test_feature_contract.py) | 单测 + 源码级接线测试 |
| [`experiments/phase3_2_feature_convergence/`](../../experiments/phase3_2_feature_convergence/) | Step4 收敛实验：`convergence_experiment.py` / `proposed_contract.py` / `REPORT.md` |
| [`fx_trade_bot.py`](../../fx_trade_bot.py) / [`fx_trade_bot_v685.py`](../../fx_trade_bot_v685.py) | L3 可回退接线：`USE_FEATURE_CONTRACT_V2 = _opt("USE_FEATURE_CONTRACT_V2", False)` + `_build_pair_features()`；4 处 `feat_engine.build(...)` 已统一改走 helper |

**Step4 结果:** 主验收 `300v500`、`500v800` 对所有 fixture/特征 **全 PASS**；`adx_break` fixture 上 `atr_ecdf_50bar` 诊断对（200v300 等）Δ=0.92，已定性为 R 类并列敏感（不影响冻结配置）。

**L3 接线语义:** 默认 OFF → 生产路径逐字节不变；ON → 走契约，且因列名/顺序不同，必须配 matching artifact，否则下游矩阵构建 **fail closed**（不静默错列）。

---

## 3. 未完成 / 阻塞

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | **P1/P2 train-inference parity** | **NOT RUN** | Doc 05 prerequisite 8，**唯一卡住冻结的硬门槛** |
| 2 | P3–P5（scaler/张量/预测输出 parity） | NOT VERIFIED | active model/scaler bundle 不可用；**不得**标 pass/waived/`NOT REQUIRED` |
| 3 | Doc 05 冻结字段 | 全空 | 候选清单 / 有序 schema / `Feature Contract Identity` / 证据包 hash / owner 签署 = `NOT FROZEN` / `NOT ISSUED` |
| 4 | 14 项 DEFER 候选 | BLOCKED | 见 §4 任务 b |
| 5 | Step7 交接 + Phase 3.3 | 未开始 | 预测价值评估 |
| — | `FULL_PARITY_STATUS` | `NOT VERIFIED` | 见 Revision Plan §238–248 |

**已记录风险（需注意）:** `05` 登记表内部有**不一致**：`atr_percentile` 的 matrix disposition = `REDEFINE`，但 final status = `DEFER`。此外 Doc 05 登记表把 `atr*`/`rsi*`/`macd*` 标为 `DEFER: BLOCKED`，而 Doc 02 FD-03..06 **已批准** ATR/RSI/ADX/MACD 的定义——原因是旧 backend（pandas_ta vs manual fallback）歧义；**新契约是单一 backend，已消除该歧义**。任务 b 需据此重新裁决。

---

## 4. 明天的任务（严格按序）

### 任务 1（先做）— P1/P2 parity（预登记 + 可执行 harness）

**目标:** 在新契约下证明「训练路径」与「推理路径」对**相同原始 OHLCV** 产生**相同校验结果**与**相同原始特征向量**，以满足 Doc 05 prerequisite 8。

**定义（源自 Revision Plan §238–248，不得降级）:**
- **P1 — 原始 OHLCV 输入一致性:** 两条路径使用相同 raw candles；对**相同 invalid fixtures 给出相同 accept/reject**。
- **P2 — Feature Engineering 输出一致性:** 比较 **scaling 之前**的原始特征行：名称/顺序/类型/missingness **精确一致**；浮点满足 `|A−B| ≤ atol + rtol·|B|`（`atol=1e-10, rtol=1e-8`）。
- P1 与 P2 **必须分别报告**，不能互相替代。

**步骤:**
1. **预登记（先写后跑）:** 把协议追加进 `03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md`（或新建独立的 parity 预登记小节），明确：fixtures、两端入口、容差、验收规则、commit/env 记录项。**看到结果后不得放宽容差。**
2. **确认两端入口:** 推理端已接（`fx_trade_bot.py::_build_pair_features`）。**训练端 (`retrain_model.py`) 的 `feat_engine.build` 目前尚未接契约**——如需真 parity，请用**同一 `USE_FEATURE_CONTRACT_V2` 模式**把训练路径也接上（默认 OFF、可回退、fail closed）。这是任务 1 的前置判断点。
3. **写 harness:** 建议放在 `experiments/phase3_2_feature_convergence/` 下（如 `parity_harness.py`），**离线、无网络、只读**，复用现有 deterministic fixtures + invalid fixtures（重复时间戳、乱序、缺失 candle、NaN/Inf、未完成最后一根）。
4. **运行并逐特征逐 fixture 记录**（禁止只报聚合分）；输出到 `REPORT` 风格文件。
5. **回写 Doc 05:** P1/P2 = PASS/FAIL，并据此更新 prerequisite 8；若 PASS，检查是否只剩 P3–P5 未验证（若如此，**仍不能宣称 full parity / activation-ready**）。

**注意:** P3–P5 需要 active 的 model / scaler / `.features.json`（含训练 timeframe 元数据）——**这些不在仓库内**。本 host `xgboost` 可正常 import（见 §5），但缺 artifact 仍使 P3–P5 无法完成。

### 任务 b（后做）— DEFER 候选正式裁决

**目标:** 对 Doc 05 登记表中的 DEFER 候选逐项给出**正式处置**并写理由，终结「DEFER 悬空」。

**DEFER 清单（按现行登记表）:** `atr`、`atr_pct`、`atr_percentile`、`atr_ma`、`atr_expanding`、`atr_ratio`、`rsi`、`rsi_slope`、`MACD_12_26_9`、`MACDh_12_26_9`、`MACDs_12_26_9`、`vol_sma_ratio`、`vol_trend`、`is_london`、`is_ny`。

**每项需产出（三选一 + 理由 + 证据引用）:**
- **RESOLVE → REDEFINE / ACCEPTABLE AS-IS**（通常适用：新契约已消除 backend 歧义，定义已存在于 Doc 02 FD-03..06）；
- **KEEP DEFER**（如 `is_london` / `is_ny`：session 定义未决 → 见 Calendar Contract §9 fail-closed）；
- **EXCLUDE**（如 `vol_*`：FD-07 = EXCLUDE，应把登记表的 `BLOCKED` 改为 `EXCLUDE`）。

**同时修掉登记表不一致:** `atr_percentile` 的 matrix disposition(`REDEFINE`) 与 final status(`DEFER`) 需统一。

**约束:** 不改变已批准的技术定义；只做**归属裁决 + 登记更新**。DEFER 候选在裁决为 eligible 前不得进入 Phase 3.3。

---

## 5. 环境与命令

**本机环境（实测，2026-11-15）:**
```
Python 3.12.15 | numpy 1.26.4 | pandas 2.2.3 | scikit-learn 1.5.2
pytest 9.1.1 | tzdata 2026.5 | pytz 2026.1 | xgboost 2.0.3（可 import）
zoneinfo.TZPATH = /home/ubuntu/miniconda3/envs/ai-sprint/share/zoneinfo
```
> 注意：`PHASE3_2_TRAIN_INFERENCE_PARITY_REPORT.md` 记录的是**另一台 host**（numpy 2.2.6 / pandas 3.1.1 / pandas-ta，且 XGBoost 因 `libomp.dylib` 不可用）。做新 parity 时请**重新记录本 host 的 env identity**，不要沿用旧记录。

**常用命令:**
```bash
# 契约 + 接线测试（应为 87 passed）
python -m pytest tests/test_feature_contract.py tests/test_phase3_runtime_containment.py -q

# 语法检查（改动 bot 后必跑）
python -m py_compile fx_trade_bot.py fx_trade_bot_v685.py

# 重跑 Step4 收敛实验（写出 REPORT.md）
python3 experiments/phase3_2_feature_convergence/convergence_experiment.py
```

**已知既有失败（与本次改动无关，勿修）:** 全仓 `pytest tests`（排除条件见下）中约 46 项失败，集中在配置 profile 断言与缺失的 `fx_trade_bot_v683.py`；另有若干模块因缺少符号 collection error。已用 `git stash` 基线对比确认是**改动前就存在**。建议跑分时排除：
`--ignore=tests/integration --ignore=tests/test_fx_trade_bot_data.py --ignore=tests/test_account.py --ignore=tests/test_market_open.py --ignore=tests/test_min_slope_ladder.py --ignore=tests/test_oanda_functions.py --ignore=tests/test_trading_core.py`

---

## 6. 红线与约束（务必遵守）

1. **不训练模型、不写/覆盖 artifact、不部署、不接 READY、不改交易行为。**
2. **fail closed**：任何未获批/未取证的日历、session、gap、invalid candle 一律拒绝，**不得静默 fallback**。
3. **可回退**：所有运行路径改动必须挂在默认 `False` 的开关后（`USE_FEATURE_CONTRACT_V2`）。
4. **只追加不改旧文**：修订/状态变化以追加记录表达，保留证据链。
5. **不得事后放宽容差**；不得把 P3–P5 标成 pass/waived/`NOT REQUIRED`。
6. 未获 owner 明确决定前，不把 `PENDING`/未批准值写成已生效。

---

## 7. 完成判据

- **任务 1 完成** = P1/P2 已预登记、已运行、逐特征逐 fixture 有记录，且 Doc 05 prerequisite 8 状态已回写（PASS/FAIL 均可，但必须是**实测**结果）。
- **任务 b 完成** = 14 项 DEFER 全部有正式处置 + 理由，Doc 05 登记表不一致已修正。
- **Phase 3.2 整体收口**（非明天必须）= P1/P2 PASS 且 P3–P5 有明确 disposition，Doc 05 各字段填毕并 owner 签署，随后才能进 Step7 / Phase 3.3。

---

## 8. 快速上手 checklist

1. `git log -1` 确认在 `152cfcc`；`git status` 确认 clean。
2. 读 [PHASE3_2_REVISION_PLAN.md](PHASE3_2_REVISION_PLAN.md) §3（授权模型）与 §14.1（台账）、[05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md](05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md) §2/§3/§5。
3. 跑 §5 的 pytest 与 py_compile，确认基线绿。
4. 执行 **任务 1**，再执行 **任务 b**。
5. 所有产出以「追加」方式落文档，并更新本文件末尾的「交接进度」。

---

## 9. 交接进度（appended 2026-11-16）

**状态:** 任务 1 完成、任务 b 完成。基线 HEAD=`152cfcc`、branch `v2026c`。

### 任务 1 — P1/P2 parity

- **预登记:** Doc 03 §10「P1/P2 Train–Inference Parity Preregistration」（先写后跑）。
- **训练路径接线:** `retrain_model.py` 新增 `USE_FEATURE_CONTRACT_V2`（`_opt`，默认 OFF、可回退）+ `_build_pair_features()`；`fetch_all_data()` 改走 helper。
- **harness:** 新建 `experiments/phase3_2_feature_convergence/parity_harness.py`（离线、无网络、只读；复用 `convergence_experiment.py` 的 5 个 valid + 11 类 invalid fixtures）。推理端入口因 `fx_trade_bot` import 有网络/客户端副作用，改为**源码级校验 bot ON 分支 transform-free**（已作为 explicit deviation 记入 Doc 03 §10.3）。
- **实测结果（见 `PARITY_P1P2_REPORT.md`）:** **P1 = PASS**（11/11 invalid fixtures 两端均 `REJECT(InputContractError)`）；**P2 = PASS**（5 fixtures × 33 特征，列名/顺序/dtype/missingness 精确一致，`max|A-B|=0`，容差 `1e-10 + 1e-8·|B|`）。cleaning chain identity = SAME。
- **回写:** Doc 05 §2 condition 8 状态更新；`FULL_PARITY_STATUS` 维持 `NOT VERIFIED`（P3–P5 无 active model/scaler bundle）。

### 任务 b — DEFER 候选正式裁决

- **产出:** Doc 05 §8「DEFER candidate adjudication」——15 行逐项「处置 + 理由 + 证据引用」。
- **结果:** ATR/RSI/MACD 家族（11 行）→ `RESOLVE → REDEFINE`；`vol_sma_ratio`/`vol_trend` → `EXCLUDE`（FD-07，登记表 `BLOCKED` 已改）；`is_london`/`is_ny` → `KEEP DEFER`（session 定义未决，Calendar Contract §7/§9 fail-closed）。
- **登记表不一致已修:** `atr_percentile` 的 matrix disposition 与 final status 现统一为 `REDEFINE`（记入 §8 scope note）。
- **未冻结任何候选**（REDEFINE ≠ eligible；待 prerequisite 6/7/11 与 P3–P5 parity 及 owner 签署）。

### 仍阻塞

- P3–P5 parity（缺 active bundle）→ `FULL_PARITY_STATUS = NOT VERIFIED`。
- `is_london`/`is_ny` → 待 owner 批准 session 定义。
- Doc 05 §5 冻结字段（候选清单 / 有序 schema / `Feature Contract Identity` / 证据包 hash / owner 签署）仍为空。
