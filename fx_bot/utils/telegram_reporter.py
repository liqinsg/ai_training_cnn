from core.config.settings import Settings
class TelegramReporter:
    def __init__(self, settings: Settings):
        self.settings = settings
    def __repr__(self):
        return "TelegramReporter(ready=True)"
