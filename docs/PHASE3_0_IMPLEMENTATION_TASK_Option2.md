我建议选择 **Option 2：先实施非边界工作，Entry Authorization 保持冻结**。

Stage A 的证据已经足够支持这个决定，不需要再扩大审计范围。尤其是 Section C 和 E，已经把两个不同问题分离出来了：

1. **运行控制流缺陷：** `ensure_model()` 失败会直接终止整个 cycle，导致本来不依赖 ML 的 Step 5、Step 6 和 owned-position management 无法执行。
2. **Entry Authorization 缺陷：** ML 不可用时，虽然 XGB 方向票是 `NEUTRAL`，但合成的 `X` 仍进入 `FINAL`，可能让 Strength + MC 的共识满足入场条件。

这两项必须分开处理，不能因为修复第一项，就顺手改变第二项。

## **Gate A 决定**

批准：Option 2

| 工作项                                         | 决定         | 边界                                                      |
| ------------------------------------------- | ---------- | ------------------------------------------------------- |
| 显式 ML 状态与失败原因                               | 批准         | 不重构完整 Prediction Contract                               |
| `ensure_model()` 失败隔离                       | 批准         | 保证独立的 Step 5 / Step 6 / owned-position management 可继续执行 |
| ML-dependent confluence                     | 批准         | ML 不可用时保持明确的失败状态，不伪造成功                                  |
| Live runtime training / artifact writes 防护  | 批准         | 不影响 `retrain_model.py` 离线训练                             |
| Legacy `.pkl` load 后自动 re-save              | 批准处理       | 禁止 live runtime 静默重新发布 artifact                         |
| Host / model / scaler / release diagnostics | 批准         | 只记录身份，不做跨主机同步                                           |
| Step 7 entry authorization                  | **暂不批准修改** | 保留现状，等待单独审批                                             |
| OANDA 实盘部署                                  | **不批准**    | 本阶段只做代码实现和测试                                            |

## **两个必须明确的实施要求**

**1. 不要把&#x20;**`ensure_model()`**&#x20;的异常简单吞掉。**

我希望最终能够区分：

- `READY`
- `MODEL_MISSING`
- `UNAVAILABLE`
- `INCOMPATIBLE`
- `LOAD_FAILED`

记录失败原因，并明确后续哪些分支可以继续、哪些必须停止。

尤其要验证：Step 5、Step 6、owned-position management 是否真的不依赖 ML，而不是仅凭函数名称判断。

**2. 暂不修改 Entry Authorization，不代表认可当前行为。**

这是一个明确保留的风险：

- ML unavailable 时，合成 `X` 仍可能参与评分。
- Strength + MC 仍可能满足方向共识。
- 因此，在 Entry Authorization 尚未单独批准前，不能把这份实现视为可以部署的安全版本。

不要偷偷把它改成禁入，也不要偷偷保留它并宣称 ML unavailable 已经安全处理。报告中必须明确写出：**Entry Authorization remains unchanged and unresolved.**

## **Stage B–E 的执行顺序**

建议按以下顺序执行，不再重新做全量审计：

1. **Stage B — Runtime containment**：ML 初始化失败隔离，保护独立仓位管理路径。
2. **Stage C — Artifact write protection**：阻止 live runtime 训练和静默 artifact 发布，保留离线训练。
3. **Stage D — Observability**：记录 host、profile、artifact、hash 和 runtime status。
4. **Stage E — Regression tests**：覆盖正常路径、模型缺失、加载失败、训练数据不足、artifact 不变，以及独立仓位管理继续运行。

有一个额外要求：测试必须证明正常模型加载路径没有被破坏；不能只证明失败路径可以继续运行。

## **最终验收时必须单独列出**

- `ensure_model()` 失败不再阻断独立仓位管理。
- ML 失败不会被伪装成有效模型结果。
- Live runtime 不训练、不修改、不重新发布模型 artifacts。
- Offline trainer 仍然可以正常工作。
- 两个运行主机的模型身份可以独立核对。
- 健康模型路径回归测试通过。
- Entry Authorization 未修改，并明确标记为待审批。
- 没有真实订单测试，没有 live deployment。

**你可以让实现代理从 Stage B 开始，继续完成 Stage C–E。** 不需要再返回一份新的宏观设计，也不需要重新审计所有 ML 算法。最终交付应当是精确 diff、测试证据和未解决事项，而不是又一份庞大的问题清单。

这次的目标很具体：先修复运行控制流和 artifact 生命周期问题，再单独决定 ML 是否有资格参与入场授权。