import json
import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

# 将项目根目录加入 sys.path，以便从 tests/ 目录下导入根目录模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 假设原函数和异常类在 fx_trade_bot_ml_v1 中
from fx_trade_bot_ml_v1 import ensure_model, ModelBundleContractError


# --- Mock Classes & Helpers ---

class MockFeatureConfig:
    schema_version = "v1.0"
    retrain_every_n_days = 30
    train_lookback_bars = 200
    required_bars = 50
    target_horizon = 5
    use_macd = True


class MockModelWrapper:
    def __init__(self, n_features=3):
        self.feature_names = [f"feat_{i}" for i in range(n_features)]
        self.model = MockSklearnModel(n_features)
        self.scaler = MockSklearnScaler(n_features)
        self.fit_called = False

    def fit(self, df, feature_cols):
        self.fit_called = True
        return {"train_score": 0.95}

    def save(self):
        # 模拟保存动作，由测试用例直接写入对应文件以控制状态
        pass

    def load(self):
        pass


class MockSklearnModel:
    def __init__(self, n_features):
        self.n_features_in_ = n_features


class MockSklearnScaler:
    def __init__(self, n_features):
        self.n_features_in_ = n_features


class MockStrategyEngine:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.features = None


class MockFetcher:
    def fetch(self, pair, oanda_symbol, count):
        # 模拟返回足够的历史行情数据
        return pd.DataFrame({"close": np.linspace(100, 110, count)})


class MockFeatureEngine:
    def build(self, raw_df):
        raw_df["feat_0"] = 1.0
        raw_df["feat_1"] = 2.0
        raw_df["feat_2"] = 3.0
        return raw_df

    def build_target(self, df, horizon):
        df["target"] = 1
        return df

    def get_feature_columns(self, df):
        return ["feat_0", "feat_1", "feat_2"]


# --- Pytest Test Cases ---

def create_valid_bundle(stem: Path, schema_version="v1.0", n_features=3):
    """Helper to create a fully valid set of Model Bundle artifacts."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    stem.with_suffix(".json").write_text("{}")
    (stem.parent / "scaler.joblib").write_text("mock_scaler")
    stem.with_suffix(".features.json").write_text("[]")
    
    manifest = {
        "schema_version": schema_version,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "feature_names": [f"feat_{i}" for i in range(n_features)],
        "n_features": n_features,
    }
    stem.with_suffix(".manifest.json").write_text(json.dumps(manifest))


def test_ensure_model_triggers_training_when_artifacts_missing(tmp_path):
    model_path = tmp_path / "models" / "strategy_model.json"
    feat_cfg = MockFeatureConfig()
    model_wrapper = MockModelWrapper(n_features=3)
    strat_engine = MockStrategyEngine()
    
    # 确认文件不存在
    assert not model_path.with_suffix(".manifest.json").exists()

    res_wrapper, res_strat = ensure_model(
        MODEL_PATH=model_path,
        FEAT_CFG=feat_cfg,
        model_wrapper=model_wrapper,
        strat_engine=strat_engine,
        fetcher=MockFetcher(),
        feat_engine=MockFeatureEngine(),
        DEFAULT_PAIRS=["EUR_USD"],
        YAHOO_TO_OANDA={"EUR_USD": "EUR_USD"},
        cfg=None,
    )

    # 验证是否触发了训练
    assert model_wrapper.fit_called is True
    # 验证依赖注入是否成功
    assert res_strat.model is model_wrapper.model
    assert res_strat.scaler is model_wrapper.scaler
    assert res_strat.features == ["feat_0", "feat_1", "feat_2"]


def test_ensure_model_triggers_retrain_on_schema_mismatch(tmp_path):
    model_path = tmp_path / "models" / "strategy_model.json"
    # 创建一个 schema 版本过期的合法 Bundle
    create_valid_bundle(model_path, schema_version="v0.9")
    
    feat_cfg = MockFeatureConfig() # 期望 schema_version = "v1.0"
    model_wrapper = MockModelWrapper(n_features=3)
    strat_engine = MockStrategyEngine()

    ensure_model(
        MODEL_PATH=model_path,
        FEAT_CFG=feat_cfg,
        model_wrapper=model_wrapper,
        strat_engine=strat_engine,
        fetcher=MockFetcher(),
        feat_engine=MockFeatureEngine(),
        DEFAULT_PAIRS=["EUR_USD"],
        YAHOO_TO_OANDA={"EUR_USD": "EUR_USD"},
        cfg=None,
    )

    # 因为版本不匹配，应强制触发重新训练
    assert model_wrapper.fit_called is True


def test_ensure_model_raises_contract_error_on_dimension_mismatch(tmp_path):
    model_path = tmp_path / "models" / "strategy_model.json"
    create_valid_bundle(model_path, schema_version="v1.0", n_features=3)
    
    feat_cfg = MockFeatureConfig()
    # 制造维度不一致：模型期望 5 个特征，但特征列表给的是 3 个
    model_wrapper = MockModelWrapper(n_features=3)
    model_wrapper.model.n_features_in_ = 5 
    strat_engine = MockStrategyEngine()

    # 应该直接触发 Hard-Stop 异常，而不是静默容错
    with pytest.raises(ModelBundleContractError) as excinfo:
        ensure_model(
            MODEL_PATH=model_path,
            FEAT_CFG=feat_cfg,
            model_wrapper=model_wrapper,
            strat_engine=strat_engine,
            fetcher=MockFetcher(),
            feat_engine=MockFeatureEngine(),
            DEFAULT_PAIRS=["EUR_USD"],
            YAHOO_TO_OANDA={"EUR_USD": "EUR_USD"},
            cfg=None,
        )

    assert "Feature dimension mismatch" in str(excinfo.value)
