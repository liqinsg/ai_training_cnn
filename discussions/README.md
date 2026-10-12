完美看清全貌 ✅ 下面给你一份**结构化归档方案**，完全贴合现有目录、零冲突、不打乱任何东西。

---

## 📂 目录结构总览（已确认）

```
ai_training_cnn/
├── archives/                          ✅ 封存旧版 v683/6.8.2 — 不动
├── attribution_v2/                    ✅ 已有归因框架
│   ├── logs/pf-a/b/c/d/YYYY-MM-DD.jsonl  ← 实时事件流水
│   ├── reports/                         ← 可视化报告
│   └── profiles/                        ← 分Profile配置
├── logs/                              ✅ 纯文本运行日志
│   ├── fx_bot_YYYYMMDD.log
│   └── trading_system_YYYY-MM-DD.log
├── daily_results_profile*/            ✅ 历史交易CSV
├── fx_trade_bot_v684.py               ✅ 当前活跃主程序
├── fx_trade_bot_v683.py               ✅ 封存参照（不改）
├── discussions/                       🆕 新建：会话/决策快照
│   ├── README.md
│   └── 2026-10-11_profile3_jpy_mismatch_close_attribution.json
└── ...
```

### 核心边界确认
| 项目 | 状态 |
|---|---|
| `archives/` + `v683.py` | ✅ 封存不动 |
| `attribution_v2/` | ✅ 复用为实时事件库，直接追加 |
| `logs/` | ✅ 保留人类可读流水，grep 新标签即可 |
| `discussions/` | 🆕 专门存「结论+根因+决策边界」，不混运行日志 |

---

## ✅ 落地执行步骤

### Step 1 — 新建 discussions 目录
```bash
cd ~/projects/ai_training_cnn
mkdir -p discussions
```

### Step 2 — 保存本次会话归档
```bash
nano discussions/2026-10-11_profile3_jpy_mismatch_close_attribution.json
```
粘贴完整JSON（前面已提供），保存退出。

### Step 3 — 建索引说明
```bash
nano discussions/README.md
```
内容：
```markdown
# Discussions & Decisions Archive

## Purpose
Preserve root-cause analysis, architectural decisions, boundary conditions, and follow-up actions.

## File Naming
`YYYY-MM-DD_short_topic_description.json`

## Schema
- `discussion_id`, `title`, `created_utc` — session header
- `reference_run` — triggering log snapshot, key metrics, outcome
- `conclusions` — root cause, AI contribution level, model options, pattern embedding
- `code_changes_delivered` — scope, protected files, reason codes
- `next_actions` — verifiable follow-up items

## Boundary Rules
- Active code: `fx_trade_bot_v684.py`, `fx_trade_bot_utils.py`
- Frozen: `fx_trade_bot_v683.py`, `archives/*` — DO NOT MODIFY
- JPY pairs universe: deferred to separate project

## Real-Time Attribution Stream
- `attribution_v2/logs/pf-{a,b,c,d}/YYYY-MM-DD.jsonl`
- Event types: `OPEN`, `CLOSE`, `UPDATE`
- Log grep tags: `✅ OPEN`, `📤 CLOSE`, `🔄 UPDATE`
```

### Step 4 — 实时归因对接（自动落盘）
每次开/平/更新，除日志+Telegram外，同时写入对应JSONL：
```python
# 在 open_position / close_position / update_tp_sl 调用处追加
import json
from datetime import datetime

def log_to_attribution(profile, event):
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    path = f"attribution_v2/logs/pf-{profile}/{date_str}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

# 示例：平仓时
log_to_attribution("a", {
    "timestamp_utc": datetime.utcnow().isoformat(),
    "event_type": "CLOSE",
    "pair": "AUD_JPY",
    "reason_code": "TIME_EXPIRY",
    "detail": "held 4.2h >= MAX=4h",
    "profile": "profile_a"
})
```
这样 `attribution_v2` 同时具备**实时统计 + 历史追溯**能力。

---

## 📌 最终检索入口

| 想查什么 | 去哪找 |
|---|---|
| 今天为什么没开仓 | `discussions/2026-10-11_*.json` → root_cause |
| 最近都是怎么平仓的 | `grep "📤 CLOSE" logs/*.log` 或 `attribution_v2/logs/pf-*/today.jsonl` |
| 某Profile本月平仓原因分布 | 统计对应 `pf-x/*.jsonl` |
| 代码改了哪些、没动哪些 | `discussions/...json` → `code_changes_delivered` |
| JPY处理计划 | 同文件 → `jpy_handling_decision: DEFERRED` |
| 历史会话索引 | `discussions/README.md` |

---

接下来每次咱们讨论完，我都会自动生成一份 `discussions/YYYY-MM-DD_topic.json`，结论永久留存、边界永远可查。需要我现在把 attribution 实时写入那几行代码直接补进 `fx_trade_bot_v684.py` 吗？
