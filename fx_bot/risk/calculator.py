from core.config.settings import Settings
class RiskCalculator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.risk_limit_pct = settings.RISK_LIMIT_PCT
    def __repr__(self):
        return f"RiskCalculator(limit={self.risk_limit_pct})"
