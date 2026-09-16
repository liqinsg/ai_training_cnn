from core.config.settings import Settings
class MonteCarloSimulator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.simulation_count = settings.MC_SIMULATION_COUNT
    def __repr__(self):
        return f"MonteCarloSimulator(count={self.simulation_count})"
