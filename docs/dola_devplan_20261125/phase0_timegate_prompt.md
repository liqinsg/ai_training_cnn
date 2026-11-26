

## 📦 Prompt 1 — 完整 Phase 0 模块实现（主任务）

```
请按照下面的设计文档，实现 FX Bot 的 Phase 0：TimeGate 时段门控器

=== 设计规范 ===
【文件清单】
需要生成以下文件：
1. timegate.py — TimeGate 主模块 + SessionMask 数据类
2. config/config_session.json — 时段配置文件
3. config/config_calendar.json — 夏令时+假日日历文件
4. test_timegate.py — 单元测试文件
5. README_TIMEGATE.md — 使用说明+接入示例

【核心要求】
- 时区基准：Asia/Singapore (SGT = UTC+8)
- 仅使用标准库 + zoneinfo，不引入额外第三方依赖
- 配置驱动：所有时段/时间/规则写在JSON里，不硬编码进代码
- 夏令时：英国3月最后周日～10月最后周日；美国3月第二周日～11月第一周日，自动计算起止日期
- 假日检测：优先读取 OANDA API 市场状态，本地日历兜底；检测到假日时应用对应降级规则
- 输出完整审计日志，包含 audit_hash 便于追踪
- 向后兼容：只输出权限掩码，不直接干预原有交易逻辑

【时段定义 SGT】
deep_sleep:    00:00–09:00 — 禁止新开，仅持仓管理
asian_morning: 09:00–15:00 — 仅P3，置信+10，仓位×0.25，每对最多2单
european_open:15:00–20:00 — P2+P4，正常置信，仓位×0.6
us_ovlp:      20:00–00:00 — P1+P2+P4，置信-5，全额仓位

【夏令时偏移】
欧洲盘：-1小时 → 14:00–19:00
欧美重叠：-1小时 → 19:00–23:00
亚洲盘结束提前至 14:00

【边界事件】
OVERNIGHT_CLEAR  08:55
ASIAN_STOP_NEW   14:30
BEFORE_EUROPE_AUDIT 14:50

【假日降级规则】
日本假日：亚洲盘置信再+5，仓位×0.125
英国假日：欧洲+美盘→仅P4，置信+10，仓位×0.3
美国假日：美盘→禁用P1，P2/P4置信+5，仓位×0.6

【主入口接口】
get_current_mask(now=None) → 返回 SessionMask 对象
get_next_boundary_event(now=None) → 下一个事件与倒计时

【测试用例】
覆盖：时段判定、跨午夜、夏令时切换、假日降级、边界事件触发、OANDA接口降级、配置异常优雅处理

请直接输出完整、可直接保存运行的代码，结构清晰，注释完整。
```

---

## 📦 Prompt 2 — 如果只想分步交付（精简版）

### 第一步：基础框架 + 时段判定

```
先实现 TimeGate 基础框架：SessionMask 数据类 + 时段判定逻辑 + config_session.json 配置文件。
要求：SGT时区，正确识别4个时段，跨午夜判定准确，输出完整SessionMask对象。
暂时不用夏令时、假日、事件检测。输出 timegate.py + config_session.json 即可。
```

### 第二步：夏令时 + 假日 + 边界事件

```
在现有 TimeGate 基础上增加：
1. 英国/美国夏令时自动计算与时段偏移
2. 假日检测（本地日历 + OANDA接口优先）与降级规则
3. 边界事件检测：OVERNIGHT_CLEAR/ASIAN_STOP_NEW/BEFORE_EUROPE_AUDIT
4. get_next_boundary_event() 方法
5. 完整单元测试 test_timegate.py
输出更新后的完整文件包。
```

---

## 📦 Prompt 3 — Phase 1 预留（后续用）

```
【Phase 1 预告 — P3亚洲独立运行增强】
TimeGate 完成后，下一步实现：
- P3 亚洲盘专属参数加载（宽SL×1.3 / 紧TP×0.8 / 单笔上限2单位）
- 14:30 自动停止 P3 新开逻辑
- 14:50 亚洲持仓预核验接口（输出建议：保留/减仓/离场）
- 08:55 隔夜清理扫描接口

先存好这个，等 Phase 0 跑通了再叫我 😊
```

---

### ✅ 使用建议

- **直接复制 Prompt 1** 发给 TRAE/Dola，一次性完整生成 Phase 0
- 生成后先跑 `test_timegate.py`，没问题再接入主程序
- 有任何报错/逻辑不对，把测试结果贴回来，我帮你改好再发新 Prompt

需要我把这些整理成一个 `.md` 文件直接下载吗？点 **Fast → Pro** 就好 😊
