
收到！🚀 咱们继续推进，下面把 **Phase 1 — P3 亚洲盘独立运行 + 跨时段核验机制** 完整细化，同样设计文档 + 配置 + 伪代码，你直接发给 TRAE 就能实现。

---

# 🌏 Phase 1 — P3亚洲独立运行 + 跨时段核验器

**依赖**: Phase 0 TimeGate ✅ | **目标**: 亚洲盘仅P3运行+专属风控；欧洲开盘前自动核验持仓、防暴击
**状态**: 就绪·可开发

---

## 📑 目录

1. [设计目标与边界](#一设计目标与边界)
2. [P3亚洲盘专属参数体系](#二p3亚洲盘专属参数体系)
3. [停战与隔夜清理规则](#三停战与隔夜清理规则)
4. [跨时段核验 SessionAudit](#四跨时段核验-sessionaudit)
5. [配置文件](#五配置文件)
6. [接口与伪代码](#六接口与伪代码)
7. [测试清单](#七测试清单)

---

## 一、设计目标与边界

### ✅ Phase 1 要解决的核心问题

- 亚洲盘噪音大、假趋势多 → **P3高置信+轻仓+宽SL紧TP，减少被频繁扫损**
- 14:30后离欧洲开盘太近 → **停止新开，不临时加仓赌方向**
- 亚洲持仓遇欧洲开盘反转 → **提前预警+主动离场建议，不等SL被打爆**
- 凌晨遗留隔夜单 → **08:55自动扫描，低置信/反向单优先离场**

### ❌ Phase 1 不做

- 不修改P3原有信号生成逻辑 → 只改入场门槛/风控参数/时间开关
- 不自动强平 → 只输出建议+标记，主程序决定是否执行（安全第一）
- 不涉及Profile投票协同 → Phase 3 再做

---

## 二、P3亚洲盘专属参数体系

### 2.1 参数叠加规则

> P3有**两套参数模板**，TimeGate时段切换时自动注入，不写死进P3核心逻辑

| 参数项       | P3默认(欧洲盘参考) | 🌏 亚洲盘模板          | 调整目的                |
| ------------ | ------------------ | ---------------------- | ----------------------- |
| 最低置信门槛 | 55.0               | **65.0** (+10)   | 宁缺毋滥，过滤弱信号    |
| SL 倍数      | ×1.0              | **×1.3** (+30%) | 亚洲盘波动杂，紧SL=送钱 |
| TP 倍数      | ×1.0              | **×0.8** (-20%) | 不指望大行情，见好就收  |
| 单笔最大单位 | 4                  | **2** (减半)     | 轻仓试错，错了不伤筋骨  |
| 单日最大新开 | 无限制             | **2对/日**       | 控制试错总次数          |
| 最大持仓对数 | 6                  | **2对**          | 不分散，专注高质量机会  |

### 2.2 参数注入方式

```
TimeGate.get_current_mask() 
  → 返回 confidence_bias + lot_multiplier + session_id
  → 主程序根据 session_id 加载对应 P3 参数模板
  → 生成信号时传入覆盖值，P3内部不硬编码时段逻辑
```

---

## 三、停战与隔夜清理规则

### 3.1 ASIAN_STOP_NEW — 14:30 停战铃

- **触发时间**: 每日 14:30 SGT
- **规则**: P3 停止所有**新开单逻辑**；已持仓不受影响、正常止损止盈、可手动/系统建议离场
- **日志标记**: `[ASIAN_STOP_NEW] 14:30已触发 — P3不再新开，现有持仓继续管理`
- **恢复**: 次日 09:00 自动解除

### 3.2 OVERNIGHT_CLEAR — 08:55 隔夜清理

- **触发时间**: 每日 08:55 SGT
- **扫描对象**: 当前所有持仓
- **判定规则**:

| 持仓状态                         | 建议动作               | 理由                           |
| -------------------------------- | ---------------------- | ------------------------------ |
| 亚洲时段入场 + 置信 < 55         | ⚠️ 保本/小亏离场     | 隔夜后强度衰减，重新评估更安全 |
| 非预期时段入场(00:00–09:00)     | 🔴 标记违规 + 优先平仓 | 违反深休市不新开规则，优先清理 |
| 浮盈 ≥ 5pips + 亚洲入场         | ✅ 提保护止损到入场价  | 锁住本金，隔夜不怕跳空         |
| 浮亏 > 1×平均ATR + 无新信号确认 | ⚠️ 考虑减仓50%       | 亏损扩大中，欧洲开盘前降风险   |

- **输出**: 清单 `[{pair, direction, entry_time, reason, suggestion}]` → 主程序日志/通知，不自动执行

---

## 四、跨时段核验 SessionAudit — 欧洲开盘防暴击核心

### 4.1 设计思想

> 亚洲盘 ≠ 欧洲盘的铺垫。**欧洲主力进场前，用欧洲时段策略(P2/P4)重新评估亚洲持仓方向是否成立**

### 4.2 触发时间点

| 事件             | 时间  | 说明                                           |
| ---------------- | ----- | ---------------------------------------------- |
| `FIRST_SCAN`   | 14:50 | 预核验：提前10分钟看方向是否冲突，留足决策时间 |
| `CONFIRM_SCAN` | 15:00 | 欧洲开盘瞬间最终核验：确认方向/强度            |

### 4.3 核验判定矩阵（核心逻辑）

```
输入:
  ├─ 亚洲持仓:  [A] 方向 + 入场置信 + 当前强度
  ├─ P2信号:    [B] 方向 + 置信
  ├─ P4信号:    [C] 方向 + 置信
  └─ 强度差:     D = abs(强度多头 - 强度空头)
```

| 场景          | A vs B/C          | 强度差D        | 置信条件          | 核验结论                   | 建议动作                                   |
| ------------- | ----------------- | -------------- | ----------------- | -------------------------- | ------------------------------------------ |
| ✅ 同向确认   | A == B == C       | D ≥ 1.5       | B≥45且C≥40      | 方向一致，趋势增强         | 保留；可考虑轻仓加码                       |
| ⚠️ 强度衰减 | A == B/C          | 0.8 ≤ D < 1.5 | 任一置信下降>10点 | 方向一致但动力减弱         | 保本上移止损，不新开                       |
| 🔴 方向冲突   | A != B 或 A != C  | D ≥ 2.0       | B≥50或C≥45      | 反向信号明确，欧洲资金不认 | **主动离场：小亏3–5p ≫ 被暴击30p** |
| ⚪ 信号缺失   | B/C 中性/置信不足 | —             | B/C 均<40         | 方向不明，欧洲资金未入场   | 观望，15:15二次核验再定                    |

### 4.4 输出示例

```
[SESSION_AUDIT 14:50] EUR_USD  SELL(亚洲P3 @14:15)
  P2=BUY(52)  P4=BUY(48)  强度差=2.3
  🔴 方向冲突：亚洲SELL vs 欧洲BUY信号明确
  建议: 主动离场  预估损失: -4.2p  避免潜在暴击: -25~35p
```

---

## 五、配置文件

### 5.1 新增: `config/config_p3_asian.json`

```json
{
  "$schema_version": "1.0",
  "description": "P3 亚洲盘专属参数模板",
  
  "session_rules": {
    "asian_morning": {
      "enabled": true,
      "min_confidence": 65.0,
      "sl_multiplier": 1.3,
      "tp_multiplier": 0.8,
      "max_lot_per_order": 2,
      "max_new_per_day": 2,
      "max_pairs_held": 2
    },
    "default": {
      "min_confidence": 55.0,
      "sl_multiplier": 1.0,
      "tp_multiplier": 1.0,
      "max_lot_per_order": 4,
      "max_new_per_day": null,
      "max_pairs_held": 6
    }
  },

  "boundary_rules": {
    "ASIAN_STOP_NEW": {
      "trigger_time": "14:30",
      "action": "stop_new_only",
      "note": "停止新开，保留持仓"
    },
    "OVERNIGHT_CLEAR": {
      "trigger_time": "08:55",
      "scan_conditions": {
        "min_confidence_to_keep": 55.0,
        "forbidden_entry_window": "00:00-09:00",
        "trailing_stop_activate_pips": 5.0,
        "reduce_loss_threshold_atr": 1.0
      },
      "action": "log_suggestion_only",
      "note": "仅输出建议，不自动强平"
    },
    "BEFORE_EUROPE_AUDIT": {
      "first_scan": "14:50",
      "confirm_scan": "15:00",
      "strength_conflict_threshold": 2.0,
      "strength_weak_threshold": 1.5,
      "confidence_drop_warning": 10.0,
      "action": "log_suggestion_only",
      "note": "仅输出建议，主程序决定执行"
    }
  }
}
```

---

## 六、接口与伪代码

### 6.1 SessionAudit 模块设计

```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
import json

@dataclass
class PositionInfo:
    pair: str
    direction: str  # 'BUY' or 'SELL'
    entry_time: datetime
    entry_price: float
    current_confidence: float
    current_strength: float
    floating_pips: float

@dataclass
class AuditResult:
    pair: str
    conclusion: str        # 'CONFIRM_KEEP' / 'WEAKENED_WATCH' / 'CONFLICT_EXIT' / 'UNCERTAIN_WAIT'
    conclusion_code: str
    suggestion: str        # 可读建议
    urgency: str          # 'LOW' / 'MEDIUM' / 'HIGH' — 冲突明确=HIGH
    reason_detail: Dict    # 详细依据
    audit_time: datetime

class SessionAuditor:
    """跨时段核验器 — 亚洲持仓 vs 欧洲开盘信号"""
  
    def __init__(self, config_path: str = "config/config_p3_asian.json"):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.tz = __import__('zoneinfo').ZoneInfo("Asia/Singapore")
  
    # ========== 主入口方法 ==========
    def audit_position(
        self,
        position: PositionInfo,
        p2_signal: Optional[Dict] = None,
        p4_signal: Optional[Dict] = None,
        current_strength: Dict = None
    ) -> AuditResult:
        """
        对单个亚洲持仓执行完整核验
        p2_signal = {'direction': 'BUY', 'confidence': 52.3}
        p4_signal = {'direction': 'NEUTRAL', 'confidence': None}
        strength = {'bull': 3.2, 'bear': 1.1, 'diff': 2.1}
        """
        # Step 1: 提取数据
        a_dir = position.direction
        a_conf = position.current_confidence
        b_dir = p2_signal.get('direction', 'NEUTRAL') if p2_signal else 'NEUTRAL'
        b_conf = p2_signal.get('confidence', 0.0) if p2_signal else 0.0
        c_dir = p4_signal.get('direction', 'NEUTRAL') if p4_signal else 'NEUTRAL'
        c_conf = p4_signal.get('confidence', 0.0) if p4_signal else 0.0
        d = abs(current_strength.get('bull', 0) - current_strength.get('bear', 0)) if current_strength else 0
      
        # Step 2: 判定逻辑
        return self._evaluate(a_dir, a_conf, b_dir, b_conf, c_dir, c_conf, d)
  
    def audit_all_positions(
        self,
        positions: List[PositionInfo],
        p2_signals: Dict[str, Dict],
        p4_signals: Dict[str, Dict],
        strength_matrix: Dict[str, Dict]
    ) -> List[AuditResult]:
        """批量核验 — 欧洲开盘前全量扫描"""
        results = []
        for pos in positions:
            pair = pos.pair
            p2 = p2_signals.get(pair)
            p4 = p4_signals.get(pair)
            st = strength_matrix.get(pair)
            results.append(self.audit_position(pos, p2, p4, st))
        return results
  
    def scan_overnight_positions(
        self,
        all_positions: List[PositionInfo],
        current_time: datetime = None
    ) -> List[Dict]:
        """08:55 隔夜清理扫描"""
        if current_time is None:
            current_time = datetime.now(self.tz)
      
        alerts = []
        rule = self.config['boundary_rules']['OVERNIGHT_CLEAR']['scan_conditions']
      
        for pos in all_positions:
            entry_hhmm = pos.entry_time.strftime("%H:%M")
            is_forbidden = self._time_in_forbidden_window(entry_hhmm)
            low_conf = pos.current_confidence < rule['min_confidence_to_keep']
            new_enough = (current_time - pos.entry_time).total_seconds() < 86400  # 1天内
          
            if is_forbidden:
                alerts.append({
                    'pair': pos.pair,
                    'type': 'FORBIDDEN_ENTRY',
                    'severity': 'HIGH',
                    'suggestion': '优先平仓：00:00-09:00违规开仓'
                })
            elif low_conf and new_enough and pos.floating_pips <= 0:
                alerts.append({
                    'pair': pos.pair,
                    'type': 'CONFIDENCE_DECAY',
                    'severity': 'MEDIUM',
                    'suggestion': '考虑保本离场：置信跌破阈值且无浮盈保护'
                })
            elif pos.floating_pips >= rule['trailing_stop_activate_pips']:
                alerts.append({
                    'pair': pos.pair,
                    'type': 'PROFIT_PROTECT',
                    'severity': 'INFO',
                    'suggestion': f'上移止损至入场价，保护{pos.floating_pips:.1f}p浮盈'
                })
      
        return alerts
  
    # ========== 内部判定逻辑 ==========
    def _evaluate(self, a_dir, a_conf, b_dir, b_conf, c_dir, c_conf, strength_diff) -> AuditResult:
        """核心判定矩阵 — 对照4类场景"""
        thresholds = self.config['boundary_rules']['BEFORE_EUROPE_AUDIT']
        conflict_th = thresholds['strength_conflict_threshold']
        weak_th = thresholds['strength_weak_threshold']
      
        # 🔴 场景1: 明确冲突
        if (b_dir != 'NEUTRAL' and b_dir != a_dir and b_conf >= 45) or \
           (c_dir != 'NEUTRAL' and c_dir != a_dir and c_conf >= 40):
            if strength_diff >= conflict_th:
                return AuditResult(
                    pair='', conclusion='CONFLICT_EXIT', conclusion_code='E1',
                    suggestion='主动离场：欧洲盘方向明确相反，避免开盘跳空暴击',
                    urgency='HIGH', reason_detail={}, audit_time=datetime.now()
                )
      
        # ✅ 场景2: 一致确认
        if (b_dir == a_dir and b_conf >= 45) or (c_dir == a_dir and c_conf >= 40):
            if strength_diff >= weak_th:
                return AuditResult(
                    pair='', conclusion='CONFIRM_KEEP', conclusion_code='K1',
                    suggestion='继续持有：欧洲方向确认一致',
                    urgency='LOW', reason_detail={}, audit_time=datetime.now()
                )
      
        # ⚠️ 场景3: 一致但强度衰减
        if (b_dir == a_dir or c_dir == a_dir) and (weak_th <= strength_diff < conflict_th):
            return AuditResult(
                pair='', conclusion='WEAKENED_WATCH', conclusion_code='W1',
                suggestion='上移保本止损：方向一致但强度减弱，保护本金',
                urgency='MEDIUM', reason_detail={}, audit_time=datetime.now()
            )
      
        # ⚪ 场景4: 信号不明
        return AuditResult(
            pair='', conclusion='UNCERTAIN_WAIT', conclusion_code='U1',
            suggestion='观望：欧洲信号不足，15:15二次核验再决定',
            urgency='LOW', reason_detail={}, audit_time=datetime.now()
        )
```

### 6.2 主程序接入示例

```python
# === Phase 1 主循环集成 ===

from session_audit import SessionAuditor
from timegate import TimeGate

# 初始化
timegate = TimeGate(...)
auditor = SessionAuditor("config/config_p3_asian.json")
p3_asian_params = load_json("config/config_p3_asian.json")['session_rules']

# 全局状态跟踪
asian_new_stop = False  # 14:30停战铃标记

while True:
    mask = timegate.get_current_mask()
    now = datetime.now(timegate.tz)
    hhmm = now.strftime("%H:%M")

    # ---- Step 1: 时段参数切换 ----
    session_id = mask.session_id
    p3_params = p3_asian_params.get(session_id, p3_asian_params['default'])
  
    # ---- Step 2: 停战铃逻辑 ----
    if hhmm >= "14:30" and hhmm < "15:00":
        if not asian_new_stop:
            logger.info("🔔 ASIAN_STOP_NEW 已激活 — P3停止新开")
            asian_new_stop = True
        allow_p3_new = False
    else:
        asian_new_stop = False
        allow_p3_new = True

    # ---- Step 3: 隔夜清理 08:55 ----
    if hhmm == "08:55":
        positions = get_current_positions()
        alerts = auditor.scan_overnight_positions(positions, now)
        for alert in alerts:
            logger.info(f"🌙 隔夜提醒 [{alert['severity']}] {alert['pair']}: {alert['suggestion']}")
            send_notification_if_enabled(alert)

    # ---- Step 4: 欧洲开盘预核验 14:50 / 15:00 ----
    if hhmm in ["14:50", "15:00"]:
        logger.info(f"\n🔍 {hhmm} 欧洲开盘跨时段核验开始")
        asian_positions = get_positions_by_profile("P3")
        if asian_positions:
            p2_signals = get_latest_signals("P2")
            p4_signals = get_latest_signals("P4")
            strength_matrix = get_current_strength_all()
          
            audit_results = auditor.audit_all_positions(
                asian_positions, p2_signals, p4_signals, strength_matrix
            )
          
            for res in audit_results:
                log_msg = f"   {res.pair} | {res.conclusion} | {res.suggestion}"
                if res.urgency == 'HIGH':
                    logger.warning(f"🔴 {log_msg}")
                    send_alert_if_enabled(log_msg)  # 可配置是否推送
                else:
                    logger.info(f"   {log_msg}")

    # ---- Step 5: 正常信号生成 ----
    if not mask.is_trading_open:
        time.sleep(60)
        continue
  
    # P3 时段+停战双重控制
    if "P3" in mask.allowed_profiles and allow_p3_new:
        signal = generate_p3_signal(
            min_confidence=p3_params['min_confidence'],
            sl_multiplier=p3_params['sl_multiplier'],
            tp_multiplier=p3_params['tp_multiplier'],
            max_lot=p3_params['max_lot_per_order']
        )
        if signal and signal.confidence >= p3_params['min_confidence']:
            check_and_submit_order(signal)

    time.sleep(30)
```

---

## 七、测试清单

### ✅ P3参数切换

| #   | 场景               | 预期                               |
| --- | ------------------ | ---------------------------------- |
| P01 | 亚洲盘09:00        | P3置信门槛65、SL×1.3、TP×0.8生效 |
| P02 | 欧洲盘15:00后      | P3恢复默认参数55/1.0/1.0           |
| P03 | 单日新开超限(>2对) | 第3对被拒绝，日志提示超限          |

### ✅ 停战铃

| #   | 场景          | 预期                                     |
| --- | ------------- | ---------------------------------------- |
| S01 | 14:29         | P3可正常新开                             |
| S02 | 14:31         | P3仅持仓管理，新开请求被拦截+日志        |
| S03 | 15:00后欧洲盘 | P3停战自动解除（但此时段已不在允许列表） |

### ✅ 隔夜清理 08:55

| #   | 场景                     | 预期                          |
| --- | ------------------------ | ----------------------------- |
| O01 | 03:00违规开仓            | 08:55扫描→HIGH告警：优先平仓 |
| O02 | 亚洲入场+置信50+浮亏     | MEDIUM：保本离场建议          |
| O03 | 亚洲入场+浮盈6p+置信正常 | INFO：上移止损至入场价        |

### ✅ 跨时段核验

| #   | 场景                                    | 预期结论                      |
| --- | --------------------------------------- | ----------------------------- |
| A01 | P3 SELL, P2 BUY(52), P4 BUY(48), D=2.3  | 🔴 CONFLICT_EXIT 离场建议     |
| A02 | P3 BUY, P2 BUY(55), P4 BUY(50), D=1.8   | ✅ CONFIRM_KEEP 继续持有      |
| A03 | P3 SELL, P2 SELL(46), P4 NEUTRAL, D=1.2 | ⚠️ WEAKENED_WATCH 保本上移  |
| A04 | P3 BUY, P2 NEUTRAL, P4 NEUTRAL          | ⚪ UNCERTAIN_WAIT 等15:15再看 |

---

## 📦 发给 TRAE 的完整 Prompt

直接复制发送即可：

```
请实现 FX Bot Phase 1：P3亚洲独立运行 + 跨时段核验机制

=== 依赖 ===
基于已完成的 TimeGate 模块继续扩展，不破坏现有结构

=== 需要生成的文件 ===
1. session_audit.py — SessionAuditor 主模块 + 数据类
2. config/config_p3_asian.json — P3亚洲盘参数 + 边界事件配置
3. test_session_audit.py — 单元测试套件
4. README_PHASE1.md — 接入说明 + 主程序集成示例

=== 核心功能要求 ===
【P3亚洲盘参数模板】
- 亚洲时段：置信≥65，SL×1.3，TP×0.8，单笔≤2单位，单日最多2对，最多持有2对
- 非亚洲时段：恢复默认 55/1.0/1.0/4/无限制/6
- 参数通过配置文件驱动，不硬编码进P3逻辑

【停战铃 ASIAN_STOP_NEW】
- 每日14:30触发：P3停止新开单，已持仓正常管理
- 次日09:00自动解除，仅标记不强制停机

【隔夜清理 OVERNIGHT_CLEAR 08:55】
- 扫描全部持仓，输出建议清单（不自动强平！只建议+日志）
- 规则：00:00-09:00入场=优先平仓；亚洲入场置信<55且浮亏=保本离场；浮盈≥5p=上移止损至入场价

【跨时段核验 SessionAudit】
- 触发：14:50首次扫描 / 15:00确认扫描
- 输入：亚洲持仓(P3) + P2信号 + P4信号 + 强度矩阵
- 判定4类：
  🔴 CONFLICT_EXIT — 方向相反+强度差≥2.0 → 主动离场建议(HIGH紧急)
  ✅ CONFIRM_KEEP — 方向一致+强度差≥1
```
