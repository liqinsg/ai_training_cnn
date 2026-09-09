from core.config.settings import Settings
class MarketGuard:
    def __init__(self, settings: Settings):
        self.settings = settings
    def __repr__(self):
        return "MarketGuard(active=True)"
