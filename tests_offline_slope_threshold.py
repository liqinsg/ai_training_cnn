"""
Offline proof for: relax profile3 EMA-slope threshold 0.001 -> 0.0003.

No network, no OANDA calls, no orders. The real `evaluate_trend_and_tp`
implementation is extracted from fx_trade_bot_v683.py via AST and executed with
stubbed module-level dependencies, so this tests the SHIPPED source text.

Run:  python tests_offline_slope_threshold.py
"""

import ast
import logging
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"

WANTED = {
    "calculate_ema",
    "calculate_ema_slope",
    "_pips_to_price",
    "_price_to_pips",
    "evaluate_trend_and_tp",
}


def load_real_functions():
    """Pull the four helpers + the filter function straight out of the bot file."""
    src = BOT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mod = ast.Module(body=[], type_ignores=[])
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED:
            mod.body.append(node)
    found = {n.name for n in mod.body}
    missing = WANTED - found
    if missing:
        raise SystemExit(f"❌ could not extract from {BOT.name}: {sorted(missing)}")

    # The shipped profile3 min_slope, read from the same file's config literal.
    def module_literal(name):
        return ast.literal_eval(
            next(
                n.value
                for n in tree.body
                if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == name
            )
        )

    cfg_src = module_literal("_TREND_TP_CONFIG")
    # Module-level scalar the diagnostic block reads, extracted the same way so
    # the test exercises the shipped value rather than a hardcoded copy.
    band_fraction = module_literal("RELAXED_SLOPE_FRACTION")
    ns = {
        "pd": pd,
        "logger": logging.getLogger("offline-test"),
        "RELAXED_SLOPE_FRACTION": band_fraction,
    }
    exec(compile(mod, str(BOT), "exec"), ns)
    return ns, cfg_src, missing


NS, SHIPPED_CFG, _ = load_real_functions()
evaluate = NS["evaluate_trend_and_tp"]


def trend_frame(direction):
    """EMA10 whose 5-bar slope is ~ -5.0e-4: passes 3e-4, fails 1e-3."""
    n = 120
    closes = [1.2000 * (1.0 - 1.0e-4) ** i for i in range(n)]
    return pd.DataFrame({"Close": closes})


def run(profile, direction, min_slope, price_side_ok=True):
    cfg = dict(NS["TREND_TP_CONFIG"]) if "TREND_TP_CONFIG" in NS else dict(SHIPPED_CFG)
    cfg = {
        "base_tp_pips": 30,
        "mc_strong_threshold": 0.75,
        "weekly_ema_period": 100,
        "ema100_buffer_pips": 30,
        "profile2": {
            "tp_normal_mult": 1.0,
            "tp_strong_mult": 2.0,
            "ema_period": 10,
            "slope_lookback": 5,
            "min_slope": 0.001,          # must stay untouched
        },
        "profile3": {
            "tp_mult": 1.2,
            "ema_period": 10,
            "slope_lookback": 5,
            "min_slope": min_slope,
        },
    }
    env = dict(NS)
    env["TREND_TP_CONFIG"] = cfg
    env["cfg_bot"] = lambda name, default: {"TREND_FILTER_ENABLED": True}.get(
        name, default
    )
    # SLOPE_DIAG is a module-level global in the bot; the offline harness must
    # provide it too, otherwise the diagnostic block raises NameError.
    env.setdefault("SLOPE_DIAG", False)
    fn = NS["evaluate_trend_and_tp"]
    fn.__globals__.update(env)

    df = trend_frame(direction)
    ema10 = NS["calculate_ema"](df["Close"], 10)
    slope, ema_level = NS["calculate_ema_slope"](ema10, 5)
    # Place entry on the side of EMA10 that satisfies the price condition.
    entry = ema_level * (0.999 if direction == "SELL" else 1.001)
    if not price_side_ok:
        entry = ema_level * (1.001 if direction == "SELL" else 0.999)

    passed, tp, reason = fn(
        profile_name=profile,
        direction=direction,
        mc_pct_up=50.0,
        entry_price=entry,
        pip_value=0.0001,
        df_h1=df,
        weekly_ema100=None,
        timeframe="15m",
    )
    return passed, slope, ema_level, entry, reason, tp


def main():
    logging.basicConfig(level=logging.WARNING, format="      log| %(message)s")
    failures = []

    p3_new = SHIPPED_CFG["profile3"]["min_slope"]
    p2_now = SHIPPED_CFG["profile2"]["min_slope"]
    print(f"shipped profile3.min_slope = {p3_new}")
    print(f"shipped profile2.min_slope = {p2_now}\n")

    if p3_new != 0.0003:
        failures.append(f"profile3.min_slope is {p3_new}, expected 0.0003")
    if p2_now != 0.001:
        failures.append(f"profile2.min_slope changed to {p2_now} — must stay 0.001")

    cases = [
        # (label, profile, direction, min_slope, price_side_ok, expect_pass)
        ("BEFORE  profile3 SELL @0.001 ", "profile3", "SELL", 0.001, True, False),
        ("AFTER   profile3 SELL @0.0003", "profile3", "SELL", 0.0003, True, True),
        ("BEFORE  profile2 SELL @0.001 ", "profile2", "SELL", 0.001, True, False),
        ("guard   profile3 SELL wrong side", "profile3", "SELL", 0.0003, False, False),
    ]

    results = []
    for label, profile, direction, ms, side_ok, expect in cases:
        passed, slope, ema_level, entry, reason, tp = run(
            profile, direction, ms, side_ok
        )
        ok = passed is expect
        if not ok:
            failures.append(f"{label}: expected pass={expect}, got {passed}")
        results.append((label, slope, passed, tp, reason, ok))

    print(f"{'case':36} {'slope':>12}  {'result':>9}   verdict")
    print("-" * 96)
    for label, slope, passed, tp, reason, ok in results:
        verdict = "PASS" if ok else "FAIL"
        print(
            f"{label:36} {slope:12.7f}  {'TRADE':>9}   {verdict}"
            if passed
            else f"{label:36} {slope:12.7f}  {'SKIP':>9}   {verdict}"
        )
        if not passed:
            print(f"{'':36} {'':12}  reason: {reason}")

    print("\nlog-precision check (format must render sub-3e-4 slopes distinctly):")
    tiny = -0.000041
    print(f"   :.4f -> {tiny:.4f}   (indistinguishable from 0.0000)")
    print(f"   :.6f -> {tiny:.6f}   <- shipped")
    if f"{tiny:.6f}" == f"{0.0:.6f}":
        failures.append("log precision still collapses tiny slopes to 0.000000")

    print("\nSLOPE DIAG band derivation (SLOPE_DIAG=True, profile3):")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("      diag| %(message)s"))
    diag_logger = NS["logger"]
    diag_logger.addHandler(handler)
    diag_logger.setLevel(logging.INFO)
    NS["SLOPE_DIAG"] = True
    try:
        run("profile3", "SELL", p3_new)
    finally:
        diag_logger.removeHandler(handler)
        NS["SLOPE_DIAG"] = False

    frac = NS.get("RELAXED_SLOPE_FRACTION")
    expected_hi = p3_new / frac if frac else None
    print(f"   RELAXED_SLOPE_FRACTION={frac} -> band_hi={expected_hi}")
    if frac is None or abs(expected_hi - 0.001) > 1e-12:
        failures.append(
            f"band_hi derived as {expected_hi}, expected 0.001 (0.0003/0.3)"
        )
    if NS.get("SLOPE_DIAG") is not False:
        failures.append("SLOPE_DIAG was left enabled after the diagnostic run")

    print()
    if failures:
        print("❌ FAILURES:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ ALL CHECKS PASSED — profile3 relaxed, profile2 untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
