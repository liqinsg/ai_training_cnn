"""
全局配置 — Multi-Account Profile 体系
.env 来源：统一 OANDA_API_TOKEN + 4个账号ID
命令行：--profile2 / --profile3 / --profile4
默认：无参数 = 自动 profile2
"""
import os
import sys
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ────────────────────────────────────────────────────────────────
# 🎯 Profile 解析 — 核心组装函数
# ────────────────────────────────────────────────────────────────
def resolve_profile_account_id():
    """
    解析命令行参数，返回目标账号ID
    优先级：--profile2/3/4 > 默认 profile2
    """
    args = [a.strip().lower() for a in sys.argv[1:]]

    if "--profile2" in args:
        return os.getenv("OANDA_ACCOUNT_ID_2", "")
    elif "--profile3" in args:
        return os.getenv("OANDA_ACCOUNT_ID_3", "")
    elif "--profile4" in args:
        return os.getenv("OANDA_ACCOUNT_ID_4", "")

    # ⚡ 默认 Profile2（无参数时）
    return os.getenv("OANDA_ACCOUNT_ID_2", "")


@dataclass
class Settings:
    # === OANDA 连接 — 统一用 API_TOKEN（修复权限问题） ===
    OANDA_API_TOKEN: str = os.getenv("OANDA_API_TOKEN", "")  # ✅ 与老代码完全对齐
    OANDA_API_KEY: str = OANDA_API_TOKEN  # 兼容别名，不影响
    OANDA_ACCOUNT_ID: str = resolve_profile_account_id()     # ✅ 自动解析 Profile
    OANDA_ENV: str = os.getenv("OANDA_ENV", "practice")

    # === 全部账号库（备查/切换用） ===
    OANDA_ACCOUNT_ID_1: str = os.getenv("OANDA_ACCOUNT_ID_1", "")
    OANDA_ACCOUNT_ID_2: str = os.getenv("OANDA_ACCOUNT_ID_2", "")
    OANDA_ACCOUNT_ID_3: str = os.getenv("OANDA_ACCOUNT_ID_3", "")
    OANDA_ACCOUNT_ID_4: str = os.getenv("OANDA_ACCOUNT_ID_4", "")

    # === Gemini AI ===
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # === 风控/策略参数 ===
    RISK_LIMIT_PCT: float = float(os.getenv("RISK_LIMIT_PCT", "0.02"))
    STOP_LOSS_DEFAULT_PIPS: int = int(os.getenv("STOP_LOSS_DEFAULT_PIPS", "30"))

    # === 蒙特卡洛模拟 ===
    MC_SIMULATION_COUNT: int = int(os.getenv("MC_SIMULATION_COUNT", "1000"))

    # === 当前 Profile 标识（日志/调试用） ===
    @property
    def profile_name(self) -> str:
        aid = self.OANDA_ACCOUNT_ID
        if aid == self.OANDA_ACCOUNT_ID_2:
            return "PROFILE-2 (Default)"
        elif aid == self.OANDA_ACCOUNT_ID_3:
            return "PROFILE-3"
        elif aid == self.OANDA_ACCOUNT_ID_4:
            return "PROFILE-4"
        return "CUSTOM"


# ────────────────────────────────────────────────────────────────
# 🔍 自检：直接运行 python core/config/settings.py
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    s = Settings()
    print("=" * 60)
    print("🔍 FX Bot 配置自检")
    print("=" * 60)
    print(f"📌 Profile     : {s.profile_name}")
    print(f"🔑 API Token  : {'✅ OK' if s.OANDA_API_TOKEN else '❌ MISSING'} ({len(s.OANDA_API_TOKEN)} chars)")
    print(f"🏦 Account ID : {s.OANDA_ACCOUNT_ID}")
    print(f"🌍 Environment: {s.OANDA_ENV}")
    print("-" * 60)
    print(f"ACCOUNT_1: {s.OANDA_ACCOUNT_ID_1 or '—'}")
    print(f"ACCOUNT_2: {s.OANDA_ACCOUNT_ID_2 or '—'}")
    print(f"ACCOUNT_3: {s.OANDA_ACCOUNT_ID_3 or '—'}")
    print(f"ACCOUNT_4: {s.OANDA_ACCOUNT_ID_4 or '—'}")
    print("=" * 60)