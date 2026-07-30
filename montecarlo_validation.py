import numpy as np
import pandas as pd

# Your historical trade results from walk-forward
trade_outcomes = [1 if r > 0 else 0 for r in res['trade_acc']]  # Or actual PnL per trade

def monte_carlo(trade_list, sims=5000):
    results = []
    for _ in range(sims):
        shuffled = np.random.choice(trade_list, size=len(trade_list), replace=True)
        equity = 1000
        for win in shuffled:
            equity *= 1.01 if win else 0.99
        results.append(equity)
    return np.array(results)

mc = monte_carlo(trade_outcomes)
print(f"📊 Monte Carlo (5000 runs):")
print(f"Median Final: ${np.median(mc):.2f}")
print(f"90% positive: {np.mean(mc>1000):.1%}")
print(f"Worst 5%: ${np.percentile(mc,5):.2f}")
