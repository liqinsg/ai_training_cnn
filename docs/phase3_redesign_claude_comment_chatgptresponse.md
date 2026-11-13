
Claude 这次的反馈很有价值。我认为它指出的不是文字润色问题，而是几个会直接影响实施安全性的架构缺口。

我的建议：先修订 PHASE3_REDESIGN.md，再编写 Phase 3.0 实施任务。不要跳过设计修订直接开始编码。

我逐项判断如下。
一、我同意的修改（必须纳入）
Claude 建议	我的决定	原因
ACCEPTED 改 PROPOSED	同意	设计文件不能替用户提前批准架构
D01 改 PD-01	同意	避免与 Audit 的 D1-D9 冲突
O10 Abstention Policy	同意	N1 的核心决策目前没有定义完整
Model Failure 不得阻断 Exit	强烈同意	模型是 Advisor，不应成为持仓管理的单点故障
MC 单位转换使用独立 Adapter	强烈同意	保护现有 TP、Fib 和其他消费方
增加 S0 Observability	同意	低成本、高价值，而且是 Class A
Shadow 提前	同意	3.1 不需要等待新模型就可以验证决策逻辑
Feature 与 Model 联合发布	强烈同意	新特征不能直接交给旧模型
F1、N8、D2-D7 补充任务映射	同意	避免审计发现最后无人负责
D8 独立风险任务	强烈同意	这是交易执行风险，不应只是附带观察
Manifest 增加版本和训练参数	同意	可复现性必须完整
Bootstrap Confidence Intervals	同意	重叠的六根 K 线标签不能简单视为独立样本

二、我想进一步明确四个技术决定
这里有些地方，我不会完全照搬 Claude 的措辞。

1. O10：ML Abstention 到底怎么办？
   这是最重要的未决问题。

假设当前三个投票来源：

- Strength
- MC
- XGB
  如果 XGB Abstain，有三种可能：
  方案	处理方式	我的意见
  A	剩余两个投票一致即可通过	不立即采用
  B	XGB 缺席，按剩余权重重新归一化	不建议默认采用
  C	XGB 是必需输入，缺席则该交易不允许进入	建议初始方案

为什么？

因为 A、B 都会改变现有三票共识机制的含义。

尤其是权重重新归一化，可能让原本不够强的 Strength 和 MC 组合获得更大的决策影响力。

我的建议：

新决策路径中，XGB Abstain 时，该 instrument 的新路径不产生交易授权。

但要区分：

- XGB 没有预测能力：模型评估问题。
- XGB 因输入异常无法预测：数据或工程问题。
- XGB 模型不可用：模型生命周期问题。
  三者不能混为一谈。

以后如果有证据支持 2-of-2，也可以单独设计、校准和测试。
2. Model Failure 不能影响 Exit Management
必须修复的系统安全边界
Claude 提出的 T23 很重要。

我建议明确规定：
MODEL INITIALIZATION FAILURE
          |
          v
ML STATUS = UNAVAILABLE
          |
          +------> EXIT MANAGEMENT CONTINUES
          |
          +------> QUICK-FLIP CONTINUES
          |
          +------> NEW ENTRY POLICY APPLIED

这里需要特别注意：

不能因为模型不可用就让整个 run abort。

但也不能因为模型不可用，就默认允许不依赖模型的新交易。

初始设计采用：

- 持仓管理：继续执行。
- QUICK-FLIP：保持原有独立逻辑。
- 新交易：新决策路径不授权。
- 模型错误：记录明确原因。
  具体实现前还需要检查 main() 的调用顺序及异常边界。

3. Model Stale 时应该怎么办？
   Claude 建议使用 default-on guard。

我支持这个方向，但需要更精确：
MODEL STARTUP
     |
     v
APPROVED ARTIFACT EXISTS?
     |
   YES
     |
     v
CONTRACT VALID?
   /       
 YES       NO
  |         |
 LOAD      UNAVAILABLE
  |
  v
NO RUNTIME TRAINING

如果没有可用的模型：

ML_UNAVAILABLE

而不是现场训练。

如果已有旧模型：

只有当它仍然是经过批准、兼容当前特征契约的 release，才允许加载。

不能仅仅因为文件存在，就认为它安全。

这项运行时保护可以成为默认强制的安全约束，但应单独记录它对原有运行行为的影响并经过验收。
4. 模型没有超过 Baseline 怎么办？
这是原设计遗漏的一个重要终点。

模型训练不是最终目的。

如果经过正确的 OOS 评估，XGB 没有展示超越 baseline 的有效预测价值，那么：

- 不应强制保留 XGB 投票。
- 不应通过调阈值人为制造优势。
- 不应仅因模型已经训练出来就继续使用。
- 应允许将 XGB 投票权重设为 0，或者正式退出该预测任务。
  但需要区分统计不确定性与确认无效：
  结果	决策
  明确优于 baseline	可以进入进一步验证
  结果不确定	不批准新增交易影响
  未优于 baseline	不启用 ML 投票
  明确劣于 baseline	停用该模型版本，调查原因

这也意味着 Phase 3 的成功标准不是必须保留 XGB，而是必须证明它值得保留。

三、实施顺序需要调整
我建议把原来的阶段调整为：

1. Phase 3.0 — Runtime Safety + S0 Observability
   - 检查训练调用链。
   - 禁止 live runtime 写入模型。
   - 模型不可用不能阻断退出管理。
   - 增加 Prediction / Abstain / Score Breakdown 日志。
   - 检查 OCI 与 Laptop 的模型和依赖差异。
2. Phase 3.1 — Decision Contract Repair + Shadow
   - N1、N2、N9、N10、N11、F1。
   - 独立 Advisor。
   - O10 Abstention Policy。
   - 新旧决策路径并行计算。
   - 不改变现有执行。
3. Phase 3.2 — Feature Contract
   - F4、F5、F6、N5、N6、N7、N12、N8。
   - Feature parity。
   - Canonical backend。
   - 完成后必须使用新 Feature Contract 重新训练和发布模型，不能直接激活旧模型。
4. Phase 3.3 — Evaluation Redesign
   - F2、F3、F10、F11。
   - Walk-forward、purge、baseline、calibration。
   - Per-instrument evaluation。
   - Bootstrap confidence intervals。
5. Phase 3.4 — Artifact Lifecycle
   - F7、F8、N3。
   - Manifest、immutable release、promotion、rollback。
   - Model-to-profile compatibility matrix。
6. Phase 3.5 — Integrated Shadow Validation
   - 验证新模型与新特征。
   - 验证完整决策路径。
   - 比较新旧行为。
7. Phase 3.6 — Controlled Activation
   - 逐项批准。
   - 逐项启用。
   - 独立回滚。

D1-D7 和 D8、D9 也需要在设计文件中建立独立的风险跟踪映射，不要让它们因为不属于 ML 核心而消失。

四、关于 Development_plan.md
Claude 提出的这一点也必须处理。

目前不能仅凭设计文件中的引用，就认定 docs/Development_plan.md 已存在并且与 Phase 3 一致。

下一步应在仓库中确认：

1. 文件是否存在。
2. 当前内容是否仍然有效。
3. Phase 3 是否符合其开发原则。
4. 是否存在架构冲突。
   如果不存在，就先处理文档权威关系，不要让实施 Agent 引用一个不存在的规范。

五、我的最终决定
批准进行设计修订
我建议现在形成第二版：

PHASE3_REDESIGN.md v1.1

这次修订必须完成：

- [ ] 修正 ACCEPTED / PROPOSED 状态。
- [ ] 重命名 PD-01 至 PD-15。
- [ ] 增加 O10 Abstention Policy。
- [ ] 增加 T23 Run Continuity。
- [ ] 增加 MC Probability Adapter 隔离设计。
- [ ] 增加模型 OOS 无效时的退出机制。
- [ ] 把 S0 加入 Phase 3.0。
- [ ] 将决策 Shadow 提前至 Phase 3.1。
- [ ] 明确 Feature Contract 与 Model Release 的联合发布。
- [ ] 完成所有审计发现的任务映射。
- [ ] 增加跨主机 Model Hash 检查。
- [ ] 完善 Manifest 和统计置信区间要求。
- [ ] 核实 Development_plan.md。
  我不建议现在就让 Claude 写 Phase 3.0 的代码任务。

先把 v1.1 设计定稿。这样 Phase 3.0 就可以是一份边界清晰、不会边做边重新讨论架构的实施任务。

这次 Claude 的反馈实际上帮我们发现了一个更重要的原则：

ML 可以失效，但交易系统不能因此失去管理已有持仓的能力；ML 可以被保留，但必须先证明它有独立的预测价值。
