# Phase 3.2 — 现阶段状态报告（供外部审查）

**报告日期:** 2026-11-16
**用途:** 供外部审查者（ChatGPT）在**无仓库访问权限**的前提下，独立复核 Phase 3.2 的完成度、证据链与剩余风险，并就「下一步动作」给出意见。
**报告依据:** 仓库 `docs/phase3_2/` 决策记录 + 实验输出 + 本机实测复现结果。
**事实标注规则:** 所有状态均已给出可复核证据；凡未验证项一律标注 `NOT VERIFIED`，不做推断性陈述。

---

## 0. 元信息（审查基线）

| 项              | 值                                                                                                                             |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Repo            | `/home/ubuntu/projects/ai_training_cnn`                                                                                      |
| Branch          | `v2026c`（与 `origin/v2026c` 同步）                                                                                        |
| HEAD            | `d6db32c`（"doc archive"）                                                                                                   |
| 工作树          | clean（`git status --porcelain` 为空）                                                                                       |
| 关键基线 commit | `7868a50`（证据包基线，origin/v2026c）                                                                                       |
| 本机环境        | Python 3.12.15 / numpy 1.26.4 / pandas 2.2.3 / scikit-learn 1.5.2 / pytest 9.1.1 / xgboost 2.0.3 / tzdata 2026.5 / pytz 2026.1 |
| 时区数据        | `zoneinfo.TZPATH = /home/ubuntu/miniconda3/envs/ai-sprint/share/zoneinfo`                                                    |

---

## 1. 背景与目标（不变式）

- **Phase 3.2 目标：** 建立一套**新的、可复现、可验证的 Feature Contract**，**不是**修复旧模型兼容性。旧模型的历史包袱可正式结束，但其**证据链与状态记录不得被抹除**。
- **治理层级：** `L1 流程` → `L2-A`（Step1–3：输入契约 / 特征定义 / 实验协议）→ `L2-B`（Step5：证据后运行配置）→ `L3`（Step8–9：实现接线，**不自动获得**）。
- **执行链：** `Step0 → Step0.1 → Step1(IC) → Step2(FD) → Step3(实验授权) → Step4(离线实验) → Step5(RC) → Step6(冻结) → Step7(交接)`。
- **记录方式：** 只追加新状态，不改旧文；不把未批准值写成已生效。

---

## 2. 完成度总览

| Step            | 内容                       | 状态                                        | 证据                                                   |
| --------------- | -------------------------- | ------------------------------------------- | ------------------------------------------------------ |
| Step0 / 0.1     | 重组与基线确认             | ✅ 完成                                     | 治理记录                                               |
| Step1 (IC)      | 输入契约决策 IC-01..08     | ✅ APPROVED                                 | Doc 01                                                 |
| Step2 (FD)      | 特征定义与资格 FD-01..09   | ✅ APPROVED                                 | Doc 02（含 §3.1）                                     |
| Step3           | 实验授权与验收协议         | ✅ APPROVED                                 | Doc 03（含 §10 parity 预登记）                        |
| Step4           | 离线收敛实验               | ✅ 完成                                     | `experiments/phase3_2_feature_convergence/REPORT.md` |
| Step5 (RC)      | 运行配置 RC-01..11         | ✅ APPROVED                                 | Doc 04                                                 |
| **Step6** | **Candidate Freeze** | ✅ **feature 级已签署（2026-11-16）** | Doc 05 §3/§5                                         |
| **Step7** | **Phase 3.3 交接**   | ⛔ **未开始**                         | —                                                     |

新增交付（本阶段）：`ml/feature_contract.py`（新契约唯一实现）、`tests/test_feature_contract.py`、`experiments/phase3_2_feature_convergence/{parity_harness.py, PARITY_P1P2_REPORT.md}`、`retrain_model.py` 与 `fx_trade_bot*.py` 的默认 OFF 可回退接线。

---

## 3. 已冻结内容（Step6 feature 级，owner 已签署）

**Doc 05 头部状态：** `FROZEN (feature-level) — OWNER-SIGNED 2026-11-16; P3–P5 recorded as downstream activation blockers`。

### 3.1 冻结范围（scope）

- **仅冻结 feature-contract 级**：33 列 `ORDERED_FEATURES`（`ml/feature_contract.py`）。
- **P3–P5（scaler / 模型张量 / 预测输出 parity）** 记为**下游 activation blocker**，**不豁免、不降级、不标 `NOT REQUIRED`**（依据 Revision Plan §248）。
- **不冻结**：最终 Phase 3.3 预测 schema、Feature Contract Identity 之外的身份、任何实现授权。

### 3.2 冻结参数（FD-03..FD-06）

`ATR_N=14, RSI_N=14, ADX_N=14, MACD=12/26/9, ECDF_WINDOW=50, ATR_SMA_N=14, ATR_RATIO_N=28`；周期 **M15**；时间戳语义 **candle-OPEN**（IC-02/RC-03）；生产历史长度 **800 bars**（RC-02）；`tzdata==2026.5` + `pytz==2026.1` 钉版、FAIL CLOSED（RC-11）。

### 3.3 登记表分布（Doc 05 §3，共 37 行）

| 终态                                     | 数量 | 名单                                                |
| ---------------------------------------- | ---- | --------------------------------------------------- |
| `TECHNICALLY ELIGIBLE (feature-level)` | 33   | 契约内全部 33 列                                    |
| `EXCLUDE`                              | 2    | `vol_sma_ratio`, `vol_trend`（FD-07）           |
| `DEFER`                                | 2    | `is_london`, `is_ny`（session interval 未定义） |

### 3.4 冻结身份（可复现）

| 字段                      | 值                                                                                                       |
| ------------------------- | -------------------------------------------------------------------------------------------------------- |
| Feature Contract Identity | `FCV2-bffdb0005083f95e`（sha256 `bffdb0005083f95e2030df7ec912af2e87ec930fdd3672f0b1a0d5530e9a0a8c`） |
| Evidence bundle identity  | `3a6ea118b5520dba`（sha256 `3a6ea118b5520dba2462e2ca57dd93bd6e98748f21e95239ca8797e6f91a4c88`）      |
| Owner approver / date     | `owner` / `2026-11-16`                                                                               |
| `FULL_PARITY_STATUS`    | `NOT VERIFIED`（P3–P5 未验证）                                                                        |

FCID 推导 = `sha256(json.dumps({"features": ORDERED_FEATURES, "params": {9 个冻结参数}}, sort_keys=True, separators=(",",":")))`；evidence bundle = 由固定输入集（Doc 01–04、Calendar Contract、REPORT.md、PARITY_P1P2_REPORT.md、`ml/feature_contract.py`、`tests/test_feature_contract.py`）的 `<relpath> <sha256>` 换行清单取 sha256，基线 commit `7868a50`。

---

## 4. 关键证据（本机实测，可复现）

### 4.1 P1/P2 Train–Inference Parity（实验 `PARITY-P1P2-01`，协议 Doc 03 §10）

- **P1 = PASS**：11/11 无效 fixture 在训练路径与推理路径**均** `REJECT(InputContractError)`（重复时间戳 / 乱序 / 缺列 / Inf / NaN / 非正价格 / high<low / HL 不包夹 / naive index / bar 不足 / 空批）。
- **P2 = PASS**：5 个确定性 fixture（up / down / varying / alternating / adx_break）× 33 特征，**列名/顺序/dtype/missingness 精确一致**，所有有限元 `max|A-B| = 0`，容差 `1e-10 + 1e-8·|B|`。
- **支撑事实**：post-build cleaning chain identity = `SAME`；训练端与推理端 ON 分支都路由到同一实现 `ml.feature_contract.build_features` → parity 由「路由同一性 + 该函数的确定性」保证。
- **注意（deviation）**：推理端因 import 有网络/客户端副作用，改为**源码级校验** bot ON 分支 transform-free（Doc 03 §10.3 已登记）。

### 4.2 收敛实验（Step4）

主验收对 `300v500`、`500v800` 在全部 fixture/特征上 PASS；仅 `adx_break` 上 `atr_ecdf_50bar` Δ=0.92，已定性为 **R 类（并列敏感）固有行为**（Doc 02 §3.1），800 bars 稳定区可接受，非阻塞项。

### 4.3 基线健康（本报告撰写时实跑）

```
python -m pytest tests/test_feature_contract.py tests/test_phase3_runtime_containment.py -q
→ 90 passed
python -m py_compile fx_trade_bot.py fx_trade_bot_v685.py retrain_model.py ml/feature_contract.py
→ OK
```

> 既有无关失败：全仓 `pytest tests` 约 46 项失败（配置 profile 断言、缺失 `fx_trade_bot_v683.py` 等），经 `git stash` 基线比对确认**改动前即存在**，与本次无关。

---

## 5. 未决 / 阻塞项（如实记录，未豁免）

### 5.1 P3–P5 parity（`NOT VERIFIED`）——**关键发现**

- 定义：P3=Scaler 输入/输出一致性；P4=模型输入张量一致性；P5=模型预测输出一致性。
- 阻塞原因（复核结论）：
  - 仓库根目录**存在**运行时 bundle：`trade_model_xgb.json`（live 模型）、`trade_model_xgb.features.json`（34 列）、`scaler.joblib`。
  - **但该 bundle 的特征 schema 是旧的 34 特征命名**（`ret_1h, vol_12h, dist_high_24, hour, day_of_week, is_london, is_ny, atr_percentile, atr_expanding, vol_sma_ratio, vol_trend` …），**与新冻结的 33 列 `ORDERED_FEATURES` 不匹配**。
  - 因此**不存在**与新契约对齐的 active bundle 可用于 P3–P5 验证；而**生产/训练/写覆 artifact 均属 Phase 3.2 红线之外**（见 §6）。
- 影响：在 P3–P5 完成前，**不得**宣称 full train/inference/model parity、Phase 3.2 end-to-end parity 或 activation-ready（Revision Plan §247）。

### 5.2 `is_london` / `is_ny`（`DEFER`）

session interval / boundaries 未获 owner 批准；Calendar Contract **显式不定义**该窗口，相邻 gap classifier 仍 fail-closed。二者**不得**进入 Phase 3.3，直至 session 定义获批并完成裁决。

### 5.3 Step7（Phase 3.3 交接）未开始

Step7 仅能做：把 33 项 `TECHNICALLY ELIGIBLE` 候选交接给 Phase 3.3 做**预测价值**评估；**不冻结预测 schema、不签发身份、不授权实现**（Revision Plan §365）。

---

## 6. 风险与治理边界

1. **语义误读风险**：`FROZEN (feature-level)` 可能被误读为 activation-ready。缓解：Doc 05 头部与 §5 反复标注 P3–P5 为尾部 blocker、`FULL_PARITY_STATUS = NOT VERIFIED`。
2. **artifact 缺口风险**：无与 33 列契约对齐的 active bundle → P3–P5 与真实部署均被阻断；补齐需**新授权**（训练/写 artifact）。
3. **session 语义风险**：`is_london/is_ny` 与 Calendar Contract 的 fail-closed 边界尚未闭合。
4. **红线（仍生效）**：不训练模型、不写/覆盖 artifact、不部署、不接 READY、不改交易行为；fail closed；只追加不改旧文；不得事后放宽容差；不得把 P3–P5 标成 pass/waived/`NOT REQUIRED`。
5. **可回退性**：所有运行路径改动均挂默认 `False` 的 `USE_FEATURE_CONTRACT_V2` 开关后；关闭时出厂路径不变。

---

## 7. 候选下一步（供审查排序）

| 选项                                        | 内容                                                          | 前置条件                                                    | 若选的影响                                         |
| ------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------- | -------------------------------------------------- |
| **A. 推进 Step7（Phase 3.3 交接包）** | 起草交接包，只交接 33 项候选做预测价值评估                    | owner 接受；不越界签发身份                                  | 开启 Phase 3.3，但 P3–P5 阻塞仍在                 |
| **B. 先补 P3–P5**                    | 获取/生成与新契约对齐的 active bundle 并跑 P3–P5             | 需**新授权**（训练+artifact 写入，越 Phase 3.2 红线） | 可关闭 `FULL_PARITY_STATUS`，但需 owner 明确开闸 |
| **C. 先闭合 session 定义**            | 定义并批准 `is_london/is_ny` 的 session interval/boundaries | owner 决策；涉及 Calendar Contract 修订                     | 解除 2 项 DEFER，可能改变 gap fail-closed 边界     |
| **D. 阶段性收口**                     | 以「feature 级冻结」为 Phase 3.2 收口点，冻结现状并归档       | owner 确认范围                                              | 停止扩展，把风险明确留待 Phase 3.3/新阶段          |

**助手倾向（仅供参考，非决策）：** 先 **A**（Step7 交接包），同时把 **B/C** 作为明确登记的遗留 item 交接下去——因为 A 不触碰红线、可立即推进，而 B 需新授权、C 需 owner 决策，均不应在未获批时自行启动。

---

## 8. 请审查者回答的问题

- **Q1（范围）**：以「feature 级冻结 + P1/P2 PASS + P3–P5 如实标注 NOT VERIFIED」作为 Phase 3.2 的收口，是否**足够**且**无虚报**？是否存在需要额外证据才能支撑 feature 级冻结的地方？
- **Q2（下一步）**：§7 的 A/B/C/D 应如何排序？是否有遗漏的第五选项？
- **Q3（Step7 边界）**：Phase 3.3 交接包中，哪些内容属于「只交接、不签发」，哪些必须等 P3–P5？请给出交接包的最小合规内容清单。
- **Q4（P3–P5 路径）**：在当前「无对齐 bundle 且禁止写 artifact」的约束下，P3–P5 是否有**不训练、不写 artifact** 的合法验证路径（例如只读复用既有 legacy bundle 做「schema-mismatch 应 fail-closed」的负向验证）？还是必须新授权？
- **Q5（session）**：`is_london/is_ny` 的 session interval 应由谁定义、以何种契约落地，才能不破坏 Calendar Contract 的 fail-closed 语义？
- **Q6（风险）**：本报告中「已知但未处置」的风险（artifact 缺口、session 悬空、feature 级 vs full parity 的语义差）是否还有被遗漏的？
- **Q7（红线）**：当前红线是否应当调整？若调整，触发条件与批准人应是谁？

---

## 附录 A — 文件 / commit 索引

| 类别        | 路径                                                                                                    |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| 输入契约    | `docs/phase3_2/01_INPUT_CONTRACT_OWNER_DECISION.md`                                                   |
| 特征定义    | `docs/phase3_2/02_FEATURE_TECHNICAL_DEFINITIONS_AND_ELIGIBILITY.md`                                   |
| 实验授权    | `docs/phase3_2/03_EXPERIMENT_AUTHORIZATION_AND_ACCEPTANCE.md`（§10 parity 预登记）                   |
| 运行配置    | `docs/phase3_2/04_RUNTIME_CONFIGURATION_DECISIONS.md`                                                 |
| 冻结记录    | `docs/phase3_2/05_TECHNICALLY_ELIGIBLE_CANDIDATE_FREEZE.md`（§3 登记表 / §5 签署 / §8 DEFER 裁决） |
| 日历契约    | `docs/phase3_2/PHASE3_2_CALENDAR_CONTRACT.md`                                                         |
| 治理路线图  | `docs/phase3_2/PHASE3_2_REVISION_PLAN.md`（§5 授权 / §8 parity 分层 / §364–365 Step6–7）         |
| 交接书      | `docs/phase3_2/PHASE3_2_HANDOVER.md`（§9 交接进度）                                                  |
| 契约实现    | `ml/feature_contract.py`                                                                              |
| 契约单测    | `tests/test_feature_contract.py`                                                                      |
| 收敛实验    | `experiments/phase3_2_feature_convergence/REPORT.md`                                                  |
| parity 报告 | `experiments/phase3_2_feature_convergence/PARITY_P1P2_REPORT.md` + `parity_harness.py`              |

## 附录 B — 相关 commit

```
d6db32c doc archive
dc3caac docs(phase3_2): back-fill Doc 05 register and issue feature-level freeze
7868a50 docs(phase3_2): record P1/P2 parity PASS and close DEFER adjudication
152cfcc phase3.2
```
