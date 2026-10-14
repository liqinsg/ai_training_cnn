"""
fx_db.py - fire-and-forget Oracle ADB logger for the forex bot (step 1: shadow path).

Safety contract
  * OFF by default: nothing happens unless ENABLE_DB_LOGGING=1.
  * Never raises into the caller and never blocks: calls only enqueue.
  * DB down / slow / erroring -> payloads spill to a JSONL file; a circuit
    breaker pauses DB attempts after repeated failures.
  * env (DEMO/LIVE) is derived from OANDA_ENV only; unknown value -> disabled.
  * Bind variables only (no string-built SQL). Password is never logged.

Env vars
  ENABLE_DB_LOGGING   1/true to enable (default off)
  OANDA_ENV           practice|demo -> DEMO ; live -> LIVE
  FXBOT_DB_USER       FXBOT
  FXBOT_DB_PASSWORD
  FXBOT_DB_DSN        tnsnames alias from the wallet, e.g. xxxx_low
  FXBOT_WALLET_DIR    unzipped wallet directory
  FXBOT_WALLET_PASSWORD  password chosen when downloading the wallet
  FXBOT_SPILL_FILE    optional, default fx_db_spill.jsonl

Usage
  import fx_db
  fx_db.log_decision_run("P1", flags={"ENABLE_X": False}, git_sha="abc123",
      strength=[{"currency": "JPY", "score": -1.2, "rank_pos": 8, "score_v2": -0.9}],
      decisions=[{"instrument": "USD_JPY", "direction": "LONG", "final_score": 0.62,
                  "action": "SKIP", "reason": "below threshold", "record": {...},
                  "factors": [{"factor": "Trend", "raw_score": 0.7, "weight": 0.4,
                               "contribution": 0.28, "score_without": 0.34,
                               "flipped_action": 0}]}])
  Self-test (synchronous, ignores the flag):  python fx_db.py --selftest
"""
import atexit
import json
import logging
import os
import queue
import stat
import sys
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("fx_db")

_ENV_MAP = {"practice": "DEMO", "demo": "DEMO", "live": "LIVE"}
_MAX_QUEUE = 1000
_BREAKER_FAILS = 3          # consecutive failures before pausing DB attempts
_BREAKER_PAUSE_S = 300      # pause length


def _enabled():
    return os.getenv("ENABLE_DB_LOGGING", "0").strip().lower() in ("1", "true", "yes", "on")


def _env():
    return _ENV_MAP.get(os.getenv("OANDA_ENV", "").strip().lower())


def _utcnow():
    """Naive UTC datetime for plain TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _js(obj):
    return None if obj is None else json.dumps(obj, default=str, separators=(",", ":"))


def _spill(kind, payload):
    path = os.getenv("FXBOT_SPILL_FILE", "fx_db_spill.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _utcnow().isoformat(), "kind": kind,
                                "payload": payload}, default=str) + "\n")
    except Exception:
        log.exception("fx_db: spill write failed")


def _check_wallet_perms(wdir):
    try:
        for name in os.listdir(wdir):
            if name.startswith(("ewallet", "cwallet", "keystore", "truststore")):
                mode = os.stat(os.path.join(wdir, name)).st_mode
                if mode & (stat.S_IRWXG | stat.S_IRWXO):
                    log.warning("fx_db: wallet file %s is group/world accessible; chmod 600", name)
    except Exception:
        pass


def _make_pool():
    import oracledb  # imported lazily so the bot runs even if it is not installed
    wdir = os.environ["FXBOT_WALLET_DIR"]
    _check_wallet_perms(wdir)
    return oracledb.create_pool(
        user=os.environ["FXBOT_DB_USER"],
        password=os.environ["FXBOT_DB_PASSWORD"],
        dsn=os.environ["FXBOT_DB_DSN"],
        config_dir=wdir,
        wallet_location=wdir,
        wallet_password=os.environ.get("FXBOT_WALLET_PASSWORD"),
        min=1, max=2, increment=1,
        tcp_connect_timeout=5,
    )


# ----------------------------------------------------------------- handlers
def _h_decision_run(conn, p):
    import oracledb
    cur = conn.cursor()
    rid = cur.var(oracledb.NUMBER)
    cur.execute(
        "INSERT INTO decision_run (env, profile_id, flags_json, git_sha, config_hash, status) "
        "VALUES (:env, :prof, :flags, :sha, :chash, :status) RETURNING run_id INTO :rid",
        env=p["env"], prof=p["profile_id"], flags=p["flags"], sha=p["git_sha"],
        chash=p["config_hash"], status=p["status"], rid=rid)
    run_id = int(rid.getvalue()[0])

    if p["strength"]:
        cur.executemany(
            "INSERT INTO strength_snapshot (run_id, currency, score, rank_pos, score_v2) "
            "VALUES (:r, :c, :s, :rk, :s2)",
            [(run_id, s["currency"], s.get("score"), s.get("rank_pos"), s.get("score_v2"))
             for s in p["strength"]])

    for d in p["decisions"]:
        did = cur.var(oracledb.NUMBER)
        cur.execute(
            "INSERT INTO decision (run_id, instrument, direction, final_score, action, reason, record_json) "
            "VALUES (:r, :i, :d, :fs, :a, :re, :rec) RETURNING decision_id INTO :did",
            r=run_id, i=d["instrument"], d=d.get("direction"), fs=d.get("final_score"),
            a=d["action"], re=(d.get("reason") or "")[:400] or None, rec=d["record"], did=did)
        decision_id = int(did.getvalue()[0])
        if d["factors"]:
            cur.executemany(
                "INSERT INTO decision_factor (decision_id, factor, raw_score, weight, contribution, "
                "score_without, flipped_action) VALUES (:d, :f, :rs, :w, :c, :sw, :fl)",
                [(decision_id, f["factor"], f.get("raw_score"), f.get("weight"),
                  f.get("contribution"), f.get("score_without"), f.get("flipped_action"))
                 for f in d["factors"]])


def _h_equity(conn, p):
    conn.cursor().execute(
        "INSERT INTO equity_snapshot (env, ts, balance, nav, unrealized_pl, margin_used) "
        "VALUES (:env, :ts, :b, :n, :u, :m)",
        env=p["env"], ts=datetime.fromisoformat(p["ts"]), b=p["balance"], n=p["nav"],
        u=p["unrealized_pl"], m=p["margin_used"])


def _h_api_usage(conn, p):
    conn.cursor().execute(
        "INSERT INTO api_usage (provider, model, cache_hit, tokens_in, tokens_out, status) "
        "VALUES (:pr, :mo, :ch, :ti, :to_, :st)",
        pr=p["provider"], mo=p["model"], ch=p["cache_hit"], ti=p["tokens_in"],
        to_=p["tokens_out"], st=p["status"])


_HANDLERS = {"decision_run": _h_decision_run, "equity": _h_equity, "api_usage": _h_api_usage}


# ------------------------------------------------------------------- worker
class _Writer:
    def __init__(self):
        self.q = queue.Queue(maxsize=_MAX_QUEUE)
        self.pool = None
        self.fails = 0
        self.paused_until = 0.0
        self.thread = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="fx_db", daemon=True)
                self.thread.start()
                atexit.register(self.flush, 5)

    def put(self, kind, payload):
        self.start()
        try:
            self.q.put_nowait((kind, payload))
        except queue.Full:
            _spill(kind, payload)  # never block the trading loop

    def _run(self):
        while True:
            kind, payload = self.q.get()
            try:
                if time.time() < self.paused_until:
                    _spill(kind, payload)
                    continue
                if self.pool is None:
                    self.pool = _make_pool()
                conn = self.pool.acquire()
                try:
                    _HANDLERS[kind](conn, payload)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    self.pool.release(conn)
                self.fails = 0
            except Exception as e:
                self.fails += 1
                log.error("fx_db: %s write failed (%d): %s", kind, self.fails, type(e).__name__)
                _spill(kind, payload)
                if self.fails >= _BREAKER_FAILS:
                    self.paused_until = time.time() + _BREAKER_PAUSE_S
                    self.fails = 0
                    log.error("fx_db: circuit open, pausing DB writes %ds", _BREAKER_PAUSE_S)
            finally:
                self.q.task_done()

    def flush(self, timeout=10):
        end = time.time() + timeout
        while self.q.unfinished_tasks and time.time() < end:
            time.sleep(0.1)


_writer = _Writer()


def _gate():
    """Return env string if logging should proceed, else None."""
    if not _enabled():
        return None
    env = _env()
    if env is None:
        log.error("fx_db: OANDA_ENV must be practice/demo/live; DB logging disabled")
    return env


# --------------------------------------------------------------- public API
def log_decision_run(profile_id, flags=None, git_sha=None, config_hash=None, status="OK",
                     strength=None, decisions=None):
    try:
        env = _gate()
        if not env:
            return
        decs = []
        for d in decisions or []:
            decs.append({**d, "record": _js(d.get("record")), "factors": list(d.get("factors") or [])})
        _writer.put("decision_run", {
            "env": env, "profile_id": profile_id, "flags": _js(flags), "git_sha": git_sha,
            "config_hash": config_hash, "status": status,
            "strength": list(strength or []), "decisions": decs})
    except Exception:
        log.exception("fx_db: log_decision_run failed")


def log_equity(balance, nav, unrealized_pl=None, margin_used=None):
    try:
        env = _gate()
        if not env:
            return
        _writer.put("equity", {"env": env, "ts": _utcnow().isoformat(), "balance": balance,
                               "nav": nav, "unrealized_pl": unrealized_pl, "margin_used": margin_used})
    except Exception:
        log.exception("fx_db: log_equity failed")


def log_api_usage(provider, model, cache_hit, tokens_in=None, tokens_out=None, status="OK"):
    try:
        if not _gate():
            return
        _writer.put("api_usage", {"provider": provider, "model": model, "cache_hit": int(bool(cache_hit)),
                                  "tokens_in": tokens_in, "tokens_out": tokens_out, "status": status})
    except Exception:
        log.exception("fx_db: log_api_usage failed")


def flush(timeout=10):
    _writer.flush(timeout)


# ---------------------------------------------------------------- self-test
def _selftest():
    print("[config]")
    for k in ("FXBOT_DB_USER", "FXBOT_DB_DSN", "FXBOT_WALLET_DIR", "OANDA_ENV", "ENABLE_DB_LOGGING"):
        print(f"  {k} = {os.getenv(k, '<unset>')}")
    print("[connect]")
    pool = _make_pool()
    with pool.acquire() as conn:
        cur = conn.cursor()
        cur.execute("SELECT USER, SYS_CONTEXT('USERENV','DB_NAME') FROM dual")
        print("  user/db:", cur.fetchone())
        cur.execute("SELECT COUNT(*) FROM user_tables")
        print("  tables :", cur.fetchone()[0], "(expect 17)")
        cur.execute("SELECT profile_id, is_live FROM strategy_profile ORDER BY 1")
        print("  profiles:", cur.fetchall())
    print("[result] OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # _selftest()
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)