"""
test_runner.py — Validate ProfileAttribution & run_all_profiles
(ai-sprint) qili@NBK202500000057 ~/projects/ai_training_cnn/attribution_v2 (v2026)$ python -m pytest tests/test_runner.py -v
=================================================== test session starts ====================================================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /home/qili/miniconda3/envs/ai-sprint/bin/python
cachedir: .pytest_cache
rootdir: /home/qili/projects/ai_training_cnn/attribution_v2
plugins: asyncio-1.4.0, anyio-4.12.1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/test_runner.py::test_runner_instantiation PASSED                                                               [ 10%]
tests/test_runner.py::test_unknown_profile_raises PASSED                                                             [ 20%]
tests/test_runner.py::test_pfa_full_pass PASSED                                                                      [ 30%]
tests/test_runner.py::test_probability_centering PASSED                                                              [ 40%]
tests/test_runner.py::test_sell_direction_alignment PASSED                                                           [ 50%]
tests/test_runner.py::test_run_all_four PASSED                                                                       [ 60%]
tests/test_runner.py::test_profiles_diverge PASSED                                                                   [ 70%]
tests/test_runner.py::test_marks_degraded PASSED                                                                     [ 80%]
tests/test_runner.py::test_config_hash_stability PASSED                                                              [ 90%]
tests/test_runner.py::test_observation_mode_enforced PASSED                                                          [100%]
==================================================== 10 passed in 0.04s ====================================================
"""
import pytest
from profile_runner import ProfileAttribution, run_all_profiles


# ════════════════════════════════════════════════
# TEST 1: Single profile instantiates correctly
# ════════════════════════════════════════════════
def test_runner_instantiation():
    runner = ProfileAttribution("PF-C")
    assert runner.profile_id == "PF-C"
    assert runner.profile["weights"]["xgb"] == 0.35
    assert len(runner._config_hash) == 10  # short sha1


# ════════════════════════════════════════════════
# TEST 2: Unknown profile raises
# ════════════════════════════════════════════════
def test_unknown_profile_raises():
    with pytest.raises(KeyError, match="Unknown profile"):
        ProfileAttribution("PF-Z")


# ════════════════════════════════════════════════
# TEST 3: Full candidate process — PF-A PASS
# ════════════════════════════════════════════════
def test_pfa_full_pass():
    runner = ProfileAttribution("PF-A")
    rec = runner.process_candidate(
        symbol="USD/JPY",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=+1,
        xgb_p_up=0.80,
        mc_p_up=0.75
    )

    assert rec["profile_id"] == "PF-A"
    assert rec["decision"]["action"] in ["PASS", "WATCH", "REJECT"]
    assert "rel_score" in rec["decision"]
    assert rec["execution"]["eligible_for_execution"] is False  # Observation mode
    assert "factors" in rec
    assert "counterfactuals" in rec
    assert "attribution" in rec


# ════════════════════════════════════════════════
# TEST 4: P_UP conversion centered correctly
# ════════════════════════════════════════════════
def test_probability_centering():
    runner = ProfileAttribution("PF-B")
    rec = runner.process_candidate(
        symbol="TEST",
        candidate_direction="BUY",
        trend_raw=0,
        location_raw=0,
        xgb_p_up=0.5,   # → 0 centered
        mc_p_up=0.0     # → -1.0
    )
    assert rec["factors"]["xgb"]["aligned"] == pytest.approx(0.0)
    assert rec["factors"]["mc"]["aligned"] == pytest.approx(-1.0)


# ════════════════════════════════════════════════
# TEST 5: SELL alignment flips signs correctly
# ════════════════════════════════════════════════
def test_sell_direction_alignment():
    runner = ProfileAttribution("PF-B")
    rec = runner.process_candidate(
        symbol="TEST",
        candidate_direction="SELL",
        trend_raw=-1,  # bearish → supports SELL → +1 aligned
        location_raw=-1,
        xgb_p_up=0.1,  # → -0.8 raw → +0.8 aligned
        mc_p_up=0.1
    )
    assert rec["factors"]["trend"]["aligned"] == pytest.approx(+1.0)
    assert rec["factors"]["xgb"]["aligned"] == pytest.approx(+0.8)


# ════════════════════════════════════════════════
# TEST 6: run_all_profiles returns exactly 4
# ════════════════════════════════════════════════
def test_run_all_four():
    results = run_all_profiles(
        symbol="USD/JPY",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=+1,
        xgb_p_up=0.75,
        mc_p_up=0.65
    )
    assert set(results.keys()) == {"PF-A", "PF-B", "PF-C", "PF-D"}
    assert all(isinstance(r, dict) for r in results.values())


# ════════════════════════════════════════════════
# TEST 7: Same input → different scores per profile
# ════════════════════════════════════════════════
def test_profiles_diverge():
    results = run_all_profiles(
        symbol="EUR/USD",
        candidate_direction="BUY",
        trend_raw=+1,
        location_raw=0,
        xgb_p_up=0.5,
        mc_p_up=0.5
    )
    scores = {pid: rec["decision"]["rel_score"] for pid, rec in results.items()}
    # PF-A weights trend highest → highest score
    assert scores["PF-A"] > scores["PF-C"]
    # PF-D thresholds highest → hardest to PASS
    assert results["PF-D"]["decision"]["rel_score"] < results["PF-A"]["decision"]["rel_score"]


# ════════════════════════════════════════════════
# TEST 8: Missing factors → degraded flag set
# ════════════════════════════════════════════════
def test_marks_degraded():
    runner = ProfileAttribution("PF-B")
    rec = runner.process_candidate(
        symbol="TEST",
        candidate_direction="BUY",
        trend_raw=None,
        location_raw=+1,
        xgb_p_up=0.6,
        mc_p_up=None
    )
    assert rec["decision"]["degraded"] is True
    assert "trend" in rec["decision"]["missing_factors"]
    assert "mc" in rec["decision"]["missing_factors"]


# ════════════════════════════════════════════════
# TEST 9: Config hash stable per identical config
# ════════════════════════════════════════════════
def test_config_hash_stability():
    r1 = ProfileAttribution("PF-B")
    r2 = ProfileAttribution("PF-B")
    assert r1._config_hash == r2._config_hash
    # Different profile = different hash
    r_a = ProfileAttribution("PF-A")
    assert r_a._config_hash != r1._config_hash


# ════════════════════════════════════════════════
# TEST 10: Execution always observation mode
# ════════════════════════════════════════════════
def test_observation_mode_enforced():
    results = run_all_profiles(
        symbol="GBP/USD",
        candidate_direction="BUY",
        trend_raw=+1, location_raw=+1, xgb_p_up=0.9, mc_p_up=0.9
    )
    for pid, rec in results.items():
        assert rec["execution"]["eligible_for_execution"] is False, f"{pid} should be observation only"
        assert rec["execution"]["order_submitted"] is False
        assert rec["execution"]["execution_block_reason"] == "OBSERVATION_MODE"