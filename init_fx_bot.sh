#!/usr/bin/env bash
set -e

BOT_DIR="./fx_bot"

echo "=== 🟢 开始完善 fx_bot 独立架构 ==="
echo "⚠️  注意：本脚本只修改 ./fx_bot/ 内部文件"
echo "    上级目录/老代码 完全不碰、不引用、不修改"
echo "========================================"

# 1. 确保所有目录存在
mkdir -p "$BOT_DIR"/{core/config,execution,monte_carlo,risk,utils,tests}

# 2. 统一创建 __init__.py（防止遗漏）
touch "$BOT_DIR"/core/__init__.py
touch "$BOT_DIR"/core/config/__init__.py
touch "$BOT_DIR"/execution/__init__.py
touch "$BOT_DIR"/monte_carlo/__init__.py
touch "$BOT_DIR"/risk/__init__.py
touch "$BOT_DIR"/utils/__init__.py
touch "$BOT_DIR"/tests/__init__.py

# 3. 创建 core/config/settings.py（独立配置，不依赖外部）
cat > "$BOT_DIR/core/config/settings.py" << 'EOF'
"""
全局配置 —— fx_bot 独立自用
从环境变量读取，不依赖上级目录任何文件
"""
import os
from dataclasses import dataclass

@dataclass
class Settings:
    # OANDA API
    OANDA_API_KEY: str = os.getenv("OANDA_API_KEY", "")
    OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")
    OANDA_ENV: str = os.getenv("OANDA_ENV", "practice")  # practice / live

    # 风控参数
    RISK_LIMIT_PCT: float = 0.02
    STOP_LOSS_DEFAULT_PIPS: int = 30

    # 蒙特卡洛模拟参数
    MC_SIMULATION_COUNT: int = 1000
EOF

# 4. 创建 core/config/constants.py
cat > "$BOT_DIR/core/config/constants.py" << 'EOF'
"""
常量 —— 全局固定参数
"""
# 交易相关
DEFAULT_PAIR = "USD_JPY"
GRANULARITY = "H1"

# 风控
RISK_LIMIT_PCT = 0.02
MAX_POSITION_UNITS = 1000

# 日志
LOG_LEVEL = "INFO"
EOF

# 5. 创建全新独立 main.py（只内部导入，绝不向上伸手）
cat > "$BOT_DIR/main.py" << 'EOF'
"""
FX Bot 新架构入口 —— 完全独立、自给自足
仅从 fx_bot 内部导入，不引用上级目录任何代码
老代码留在外部继续运行，互不干涉
"""
from core.config.settings import Settings

# 预留模块接入位置 —— 复制业务代码后取消注释
# from execution.oanda_client import OandaClient
# from execution.order_manager import OrderManager
# from monte_carlo.simulator import MonteCarloSimulator
# from risk.calculator import RiskCalculator
# from utils.market_guard import MarketGuard
# from utils.telegram_reporter import TelegramReporter


def main():
    settings = Settings()

    # 模块接入示例 —— 复制代码后取消注释
    # oanda = OandaClient(settings)
    # order_mgr = OrderManager(settings, oanda)
    # simulator = MonteCarloSimulator(settings)
    # risk_calc = RiskCalculator(settings)

    print("✅ FX Bot 独立架构启动成功！")
    print(f"   配置环境: {settings.OANDA_ENV}")
    print("   全部内部导入 ✅ 不依赖上级 ✅ 不碰老代码 ✅")


if __name__ == "__main__":
    main()
EOF

# 6. 创建模块占位文件（防止导入报错，复制代码时直接覆盖）
for f in execution/oanda_client.py execution/order_manager.py \
         monte_carlo/simulator.py risk/calculator.py \
         utils/market_guard.py utils/telegram_reporter.py; do
    [ ! -f "$BOT_DIR/$f" ] && cat > "$BOT_DIR/$f" << EOF
"""
TODO: 复制老代码内容至此文件
路径: $f
导入写法: from core.config.settings import Settings
"""
EOF
done

# 7. 验证
echo ""
echo "=== ✅ 文件生成完成 ==="
echo ""
tree "$BOT_DIR" --noreport 2>/dev/null || ls -la "$BOT_DIR"

echo ""
echo "=== 🧪 验证独立导入 ==="
cd "$BOT_DIR"
python3 -c "from main import main; main()"

echo ""
echo "=== ✅ 全部就绪 ==="
echo "下一步：复制老代码内容到各 .py 文件，import 统一写：from core.config.settings import Settings"
