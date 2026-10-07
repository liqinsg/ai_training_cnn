"""
Offline proof for the profile3 EMA-slope relax + the Weekly EMA100 gate bug.

No network, no OANDA calls, no orders. The real `evaluate_trend_and_tp` and
`resolve_weekly_ema100` implementations are extracted from the bot source via
AST and executed with stubbed module-level dependencies, so this tests the
SHIPPED source text of both fx_trade_bot_v683.py and fx_trade_bot_v6.8.3.py.

Run:  python tests_offline_slope_threshold.py
"""

import ast
import logging
import sys
from pathlib import Path

import pandas as pd

from data_guard import (
    MIN_REQUIRED_BARS,
    get_safe_series,
    has_min_bars,
    safe_last,
    safe_tail,
    to_float,
)

BASE_DIR = Path(__file__).resolve().parent
BOT = BASE_DIR / "fx_trade_bot_v683.py"

WANTED = {
    "calculate_ema",
    "calculate_ema_slope",
    "_pips_to_price",
    "_price_to_pips",
    "resolve_weekly_ema100",
    "resolve_min_slope",
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
    baseline = module_literal("SLOPE_DIAG_BASELINE")
    ns = {
        "pd": pd,
        "logger": logging.getLogger("offline-test"),
        "SLOPE_DIAG_BASELINE": baseline,
        "MIN_SLOPE_LADDER": module_literal("MIN_SLOPE_LADDER"),
        # 数据边界保护 helpers —— evaluate_trend_and_tp 现在会调用它们，
        # AST 抽取执行时必须一并注入，否则 NameError（同 PROFILE_NAME 的坑）。
        "MIN_REQUIRED_BARS": MIN_REQUIRED_BARS,
        "get_safe_series": get_safe_series,
        "has_min_bars": has_min_bars,
        "safe_last": safe_last,
        "safe_tail": safe_tail,
        "to_float": to_float,
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
            "min_slope_rung": min_slope,
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


def verify_resolve_helper(bot_path, label):
    """Extract resolve_weekly_ema100 from `bot_path` and check its four cases.

    Generic on purpose: the same gate bug shipped in more than one bot file, so
    each fix must be proven against that file's own source text rather than
    assumed identical.
    """
    tree = ast.parse(bot_path.read_text(encoding="utf-8"))
    node = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "resolve_weekly_ema100"
        ),
        None,
    )
    if node is None:
        return [f"{label}: resolve_weekly_ema100 not found in {bot_path.name}"]

    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(bot_path), "exec"), ns)
    resolve = ns["resolve_weekly_ema100"]

    cached = 145.83
    problems = []
    cases = [
        ("enabled + cached", cached, True, cached),
        ("enabled + cache miss", None, True, None),
        ("disabled + cached", cached, False, None),
        ("disabled + cache miss", None, False, None),
    ]
    print(f"\n{label} ({bot_path.name}):")
    for case_label, c, enabled, expect in cases:
        got = resolve(c, enabled)
        ok = got == expect and type(got) is type(expect)
        print(
            f"   {case_label:22} -> {str(got):>7}  {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            problems.append(
                f"{label}: resolve_weekly_ema100({c}, {enabled}) = {got!r}, "
                f"expected {expect!r}"
            )
    if resolve(cached, True) is True:
        problems.append(f"{label}: gate still collapses the cached level into a boolean")
    return problems


def main():
    logging.basicConfig(level=logging.WARNING, format="      log| %(message)s")
    failures = []

    p3_rung = SHIPPED_CFG["profile3"]["min_slope_rung"]
    p2_now = SHIPPED_CFG["profile2"]["min_slope"]
    print(f"shipped profile3.min_slope_rung = {p3_rung}")
    print(f"shipped profile2.min_slope      = {p2_now}\n")

    ladder = NS["MIN_SLOPE_LADDER"]
    print(f"MIN_SLOPE_LADDER = {ladder}")
    if p3_rung not in ladder:
        failures.append(f"profile3.min_slope_rung {p3_rung} is not a ladder rung")
    if p3_rung != 0.0003:
        failures.append(f"profile3 rung is {p3_rung}, expected the widest 0.0003")
    if p2_now != 0.001:
        failures.append(f"profile2.min_slope changed to {p2_now} — must stay 0.001")
    # profile2 was never relaxed, so it must not carry a ladder knob at all.
    if "min_slope_rung" in SHIPPED_CFG["profile2"]:
        failures.append("profile2 gained a min_slope_rung it should not have")

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

    print("\nSLOPE DIAG sensitive-band criteria (SLOPE_DIAG=True, profile3):")
    import re

    diag_lines = []

    class _Capture(logging.Handler):
        def emit(self, record):
            if "SLOPE DIAG" in record.getMessage():
                diag_lines.append(record.getMessage())

    handler = _Capture()
    diag_logger = NS["logger"]
    diag_logger.addHandler(handler)
    diag_logger.setLevel(logging.INFO)
    NS["SLOPE_DIAG"] = True
    try:
        # price_ok=True (entry on the correct side of EMA10)
        run("profile3", "SELL", p3_rung, price_side_ok=True)
        # price_ok=False — the USDJPY case: slope-sensitive but price-blocked
        run("profile3", "SELL", p3_rung, price_side_ok=False)
        run("profile3", "BUY", p3_rung, price_side_ok=True)
    finally:
        diag_logger.removeHandler(handler)
        NS["SLOPE_DIAG"] = False

    baseline = NS.get("SLOPE_DIAG_BASELINE")
    print(f"   SLOPE_DIAG_BASELINE={baseline} (independent of min_slope)")
    if baseline != 0.001:
        failures.append(f"SLOPE_DIAG_BASELINE is {baseline}, expected 0.001")
    if len(diag_lines) != 3:
        failures.append(f"expected 3 diagnostic lines, captured {len(diag_lines)}")

    pattern = re.compile(
        r"slope=(?P<slope>-?\d+\.\d+) min_slope=(?P<min_slope>\d+\.\d+) "
        r"price_ok=(?P<price_ok>True|False) "
        r"loose\((?P<loose_th>-?[\d.]+)(?P<loose_cmp>[<>]=)\)=(?P<loose>True|False) "
        r"strict\((?P<strict_th>-?[\d.]+)(?P<strict_cmp>[<>]=)\)=(?P<strict>True|False) "
        r"sensitive=(?P<sensitive>True|False) would_flip=(?P<flip>True|False)"
    )
    for line in diag_lines:
        # search(), not match(): the subject starts with "profile=..." and the
        # slope fields come later.
        m = pattern.search(line.split("SLOPE DIAG: ", 1)[1])
        if not m:
            failures.append(f"diagnostic line did not parse: {line}")
            continue
        d = m.groupdict()
        slope = float(d["slope"])
        loose = d["loose"] == "True"
        strict = d["strict"] == "True"
        sensitive = d["sensitive"] == "True"
        flip = d["flip"] == "True"
        price_ok = d["price_ok"] == "True"

        # the printed thresholds must be the negated magnitudes
        if float(d["loose_th"]) != -float(d["min_slope"]):
            failures.append(f"loose threshold mismatch: {d['loose_th']}")
        if float(d["strict_th"]) != -baseline:
            failures.append(f"strict threshold mismatch: {d['strict_th']}")

        # The two slope verdicts must match their own thresholds, using the
        # filter's inclusive comparisons. The printed operator encodes
        # direction: "<=" is the BUY predicate (slope >= min_slope) and ">=" is
        # the SELL one (slope <= -min_slope).
        if d["loose_cmp"] == "<=":
            expect_loose = slope >= float(d["min_slope"])
            expect_strict = slope >= baseline
        else:
            expect_loose = slope <= -float(d["min_slope"])
            expect_strict = slope <= -baseline
        if loose != expect_loose:
            failures.append(f"loose verdict wrong for slope={slope}")
        if strict != expect_strict:
            failures.append(f"strict verdict wrong for slope={slope}")

        # sensitive must be orthogonal to price, would_flip must require it
        if sensitive != (loose and not strict):
            failures.append(f"sensitive wrong for slope={slope}")
        if flip != (price_ok and sensitive):
            failures.append(f"would_flip wrong for slope={slope}")
        print(
            f"   slope={slope:+.6f} price_ok={price_ok!s:5} "
            f"loose={loose!s:5} strict={strict!s:5} "
            f"sensitive={sensitive!s:5} would_flip={flip!s:5}"
        )

    # The regression the new criteria fixes: a price-blocked candidate must be
    # reported as sensitive=False OR would_flip=False — never as a flip.
    flips_while_price_blocked = [
        d for d in diag_lines if "price_ok=False" in d and "would_flip=True" in d
    ]
    if flips_while_price_blocked:
        failures.append("price_ok=False candidate reported would_flip=True")
    if not any("price_ok=False" in d for d in diag_lines):
        failures.append("no price-blocked diagnostic line was captured")
    if NS.get("SLOPE_DIAG") is not False:
        failures.append("SLOPE_DIAG was left enabled after the diagnostic run")

    print("\nWeekly EMA100 gate (the `a and b` short-circuit bug):")
    resolve = NS["resolve_weekly_ema100"]
    cached = 145.83

    # Reproduce the shipped bug: `cached and True` evaluates to the *boolean*,
    # so the filter compared prices against True (== 1.0) instead of 145.83.
    old_gate = cached and True
    print(f"   old `cached and True`      -> {old_gate!r} (type {type(old_gate).__name__})")
    print(f"   old SELL compare 157.21>   -> {157.21 > old_gate}  (blocks a valid SELL)")

    cases = [
        # (label, cached, enabled, expect)
        ("enabled + cached", cached, True, cached),
        ("enabled + cache miss", None, True, None),
        ("disabled + cached", cached, False, None),
        ("disabled + cache miss", None, False, None),
    ]
    for label, c, enabled, expect in cases:
        got = resolve(c, enabled)
        ok = got == expect and type(got) is type(expect)
        print(
            f"   {label:22} cached={str(c):>7} enabled={str(enabled):>5}"
            f" -> {str(got):>7}  {'ok' if ok else 'FAIL'}"
        )
        if not ok:
            failures.append(
                f"resolve_weekly_ema100({c}, {enabled}) = {got!r}, expected {expect!r}"
            )
    if resolve(cached, True) is True:
        failures.append("gate still collapses the cached level into a boolean")
    if not (157.21 > (cached and True)):
        failures.append("could not reproduce the original short-circuit symptom")

    # Both shipped profile switches must actually be off.
    for profile_cfg in ("config_bot.py",):
        cfg_path = BASE_DIR / profile_cfg
        flag = next(
            (
                line.split("#")[0].strip()
                for line in cfg_path.read_text(encoding="utf-8").splitlines()
                if line.startswith("WEEK_EMA100_FILTER_ENABLED")
            ),
            None,
        )
        print(f"   {profile_cfg}: {flag}")
        if flag != "WEEK_EMA100_FILTER_ENABLED = False":
            failures.append(f"{profile_cfg} WEEK flag not disabled: {flag!r}")

    # Same gate bug shipped in the sibling bot; prove that fix against its source.
    failures.extend(
        verify_resolve_helper(BASE_DIR / "fx_trade_bot_v6.8.3.py", "v6.8.3 sibling")
    )

    print()
    if failures:
        print("❌ FAILURES:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("✅ ALL CHECKS PASSED — slope band correct, Weekly EMA100 gate fixed + off")
    return 0


if __name__ == "__main__":
    sys.exit(main())
