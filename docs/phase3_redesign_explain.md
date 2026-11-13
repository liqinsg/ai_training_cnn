我会把 PHASE3_REDESIGN.md 定位为 v685 ML 系统从现状修复到可验证、可控部署的正式技术设计文件。

它与 AUDIT_PHASE3.md 的职责不同：
- AUDIT_PHASE3.md：记录事实、缺陷、证据和待确认事项。
- PHASE3_REDESIGN.md：确定目标架构、技术决策、实施顺序和验收标准。
- 后续实施：严格按照设计逐项推进，不能因为某个 AI 工具提出更方便的方案，就擅自改变架构。
我会特别保留三个原则：
1. Evidence before behavior change：先证明问题，再改变行为。
2. Model prediction ≠ Trading authorization：预测、策略资格和执行授权必须分离。
3. No observation without an action path：每项观测都必须有明确的分析目的、判断标准和后续行动。
另外，所有行为改变都采用独立开关，默认关闭。不能把一次代码修复变成整个交易系统的隐性行为变更。

这份设计中，我特别确定了四个关键方向
1. 不预先拆分四个 Profile 的模型。 先建立 Model Identity 和兼容性矩阵，按预测任务决定共享还是独立。
2. 先修复预测契约，再修评分系统。 不允许 generate_signal() 决定 ML 有没有投票资格。
3. 训练与运行彻底分离。 Live Bot 只加载经过批准的模型，不能自行训练和覆盖模型。
4. 评估先于模型优化。 先证明模型究竟有没有 OOS predictive value，再考虑特征、权重和参数优化。
建议执行顺序
下一步：Phase 3.0
先检查 runtime training、共享 artifact、并发覆盖风险。暂不修改模型或交易行为。

我建议把这份文件作为 Phase 3 的正式设计基线。后续每个阶段单独编写严格实施任务，完成后提交证据和验收结果。

最重要的是：我们现在不再需要反复证明系统哪里有问题，而是开始逐项建立一个真正可信的 ML 系统。
