"""
mc_bundle_loader.py — 适配现有 fx_trade_bot_mc 命名规范
- D(daily): 今日 00:00 起最新
- W(h4): 本周一 00:00 起最新
- 融合逻辑：周定基准、日抓动态、自动降级
"""
import os
import re
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

# 复用现有配置
from fx_trade_bot_mc import MCConfig
cfg = MCConfig()
MC_RESULTS_DIR = cfg.RESULTS_DIR


# ─── 加载器 ───
def get_this_week_latest_w_bundle() -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """匹配 h4_YYYYMMDD_HHMM.json，取本周一以来最新"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())  # 0=周一
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)

    pattern = re.compile(r"^h4_.*?_(\d{8})_\d{4}\.json$")
    latest_file: Optional[str] = None
    latest_dt: Optional[datetime] = None

    if not os.path.isdir(MC_RESULTS_DIR):
        return None, False, f"dir_not_found: {MC_RESULTS_DIR}"

    for fname in os.listdir(MC_RESULTS_DIR):
        match = pattern.match(fname)
        if not match:
            continue
        try:
            file_dt = datetime.strptime(match.group(1), "%Y%m%d")
        except ValueError:
            continue
        if file_dt >= week_start:
            if (latest_dt is None) or (file_dt > latest_dt):
                latest_dt = file_dt
                latest_file = fname

    if not latest_file:
        return None, False, "no_this_week_h4_bundle"

    full_path = os.path.join(MC_RESULTS_DIR, latest_file)
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f), True, latest_file


def get_today_latest_d_bundle() -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """匹配 daily_YYYYMMDD_HHMM.json，仅今日、取时间戳最大"""
    today_str = datetime.now().strftime("%Y%m%d")
    pattern = re.compile(rf"^daily_.*?_{today_str}_\d{{4}}\.json$")
    latest_file: Optional[str] = None

    if not os.path.isdir(MC_RESULTS_DIR):
        return None, False, f"dir_not_found: {MC_RESULTS_DIR}"

    for fname in os.listdir(MC_RESULTS_DIR):
        if pattern.match(fname):
            if (latest_file is None) or (fname > latest_file):
                latest_file = fname

    if not latest_file:
        return None, False, "no_today_daily_bundle"

    full_path = os.path.join(MC_RESULTS_DIR, latest_file)
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f), True, latest_file


# ─── 融合核心 ───
def blend_metric(
    w_val: float,
    d_val: float,
    mode: str = "FULL",
    w_weight_base: float = 0.7,
    max_deviation_adjust: float = 0.2
) -> float:
    """
    融合公式：偏离越大 → 越信任周基准
    mode: FULL / W_ONLY / D_ONLY
    """
    if mode == "W_ONLY":
        return w_val
    if mode == "D_ONLY":
        return d_val * 0.5  # 单日信号保守折扣

    # 动态加权
    deviation = abs(d_val - w_val) / (abs(w_val) + 1e-8)
    w_weight = w_weight_base + max_deviation_adjust * min(deviation, 1.0)
    d_weight = 1.0 - w_weight
    return w_weight * w_val + d_weight * d_val


def get_run_mode(w_ok: bool, d_ok: bool) -> str:
    if w_ok and d_ok:
        return "FULL"
    if w_ok:
        return "W_ONLY"
    if d_ok:
        return "D_ONLY"
    return "NONE"


# ─── 便捷入口 ───
def load_and_blend() -> Dict[str, Any]:
    """一键加载+判定模式，主脚本直接调用"""
    w_data, w_ok, w_name = get_this_week_latest_w_bundle()
    d_data, d_ok, d_name = get_today_latest_d_bundle()
    mode = get_run_mode(w_ok, d_ok)

    return {
        "mode": mode,
        "w": {"ok": w_ok, "name": w_name, "data": w_data},
        "d": {"ok": d_ok, "name": d_name, "data": d_data},
        "blend": lambda w, d, **kw: blend_metric(w, d, mode, **kw)
    }
