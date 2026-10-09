"""
patch_log_enhance.py — 为 signal_log 补充 direction + location 两列
✅ 只读增强 · 不改变主逻辑 · 不破坏现有文件
使用：在日志写入处导入并调用 enhance_log_row()
"""

from typing import Dict, Any, Optional
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def enhance_log_row(
    row: Dict[str, Any],
    signal_obj: Optional[Any] = None,
    strategy_engine: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    给待写入日志行补充 direction / location 字段
    优先级：直接传入值 → Signal 对象 → 从现有字段推导
    """
    enhanced = row.copy()

    # ── 1. Direction 方向 ──────────────────────────────────
    if "direction" not in enhanced or not enhanced["direction"]:
        dir_val = None

        # 从 Signal 对象
        if signal_obj:
            dir_val = getattr(signal_obj, "direction", getattr(signal_obj, "action", None))
            if dir_val:
                dir_val = str(dir_val).replace("Direction.", "").upper()
                if "LONG" in dir_val or "BUY" in dir_val:
                    dir_val = "BUY"
                elif "SHORT" in dir_val or "SELL" in dir_val:
                    dir_val = "SELL"

        # 从现有 action 列推导
        if not dir_val and "action" in enhanced:
            a = str(enhanced["action"]).upper()
            if "BUY" in a or "LONG" in a:
                dir_val = "BUY"
            elif "SELL" in a or "SHORT" in a:
                dir_val = "SELL"

        enhanced["direction"] = dir_val or ""

    # ── 2. Location 位置/支撑阻力 ──────────────────────────
    if "location" not in enhanced or not enhanced["location"]:
        loc_val = None

        # 从 Signal.pivot_levels 推导
        if signal_obj:
            pivot = getattr(signal_obj, "pivot_levels", None)
            if pivot and isinstance(pivot, dict):
                # 价格相对 pivot 判断
                mid_price = getattr(signal_obj, "mid_price", getattr(signal_obj, "price", None))
                pivot_val = pivot.get("pivot") or pivot.get("mid")
                if mid_price and pivot_val:
                    try:
                        mp = float(mid_price)
                        pv = float(pivot_val)
                        if mp > pv * 1.001:
                            loc_val = "ABOVE"
                        elif mp < pv * 0.999:
                            loc_val = "BELOW"
                        else:
                            loc_val = "AT"
                    except (TypeError, ValueError):
                        pass

        # 从 StrategyEngine 或其他缓存读取
        if not loc_val and strategy_engine:
            loc_val = getattr(strategy_engine, "_last_location_state", None) or \
                      getattr(strategy_engine, "location", None)

        enhanced["location"] = loc_val or ""

    return enhanced


def enhance_csv_header(file_path: str) -> bool:
    """
    给已有 CSV 文件补列（仅首次执行），安全不破坏数据
    返回 True=已更新 False=无需更新
    """
    from pathlib import Path
    import csv

    fpath = Path(file_path)
    if not fpath.exists():
        return False

    with open(fpath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return False
        fields = list(reader.fieldnames)
        if "direction" in fields and "location" in fields:
            return False  # 已补过

        # 补列
        rows = list(reader)

    fields += [c for c in ["direction", "location"] if c not in fields]

    with open(fpath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ 增强日志表头: {fpath.name} → +direction +location")
    return True


if __name__ == "__main__":
    print("✅ patch_log_enhance 就绪")
    print("""
使用方式（二选一）：

A. 直接在写入处调用
---
from attribution_v2.patch_log_enhance import enhance_log_row

row = { ... }  # 你现有的日志行
row = enhance_log_row(row, signal_obj=signal)
writer.writerow(row)

B. 批量补已有文件（先备份！）
---
enhance_csv_header("daily_results_profile1/2026-10-09_signal_log.csv")
""")
