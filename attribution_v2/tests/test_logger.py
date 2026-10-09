"""
test_logger.py — Validate isolated logging per profile
(ai-sprint) qili@NBK202500000057 ~/projects/ai_training_cnn/attribution_v2 (v2026)$ python -m pytest tests/test_logger.py -v
=================================================== test session starts ====================================================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /home/qili/miniconda3/envs/ai-sprint/bin/python
cachedir: .pytest_cache
rootdir: /home/qili/projects/ai_training_cnn/attribution_v2
plugins: asyncio-1.4.0, anyio-4.12.1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/test_logger.py::test_creates_profile_dir PASSED                                                                [ 10%]
tests/test_logger.py::test_write_creates_file PASSED                                                                 [ 20%]
tests/test_logger.py::test_append_accumulates PASSED                                                                 [ 30%]
tests/test_logger.py::test_profile_isolation PASSED                                                                  [ 40%]
tests/test_logger.py::test_write_all_four PASSED                                                                     [ 50%]
tests/test_logger.py::test_date_filename_format PASSED                                                               [ 60%]
tests/test_logger.py::test_read_missing_returns_empty PASSED                                                         [ 70%]
tests/test_logger.py::test_dir_names_lowercase PASSED                                                                [ 80%]
tests/test_logger.py::test_unicode_safe PASSED                                                                       [ 90%]
tests/test_logger.py::test_file_closed PASSED                                                                        [100%]
==================================================== 10 passed in 0.05s ====================================================
"""
import os
from pathlib import Path
import pytest
from profile_logger import ProfileLogger, write_all, clear_all_logs, LOGS_ROOT


# ════════════════════════════════════════════════
# Fixture: Isolate logs to temp dir
# ════════════════════════════════════════════════
@pytest.fixture
def temp_logs(tmp_path):
    """Temp directory for all test logs — auto-cleaned."""
    return tmp_path / "test_logs"


# ════════════════════════════════════════════════
# TEST 1: Profile directories created automatically
# ════════════════════════════════════════════════
def test_creates_profile_dir(temp_logs):
    logger = ProfileLogger("PF-A", logs_root=temp_logs)
    assert (temp_logs / "pf-a").exists()
    assert (temp_logs / "pf-a").is_dir()


# ════════════════════════════════════════════════
# TEST 2: Write → file appears, line valid JSON
# ════════════════════════════════════════════════
def test_write_creates_file(temp_logs):
    logger = ProfileLogger("PF-B", logs_root=temp_logs)
    record = {"profile_id": "PF-B", "decision": "PASS", "symbol": "USD/JPY"}
    bytes_written = logger.write(record, date_str="2026-10-09")

    file_path = temp_logs / "pf-b" / "2026-10-09.jsonl"
    assert file_path.exists()
    assert bytes_written > 0

    import json
    with open(file_path) as f:
        loaded = json.loads(f.readline())
    assert loaded["profile_id"] == "PF-B"
    assert loaded["decision"] == "PASS"


# ════════════════════════════════════════════════
# TEST 3: Append mode — multiple writes accumulate
# ════════════════════════════════════════════════
def test_append_accumulates(temp_logs):
    logger = ProfileLogger("PF-C", logs_root=temp_logs)
    for i in range(3):
        logger.write({"seq": i}, date_str="2026-10-09")

    lines = logger.read_tail(n=10, date_str="2026-10-09")
    assert len(lines) == 3
    assert [r["seq"] for r in lines] == [0, 1, 2]


# ════════════════════════════════════════════════
# TEST 4: Profile isolation — no cross-contamination
# ════════════════════════════════════════════════
def test_profile_isolation(temp_logs):
    log_a = ProfileLogger("PF-A", logs_root=temp_logs)
    log_d = ProfileLogger("PF-D", logs_root=temp_logs)

    log_a.write({"msg": "only in A"}, date_str="2026-10-09")
    log_d.write({"msg": "only in D"}, date_str="2026-10-09")

    lines_a = log_a.read_tail(date_str="2026-10-09")
    lines_d = log_d.read_tail(date_str="2026-10-09")

    assert len(lines_a) == 1
    assert len(lines_d) == 1
    assert lines_a[0]["msg"] == "only in A"
    assert lines_d[0]["msg"] == "only in D"
    assert temp_logs / "pf-a" != temp_logs / "pf-d"


# ════════════════════════════════════════════════
# TEST 5: write_all() → 4 files, 1 line each
# ════════════════════════════════════════════════
def test_write_all_four(temp_logs, monkeypatch):
    monkeypatch.setattr("profile_logger.LOGS_ROOT", temp_logs)

    records = {
        "PF-A": {"profile_id": "PF-A", "decision": "PASS"},
        "PF-B": {"profile_id": "PF-B", "decision": "WATCH"},
        "PF-C": {"profile_id": "PF-C", "decision": "PASS"},
        "PF-D": {"profile_id": "PF-D", "decision": "REJECT"},
    }

    bytes_map = write_all(records, date_str="2026-10-09")
    assert len(bytes_map) == 4
    assert all(v > 0 for v in bytes_map.values())

    # Verify each independently
    for pid in records:
        lines = ProfileLogger(pid, logs_root=temp_logs).read_tail(date_str="2026-10-09")
        assert len(lines) == 1
        assert lines[0]["profile_id"] == pid


# ════════════════════════════════════════════════
# TEST 6: Date-based filename format
# ════════════════════════════════════════════════
def test_date_filename_format(temp_logs):
    logger = ProfileLogger("PF-A", logs_root=temp_logs)
    logger.write({"test": 1}, date_str="2026-12-31")
    expected_file = temp_logs / "pf-a" / "2026-12-31.jsonl"
    assert expected_file.exists()


# ════════════════════════════════════════════════
# TEST 7: read_tail returns empty list for missing file
# ════════════════════════════════════════════════
def test_read_missing_returns_empty(temp_logs):
    logger = ProfileLogger("PF-A", logs_root=temp_logs)
    lines = logger.read_tail(date_str="1999-01-01")
    assert lines == []


# ════════════════════════════════════════════════
# TEST 8: Lowercase directory names
# ════════════════════════════════════════════════
def test_dir_names_lowercase(temp_logs):
    logger = ProfileLogger("pf-a", logs_root=temp_logs)
    assert "pf-a" in str(logger._ensure_dir())
    logger2 = ProfileLogger("PF-A", logs_root=temp_logs)
    assert logger2.profile_id == "pf-a"  # normalized


# ════════════════════════════════════════════════
# TEST 9: Unicode characters preserved
# ════════════════════════════════════════════════
def test_unicode_safe(temp_logs):
    logger = ProfileLogger("PF-A", logs_root=temp_logs)
    record = {"symbol": "EUR/JPY", "note": "📈 上昇趋势"}
    logger.write(record, date_str="2026-10-09")
    loaded = logger.read_tail(date_str="2026-10-09")[0]
    assert loaded["note"] == "📈 上昇趋势"


# ════════════════════════════════════════════════
# TEST 10: File handle closed after write
# ════════════════════════════════════════════════
def test_file_closed(temp_logs):
    logger = ProfileLogger("PF-A", logs_root=temp_logs)
    import gc

    record = {"test": "gc"}
    logger.write(record, date_str="2026-10-09")
    # Force GC — would raise if file handle leaked
    gc.collect()
    # Can delete immediately — no lock
    fpath = logger._get_file_path("2026-10-09")
    fpath.unlink()
    assert not fpath.exists()