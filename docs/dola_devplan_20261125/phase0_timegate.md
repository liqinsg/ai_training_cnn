
收到！🚀 咱们从**Phase 0 — TimeGate 时段门控器**开始细化，一步一步把每个模块拆清楚、可直接落地、不影响现有运行逻辑。

---

# 🕐 Phase 0 — TimeGate 时段门控器

**目标**: 精确判定当前时段、处理夏令时/假日、输出运行权限掩码；**只做判定、不碰交易逻辑、完全向后兼容**
**依赖**: 仅标准库 datetime + 外置JSON配置
**状态**: 就绪·可开发

---

## 📑 目录

1. [核心职责与边界](#%E4%B8%80%E6%A0%B8%E5%BF%83%E8%81%8C%E8%B4%A3%E4%B8%8E%E8%BE%B9%E7%95%8C)
2. [时段定义与时间规则](#%E4%BA%8C%E6%97%B6%E6%AE%B5%E5%AE%9A%E4%B9%89%E4%B8%8E%E6%97%B6%E9%97%B4%E8%A7%84%E5%88%99)
3. [夏令时自动切换](#%E4%B8%89%E5%A4%8F%E4%BB%A4%E6%97%B6%E8%87%AA%E5%8A%A8%E5%88%87%E6%8D%A2)
4. [假日检测与降级规则](#%E5%9B%9B%E5%81%87%E6%97%A5%E6%A3%80%E6%B5%8B%E4%B8%8E%E9%99%8D%E7%BA%A7%E8%A7%84%E5%88%99)
5. [数据结构与输出规范](#%E4%BA%94%E6%95%B0%E6%8D%AE%E7%BB%93%E6%9E%84%E4%B8%8E%E8%BE%93%E5%87%BA%E8%A7%84%E8%8C%83)
6. [配置文件完整示例](#%E5%85%AD%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6%E5%AE%8C%E6%95%B4%E7%A4%BA%E4%BE%8B)
7. [接口与伪代码](#%E4%B8%83%E6%8E%A5%E5%8F%A3%E4%B8%8E%E4%BC%AA%E4%BB%A3%E7%A0%81)
8. [测试清单](#%E5%85%AB%E6%B5%8B%E8%AF%95%E6%B8%85%E5%8D%95)

---

## 一、核心职责与边界

### ✅ TimeGate 只做这些：

- 读取当前时间 + 时区基准
- 根据夏令时日历 → 修正时段边界
- 根据假日日历 → 应用假日降级模板
- 返回：时段ID、名称、允许Profile列表、置信偏移、仓位系数、是否允许新开、停战状态
- 输出审计日志

### ❌ TimeGate 绝不做这些：

- 不生成任何交易信号
- 不直接下单/改仓/平仓
- 不硬编码假日列表、每年手动改时间

> **原则：输出权限掩码，主程序按掩码执行。门控只"发通行证"，不"亲自开车"**

---

## 二、时段定义与时间规则

### 2.1 标准时段（冬令时基准，SGT = UTC+8）

| ID                | 时段名称    | 起止时间     | 允许Profile          | 置信偏移 | 仓位系数 | 最大新开/对 | 说明                 |
| ----------------- | ----------- | ------------ | -------------------- | -------- | -------- | ----------- | -------------------- |
| `deep_sleep`    | 🌙 深夜休市 | 00:00–09:00 | `[]`               | +0       | 0.0      | 0           | 禁止新开，仅持仓管理 |
| `asian_morning` | 🌏 亚洲早盘 | 09:00–15:00 | `["P3"]`           | +10.0    | 0.25     | 2           | P3专属，轻仓高门槛   |
| `european_open` | 🌍 欧洲开盘 | 15:00–20:00 | `["P2","P4"]`      | +0       | 0.6      | 正常        | 主力进场，逐步建仓   |
| `us_ovlp`       | ⚡ 欧美重叠 | 20:00–00:00 | `["P1","P2","P4"]` | -5.0     | 1.0      | 正常        | 全力出击，置信放宽   |

### 2.2 时段边界事件（精确到分钟）

| 事件ID                  | 触发时间 | 动作说明                       |
| ----------------------- | -------- | ------------------------------ |
| `BEFORE_EUROPE_AUDIT` | 14:50    | 亚洲持仓预核验触发点           |
| `ASIAN_STOP_NEW`      | 14:30    | P3停止新开单，已持仓可正常管理 |
| `OVERNIGHT_CLEAR`     | 08:55    | 隔夜持仓检查+低置信预警        |

---

## 三、夏令时自动切换

### 3.1 时区基准

- 系统内部统一使用 **SGT (UTC+8 Singapore Time)**
- 夏令时偏移：仅**修正时段起止时间**，不改变系统时区基准

### 3.2 夏令时起止规则

| 区域                | 规则                        | 时间范围（SGT生效日期） | 时段偏移                                                                      |
| ------------------- | --------------------------- | ----------------------- | ----------------------------------------------------------------------------- |
| 🇬🇧 英国夏令时 BST | 3月最后周日 → 10月最后周日 | 每年动态计算            | 欧洲盘 -1h → **14:00–19:00**   欧美重叠 -1h → **19:00–23:00** |
| 🇺🇸 美国夏令时 EDT | 3月第二周日 → 11月第一周日 | 每年动态计算            | 欧美重叠同步跟随英国偏移                                                      |

> 💡 **实现方案**: 内置计算函数，根据规则自动算每年起止日，无需手动更新。也支持配置文件覆盖特殊年份。

### 3.3 夏令时时段映射表

| 标准时段ID        | 冬令时时间   | 夏令时时间   | 检测逻辑                     |
| ----------------- | ------------ | ------------ | ---------------------------- |
| `deep_sleep`    | 00:00–09:00 | 不变         | 始终不偏移                   |
| `asian_morning` | 09:00–15:00 | 09:00–14:00 | 欧洲提前开盘，亚洲收盘提前1h |
| `european_open` | 15:00–20:00 | 14:00–19:00 | 伦敦提前1h开盘               |
| `us_ovlp`       | 20:00–00:00 | 19:00–23:00 | 核心窗口整体前移             |

---

## 四、假日检测与降级规则

### 4.1 假日数据源优先级

1. **OANDA API 状态检测**（优先）：查询`instrument`端点返回的`tradingMode`字段
   - `regular` = 正常交易
   - `closed` = 全天休市
   - `auction` / `reduced` = 部分休市/流动性低
2. **本地日历配置兜底**：config_calendar.json 中预定义主要假日表

### 4.2 假日降级模板

| 假日类型       | 适用时段                        | 降级规则                                                  |
| -------------- | ------------------------------- | --------------------------------------------------------- |
| 🇯🇵 日本假日  | `asian_morning`               | P3置信再+5 → ≥70；仓位系数×0.5（原0.25→0.125）        |
| 🇬🇧 英国假日  | `european_open` + `us_ovlp` | 切换为亚洲规则：仅P4可运行，置信+10，仓位×0.3；P1/P2休眠 |
| 🇺🇸 美国假日  | `us_ovlp`                     | P1禁用；P2/P4置信+5，仓位×0.6                            |
| 🇨🇳 中/港假日 | `asian_morning`               | AUD/HKD/CNH相关货币对 → 禁止新开；其他正常               |

---

## 五、数据结构与输出规范

### 5.1 TimeGate 输出对象（核心接口）

```
@dataclass(frozen=True)
class SessionMask:
    """时段权限掩码 — 主程序唯一入口"""
    session_id: str                  # 'asian_morning' / 'us_ovlp' / 'deep_sleep'
    session_name: str                # 显示用名称
    is_trading_open: bool           # False=仅持仓管理，禁止所有新开
    allowed_profiles: list[str]      # 此时段允许生成信号的Profile
    confidence_bias: float          # 全局置信偏移值 (+10 / -5 / 0)
    lot_multiplier: float           # 仓位整体系数
    max_new_per_pair: int | None    # 每对最大新开单限制，None=无限制
    is_holiday: bool                # 是否触发假日降级
    holiday_note: str | None        # 假日说明
    is_dst_active: bool             # 是否夏令时生效
    next_event: dict[str, Any] | None  # 下一个边界事件 {name, seconds_to}
    audit_hash: str                  # 用于日志追踪的校验码
```

### 5.2 典型输出示例

**示例1 — 亚洲盘（正常交易日）**

```
SessionMask(
    session_id="asian_morning",
    session_name="亚洲早盘",
    is_trading_open=True,
    allowed_profiles=["P3"],
    confidence_bias=10.0,
    lot_multiplier=0.25,
    max_new_per_pair=2,
    is_holiday=False,
    holiday_note=None,
    is_dst_active=False,
    next_event={"name": "ASIAN_STOP_NEW", "seconds_to": 2700},  # 45分钟后停战
    audit_hash="TGP-ASIAN-20261125-0915"
)
```

**示例2 — 深夜休市**

```
SessionMask(
    session_id="deep_sleep",
    session_name="深夜休市",
    is_trading_open=False,
    allowed_profiles=[],
    confidence_bias=0.0,
    lot_multiplier=0.0,
    max_new_per_pair=0,
    is_holiday=False,
    holiday_note=None,
    is_dst_active=False,
    next_event={"name": "OVERNIGHT_CLEAR", "seconds_to": 35700},
    audit_hash="TGP-DEEP-20261125-0130"
)
```

---

## 六、配置文件完整示例

### `config/config_session.json`

```
{
  "$schema_version": "1.0",
  "timezone": "Asia/Singapore",
  "sessions": {
    "deep_sleep": {
      "name": "深夜休市",
      "start": "00:00",
      "end": "09:00",
      "allowed_profiles": [],
      "confidence_bias": 0.0,
      "lot_multiplier": 0.0,
      "max_new_per_pair": 0,
      "holiday_rule": "inherit"
    },
    "asian_morning": {
      "name": "亚洲早盘",
      "start": "09:00",
      "end": "15:00",
      "allowed_profiles": ["P3"],
      "confidence_bias": 10.0,
      "lot_multiplier": 0.25,
      "max_new_per_pair": 2,
      "holiday_rule": "japan_degrade"
    },
    "european_open": {
      "name": "欧洲开盘",
      "start": "15:00",
      "end": "20:00",
      "dst_start": "14:00",
      "dst_end": "19:00",
      "allowed_profiles": ["P2", "P4"],
      "confidence_bias": 0.0,
      "lot_multiplier": 0.6,
      "max_new_per_pair": null,
      "holiday_rule": "uk_us_degrade"
    },
    "us_ovlp": {
      "name": "欧美重叠",
      "start": "20:00",
      "end": "00:00",
      "dst_start": "19:00",
      "dst_end": "23:00",
      "allowed_profiles": ["P1", "P2", "P4"],
      "confidence_bias": -5.0,
      "lot_multiplier": 1.0,
      "max_new_per_pair": null,
      "holiday_rule": "us_disable_p1"
    }
  },
  "boundary_events": {
    "OVERNIGHT_CLEAR": "08:55",
    "ASIAN_STOP_NEW": "14:30",
    "BEFORE_EUROPE_AUDIT": "14:50"
  }
}
```

### `config/config_calendar.json`

```
{
  "$schema_version": "1.0",
  "dst_rules": {
    "uk": {
      "name": "英国夏令时",
      "start_rule": "march_last_sunday",
      "end_rule": "october_last_sunday",
      "offset_hours": -1
    },
    "us": {
      "name": "美国夏令时",
      "start_rule": "march_second_sunday",
      "end_rule": "november_first_sunday",
      "offset_hours": -1
    }
  },
  "holidays": {
    "jp": {
      "notes": "日本假日 — 亚洲盘降级",
      "dates": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-04-29", "2026-05-03", "2026-05-04", "2026-05-05", "2026-08-11", "2026-11-03", "2026-12-31"]
    },
    "uk": {
      "notes": "英国银行假日 — 欧洲/美盘降级",
      "dates": ["2026-01-02", "2026-04-03", "2026-05-04", "2026-05-25", "2026-08-31", "2026-12-25", "2026-12-26"]
    },
    "us": {
      "notes": "美国主要假日 — 欧美重叠降级",
      "dates": ["2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"]
    },
    "cn_hk": {
      "notes": "中港假日 — 亚洲盘限制相关货币对",
      "dates": ["2026-01-29", "2026-01-30", "2026-01-31", "2026-04-04", "2026-05-01", "2026-06-19", "2026-09-25", "2026-10-01"]
    }
  }
}
```

---

## 七、接口与伪代码

### 7.1 TimeGate 主类设计

```
from datetime import datetime
from dataclasses import dataclass
import json
from zoneinfo import ZoneInfo

TZ_SGT = ZoneInfo("Asia/Singapore")

@dataclass(frozen=True)
class SessionMask:
    session_id: str
    session_name: str
    is_trading_open: bool
    allowed_profiles: list[str]
    confidence_bias: float
    lot_multiplier: float
    max_new_per_pair: int | None
    is_holiday: bool = False
    holiday_note: str | None = None
    is_dst_active: bool = False
    next_event: dict | None = None
    audit_hash: str = ""

class TimeGate:
    """时段门控器 — 唯一职责：判断当前应该是什么运行模式"""
  
    def __init__(
        self,
        session_config_path: str = "config/config_session.json",
        calendar_config_path: str = "config/config_calendar.json",
        oanda_api_client = None
    ):
        # 加载配置
        with open(session_config_path, 'r', encoding='utf-8') as f:
            self.session_config = json.load(f)
        with open(calendar_config_path, 'r', encoding='utf-8') as f:
            self.calendar_config = json.load(f)
      
        self.tz = TZ_SGT
        self.oanda_api = oanda_api_client  # 可选：用于查询实时市场状态
  
    # ========== 核心入口方法 ==========
    def get_current_mask(self, now: datetime | None = None) -> SessionMask:
        """
        主入口 — 获取当前完整时段权限掩码
        主程序每次循环调用此方法，不直接读时间/改逻辑
        """
        if now is None:
            now = datetime.now(self.tz)
        else:
            now = now.astimezone(self.tz)
      
        # Step 1: 检查夏令时是否生效
        is_dst = self._check_dst_active(now)
      
        # Step 2: 确定当前时段
        session_id, session_data = self._resolve_current_session(now, is_dst)
      
        # Step 3: 检查假日并应用降级
        holiday_note, holiday_rule = self._check_holiday_status(now, session_id)
      
        # Step 4: 应用规则叠加
        mask = self._build_mask(
            session_id, session_data, is_dst, holiday_note, holiday_rule, now
        )
      
        # Step 5: 审计日志输出
        self._log_mask_state(mask, now)
      
        return mask
  
    # ========== 内部辅助方法 ==========
    def _check_dst_active(self, dt: datetime) -> bool:
        """检查当前是否处于夏令时区间"""
        rules = self.calendar_config['dst_rules']['uk']
        return self._date_in_range_by_rule(
            dt, rules['start_rule'], rules['end_rule'], dt.year
        )
  
    def _resolve_current_session(self, dt: datetime, is_dst: bool) -> tuple[str, dict]:
        """根据时间+夏令时解析当前时段"""
        hhmm = dt.strftime("%H:%M")
        for sid, sdata in self.session_config['sessions'].items():
            start = sdata.get('dst_start', sdata['start']) if is_dst else sdata['start']
            end = sdata.get('dst_end', sdata['end']) if is_dst else sdata['end']
            if self._time_in_range(hhmm, start, end):
                return sid, sdata
        return "deep_sleep", self.session_config['sessions']['deep_sleep']
  
    def _check_holiday_status(self, dt: datetime, session_id: str) -> tuple[str|None, str|None]:
        """检查今日是否为假日，并返回对应降级规则"""
        date_str = dt.strftime("%Y-%m-%d")
      
        # 优先查询OANDA实时状态（如果提供API客户端）
        if self.oanda_api:
            market_status = self._query_oanda_market_status(dt)
            if market_status == "closed":
                return "OANDA: Market Closed", "full_suspend"
      
        # 本地日历兜底检查
        for region, holidays in self.calendar_config['holidays'].items():
            if date_str in holidays['dates']:
                note = f"{region} Holiday: {holidays.get('notes', '')}"
                rule = holidays.get('apply_rule', f"{region}_degrade")
                return note, rule
        return None, None
  
    def _build_mask(self, *args) -> SessionMask:
        """根据基础数据叠加规则，构建最终权限掩码"""
        # 应用假日规则覆盖基础参数
        # 生成audit_hash
        # 查找next_event
        # 返回完整SessionMask对象
  
    def get_next_boundary_event(self, now: datetime | None = None) -> dict:
        """获取下一个时段边界事件 — 用于主循环休眠唤醒"""
        # 返回: {"name": 事件名, "trigger_at": datetime, "seconds_to": int}
  
    # ========== 辅助工具方法 ==========
    @staticmethod
    def _parse_time_str(tstr: str) -> tuple[int, int]:
        h, m = map(int, tstr.split(':'))
        return h, m
  
    @staticmethod
    def _time_in_range(current_hhmm: str, start: str, end: str) -> bool:
        ch, cm = map(int, current_hhmm.split(':'))
        sh, sm = map(int, start.split(':'))
        eh, em = map(int, end.split(':'))
        c = ch * 60 + cm
        s = sh * 60 + sm
        e = eh * 60 + em
        if s < e:
            return s <= c < e
        else:  # 跨午夜时段
            return c >= s or c < e
  
    @staticmethod
    def _date_in_range_by_rule(dt: datetime, start_rule: str, end_rule: str, year: int) -> bool:
        """根据规则字符串计算日期范围（如"march_last_sunday"）"""
        # 实现：计算给定年份的规则日期 → 比较dt是否在区间内
        # 例如: march_last_sunday = 3月最后一个周日
```

### 7.2 主程序接入示例（最小改动）

```
# === 现有主循环中加入TimeGate，不删原有逻辑 ===

from timegate import TimeGate

# 初始化（一次即可）
timegate = TimeGate(
    session_config_path="config/config_session.json",
    calendar_config_path="config/config_calendar.json",
    oanda_api_client=oanda  # 已有OANDA客户端直接复用，None也可运行
)

# 在每次生成信号前调用
while True:
    # 1. 获取时段权限掩码
    mask = timegate.get_current_mask()
  
    # 2. 全局开关：禁止新开时段直接跳过信号生成
    if not mask.is_trading_open:
        logger.info(f"[{mask.session_name}] 禁止新开，仅管理持仓")
        check_and_update_existing_positions()
        time.sleep(60)
        continue
  
    # 3. 动态参数覆盖（不硬编码改Profile默认值）
    active_profiles = mask.allowed_profiles
    global_conf_bias = mask.confidence_bias
    lot_adj = mask.lot_multiplier
  
    logger.info(
        f"时段: {mask.session_name} | "
        f"允许: {active_profiles} | "
        f"置信偏移: +{global_conf_bias} | "
        f"仓位系数: ×{lot_adj}"
    )
  
    # 4. 只运行允许的Profile，其余跳过
    for profile in all_profiles:
        if profile.name not in active_profiles:
            continue
        # 生成信号时应用偏移：effective_confidence = raw_confidence + global_conf_bias
        signal = profile.generate_signal(
            confidence_bias=global_conf_bias,
            max_lot_factor=lot_adj
        )
        process_signal(signal)
  
    # 5. 到点触发特殊事件
    next_event = timegate.get_next_boundary_event()
    sleep_seconds = min(60, next_event['seconds_to'])
    time.sleep(sleep_seconds)
```

---

## 八、测试清单

### ✅ 单元测试用例

| #   | 测试场景             | 输入时间               | 预期输出                                            |
| --- | -------------------- | ---------------------- | --------------------------------------------------- |
| T01 | 深夜时段             | 03:00 SGT              | deep_sleep, is_trading_open=False                   |
| T02 | 亚洲盘开始           | 09:00 SGT              | asian_morning, allowed=["P3"]                       |
| T03 | 亚洲停战铃后         | 14:40 SGT              | asian_morning, 但next_event提示ASIAN_STOP_NEW已触发 |
| T04 | 欧洲开盘后（冬令时） | 15:00 SGT              | european_open, allowed=["P2","P4"]                  |
| T05 | 欧美重叠（冬令时）   | 21:00 SGT              | us_ovlp, allowed=["P1","P2","P4"], bias=-5          |
| T06 | 夏令时欧洲开盘       | 2026-06-01 14:30 SGT   | european_open（提前至14:00）                        |
| T07 | 英国假日降级         | 英国银行假日 16:00 SGT | european_open但rule=uk_degrade, bias=+10, lot=0.3   |
| T08 | 跨午夜判定           | 23:59 vs 00:01         | 23:59=us_ovlp, 00:01=deep_sleep                     |

### ✅ 集成测试重点

- 夏令时切换日无跳变/重复/遗漏
- OANDA休市状态与本地日历不一致时以谁为准（已设计：OANDA优先、日志警告）
- 08:55 / 14:30 / 14:50 边界事件准确触发，不漂移
- 配置文件格式错误 → 优雅降级到默认时段+ERROR日志，不崩溃

---

## 📌 下一步：Phase 0 交付物

完成这份细化后，Phase 0 产出物清单：

- ✅ `timegate.py` — TimeGate 完整实现
- ✅ `config_session.json` — 时段配置
- ✅ `config_calendar.json` — 夏令时+假日日历
- ✅ `test_timegate.py` — 单元测试套件
- ✅ 主程序接入示例代码片段

确认方向没问题，我就把这些整理成完整可直接复制的代码包，你直接保存到项目里就能跑！要不要继续细化 Phase 1 — P3亚洲独立运行 + 跨时段核验器的设计文档？

---
