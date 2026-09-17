
每套策略核心调参说明
🔹 profile_baseline｜基准对照
原始参数，不松不紧
用途：回测基准、新旧对比
开单频率：中等
MIN_CONVICTION_SCORE=20, EDGE=0.50, 最多6仓/每次2单

🔹 profile_conservative｜保守稳健
入场门槛抬高：MIN_CONVICTION_SCORE=30、EDGE=0.65
强制强动量：REQUIRE_STRONG_MOMENTUM=true
持仓减半、单次只开1单、品种池缩小至前2、排除CAD/NZD
止盈止损更紧、持仓周期缩短
开单频率：低、信号质量高、交易少

🔹 profile_balanced｜平衡推荐 ✅
修复版，能正常开单且不过度
MIN_CONVICTION_SCORE=23、EDGE=0.55、共识仅需1票、不强制动量
兼顾频率与确定性
开单频率：正常、实盘首选

🔹 profile_aggressive｜进取活跃
全面放宽：MIN_SCORE=16、EDGE=0.40
置信度门槛压低至0.48/51%、共识1票即可、ADX权重降低
持仓上限放大、单次可开3单、品种池扩大至前5
止盈空间更大、止损容忍度更高
开单频率：高、机会多、风险更高
