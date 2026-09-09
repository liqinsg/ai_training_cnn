"""
FX Bot 新架构入口 —— 完全独立、自给自足
仅从 fx_bot 内部导入，不引用上级目录任何代码
老代码留在外部继续运行，互不干涉
"""
from core.config.settings import Settings
from execution.oanda_client import OandaClient
from execution.order_manager import OrderManager
from monte_carlo.simulator import MonteCarloSimulator
from risk.calculator import RiskCalculator
from utils.market_guard import MarketGuard
from utils.telegram_reporter import TelegramReporter


def main():
    settings = Settings()
    oanda = OandaClient(settings)
    order_mgr = OrderManager(settings, oanda)
    simulator = MonteCarloSimulator(settings)
    risk_calc = RiskCalculator(settings)
    guard = MarketGuard(settings)
    reporter = TelegramReporter(settings)
    print("✅ FX Bot 新架构启动成功！")


if __name__ == "__main__":
    main()