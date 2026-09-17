每套策略核心调参说明
🔹 profile_baseline｜基准对照
原始参数，不松不紧
用途：回测基准、新旧对比
开单频率：中等
🔹 profile_conservative｜保守稳健
入场门槛显著抬高：MIN_CONVICTION_SCORE=30、EDGE=0.65
强制强动量：REQUIRE_STRONG_MOMENTUM=true
持仓减半、单次只开 1 单、品种池缩小至前 2
止盈止损更紧、持仓周期缩短
开单频率：低、信号质量高、交易少
🔹 profile_balanced｜平衡推荐 ✅
修复版，能正常开单且不过度
门槛略高于基准、共识宽松、不强制动量
兼顾频率与确定性
开单频率：正常、实盘首选
🔹 profile_aggressive｜进取活跃
全面放宽：MIN_SCORE=16、EDGE=0.40
模型置信度门槛压低至 0.48/51%
共识仅需 1 票即可、ADX 权重降低
持仓上限放大、单次可开 3 单、品种池扩大
止盈空间更大、止损容忍度更高
开单频率：高、机会多、风险更高