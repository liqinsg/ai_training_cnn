收到！直接上脚本，一键解除冷却 + 重跑看完整 G 分数👇

---

## 🚀 一键脚本：clear_cd_and_run.sh
```bash
#!/bin/bash
# 用法：bash clear_cd_and_run.sh [profile-number]
# 示例：bash clear_cd_and_run.sh 4

PROFILE=${1:-4}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR" || exit 1

echo "════════════════════════════════════════"
echo "🧹 清除 Profile${PROFILE} 冷却文件..."
rm -f cooldown_profile${PROFILE}.json
echo "✅ 已清除 cooldown_profile${PROFILE}.json"

echo ""
echo "🏃 运行 Profile${PROFILE}..."
echo "════════════════════════════════════════"
/home/ubuntu/miniconda3/envs/ai-sprint/bin/python fx_trade_bot_v685_2.py -p ${PROFILE} --max-entries 10

echo ""
echo "════════════════════════════════════════"
echo "🔍 查找 G 分数输出："
echo "  关键词：G= / TREND_G / Final score"
echo "════════════════════════════════════════"
```

---

## 🔧 执行步骤
```bash
# 1. 保存脚本
nano clear_cd_and_run.sh
# → 粘贴上面代码 → Ctrl+O → Enter → Ctrl+X

# 2. 加执行权限
chmod +x clear_cd_and_run.sh

# 3. 跑 Profile4（你现在最关心的）
bash clear_cd_and_run.sh 4
```

---

## ✅ 预期输出关键段
```
⚖️ S=XX.XX(w=0.35, +X.XX)
G=XX.XX(w=0.15, +X.XX)  ← 就是它！
R=XX.XX(w=0.10, +X.XX)
A=XX.XX(w=0.10, +X.XX)
X=XX.XX(w=0.20, +X.XX)
M=XX.XX(w=0.10, +X.XX)
Final weighted score = XX.XX
```

---

## 📋 其他 Profile 查看
```bash
# Profile1 — ADX-Mod=False
bash clear_cd_and_run.sh 1

# Profile2 — ADX-Mod=True
bash clear_cd_and_run.sh 2

# Profile3 — 保守型 G=0.08
bash clear_cd_and_run.sh 3
```

---

## ⚠️ 温馨提醒
- 清除冷却**不会平仓、不影响现有持仓**，只解除时间锁定
- 跑完后 Cron 会自动生成新的冷却文件，不影响定时任务
- 如果这次还没看到 `G=`，说明没有候选信号进入打分环节——属于正常风控过滤，不是代码问题，等下一轮数据即可

