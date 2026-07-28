import numpy as np
import matplotlib.pyplot as plt

# === 基础参数 ===
S0 = 1.0800       # 当前EUR/USD
sigma_annual = 0.085  # 年化波动率
t = 1/12          # 1个月（年）
mu = 0.00         # 漂移项，可改为±0.01~0.03
n_sim = 10000     # 模拟次数

# === 蒙特卡洛模拟 ===
np.random.seed(42)  # 固定随机种子，结果可复现
Z = np.random.normal(0, 1, n_sim)
S_T = S0 * np.exp( (mu - 0.5*sigma_annual**2)*t + sigma_annual*np.sqrt(t)*Z )

# === 关键统计 ===
prob_below = np.mean(S_T < 1.0650)
prob_above = np.mean(S_T > 1.1000)
ci_low = np.percentile(S_T, 5)
ci_high = np.percentile(S_T, 95)

print(f"均值: {S_T.mean():.4f}")
print(f"低于1.0650概率: {prob_below:.1%}")
print(f"高于1.1000概率: {prob_above:.1%}")
print(f"90%置信区间: {ci_low:.4f} ~ {ci_high:.4f}")

# === 可视化分布 ===
plt.figure(figsize=(8,4))
plt.hist(S_T, bins=50, alpha=0.7, color='#1f77b4')
plt.axvline(1.0650, color='green', linestyle='--', label='1.0650（节省成本）')
plt.axvline(1.1000, color='red', linestyle='--', label='1.1000（超预算）')
plt.title('EUR/USD 1个月后汇率分布（10000次模拟）')
plt.xlabel('汇率')
plt.ylabel('频次')
plt.legend()
plt.grid(axis='y', alpha=0.3)
plt.show()