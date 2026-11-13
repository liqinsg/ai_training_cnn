
按照 Phase 3 规范，**Shadow Inference（影子模式）** 是实现新 ML 系统平稳切流、绝对安全的护城河。

在实盘中，ML 模块绝不能直接参与真实下单或直接干预现有订单。相反，它必须以非阻塞的旁路身份（Sidecar / Shadow Runner）挂载到现有的 `StrategyEngine` 中：

1. **零下单权限**：影子推理的输出只记录、只对比、只报警，绝不写入 OANDA 订单生成逻辑。
2. **双轨并行（Dual-Track Comparison）**：如果旧模型（或现有策略）仍在运行，系统可以同时记录旧模型的决策与新 Feature Contract + Bundle 模型的预测结果，用于离线回测与胜率对比。
3. **断路保护（Circuit Breaker）**：如果特征计算出现 NaN 或模型 Bundle 校验失败，影子推理只记录异常并优雅降级，**绝不让 ML 异常导致整个交易循环崩溃**。

---

## 影子模式运行与日志校验架构设计 (`ml/shadow_runner.py`)

我们可以设计一个轻量、健壮的 `ShadowInferenceRunner`，直接织入实盘交易循环：

```python
# ml/shadow_runner.py — SHADOW INFERENCE RUNNER (PHASE 3)
# Executes model prediction in shadow-only mode alongside live strategy.
# Guarantees zero execution risk and structured parity logging.

import logging
import time
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


class ShadowInferenceRunner:
    """
    Executes ML inference in shadow mode: fetches live candles, builds features
    via the authoritative Feature Contract, predicts probabilities, and logs results 
    without submitting trades.
    """

    def __init__(self, model_wrapper, feature_engine, config=None):
        self.model_wrapper = model_wrapper
        self.feature_engine = feature_engine
        self.config = config or {}
        self.enabled = self.config.get("shadow_mode_enabled", True)
        self.prediction_log_path = Path(self.config.get("log_path", "logs/shadow_predictions.csv"))
        self.prediction_log_path.parent.mkdir(parents=True, exist_ok=True)

    def run_shadow_pass(self, pair: str, raw_candles: pd.DataFrame, live_strategy_signal: str = "NEUTRAL"):
        """
        Executes a single shadow inference step.
      
        Args:
            pair: Trading pair identifier (e.g., 'EUR_USD')
            raw_candles: Recent OHLCV DataFrame fetched from OANDA
            live_strategy_signal: The signal produced by the current live strategy ('BUY', 'SELL', 'NEUTRAL')
        """
        if not self.enabled:
            return

        start_time = time.time()
        prediction_record = {
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "pair": pair,
            "live_signal": live_strategy_signal,
            "ml_probability": None,
            "ml_signal": "NEUTRAL",
            "status": "SUCCESS",
            "error_message": "",
            "latency_ms": 0.0,
        }

        try:
            # 1. Apply authoritative Feature Contract
            feat_df = self.feature_engine.build(raw_candles)
            feature_cols = self.model_wrapper.feature_names
          
            # Extract the latest bar features matching model expectations
            latest_features = feat_df.iloc[-1][feature_cols].values.reshape(1, -1)
          
            # Check for NaN / Inf in features
            if pd.isna(latest_features).any() or not np.isfinite(latest_features).all():
                raise ValueError("Feature vector contains NaN or Inf values. Skipping prediction.")

            # 2. Scale features using bundle scaler
            scaled_features = self.model_wrapper.scaler.transform(latest_features)

            # 3. Model prediction
            proba = self.model_wrapper.model.predict_proba(scaled_features)[0]
            # Assuming binary classification: index 1 is 'UP' probability
            up_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])
          
            prediction_record["ml_probability"] = up_prob
          
            # Map probability to signal based on thresholds
            buy_threshold = self.config.get("buy_threshold", 0.55)
            sell_threshold = self.config.get("sell_threshold", 0.45)
          
            if up_prob >= buy_threshold:
                prediction_record["ml_signal"] = "BUY"
            elif up_prob <= sell_threshold:
                prediction_record["ml_signal"] = "SELL"
            else:
                prediction_record["ml_signal"] = "NEUTRAL"

        except Exception as e:
            prediction_record["status"] = "ERROR"
            prediction_record["error_message"] = str(e)
            logger.error(f"[SHADOW MODE] Inference failure for {pair}: {e}", exc_info=False)

        finally:
            latency = (time.time() - start_time) * 1000.0
            prediction_record["latency_ms"] = round(latency, 2)
          
            # Log structured comparison
            logger.info(
                f"[SHADOW] Pair={pair} | LiveSignal={prediction_record['live_signal']} | "
                f"MLSignal={prediction_record['ml_signal']} (Prob: {prediction_record['ml_probability']}) | "
                f"Status={prediction_record['status']} | Latency={prediction_record['latency_ms']}ms"
            )
          
            # Append record to shadow log CSV for offline validation and parity checking
            self._append_to_log(prediction_record)

    def _append_to_log(self, record: dict):
        """Append shadow prediction record to CSV file atomically."""
        try:
            df_rec = pd.DataFrame([record])
            header = not self.prediction_log_path.exists()
            df_rec.to_csv(self.prediction_log_path, mode="a", index=False, header=header)
        except Exception as log_err:
            logger.error(f"[SHADOW MODE] Failed to write prediction log: {log_err}")

```

---

## 校验与晋升标准（Shadow Validation Gate）

在影子模式运行期间，我们将通过以下指标判定新模型是否具备晋升为实盘（Live Production Promotion）的资格：

1. **数值与契约稳定性**：影子日志中 `status == "SUCCESS"` 的比例必须连续 14 个交易日达到 100%，零特征对齐异常或维度不匹配。
2. **延迟红线（Latency SLA）**：单次特征计算与推理耗时 (`latency_ms`) 必须稳定在 `< 50ms` 以内，确保绝不拖慢 OANDA 实盘轮询节拍。
3. **回测胜率对比**：离线对比 `ml_signal` 与历史行情的实际走势，确认其方向准确率显著优于旧模型或随机基准。



Shadow Inference 影子模式设计完成。接下来你可以选择：

1, 审查并确认完整的 Phase 3 架构改造路线图

2, 开始编写针对 shadow_runner 的单元测试
