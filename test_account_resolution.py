#!/usr/bin/env python3
"""Offline test of account-ID resolution. Does NOT import or run the bot."""
import sys
import config_bot as C

LIVE_ACCT_PREFIX = "001-"   # live accounts
DEMO_ACCT_PREFIX = "101-"   # practice accounts

def indexed(live: bool):
    key = "account_id_live" if live else "account_id_demo"
    return {int(pid): p[key] for pid, p in C.PROFILES.items()}

passed = failed = 0
def check(label, got, want):
    global passed, failed
    ok = got == want
    passed += ok; failed += (not ok)
    print(f"  {'✅' if ok else '❌'} {label}\n       got={got}  want={want}")

print("=" * 60)
print("[1/4] Profile default (no -a): demo")
for n in C.PROFILE_IDS:
    want = C.PROFILES[str(n)]["account_id_demo"]
    got = C.resolve_account_id(n, live=False)
    check(f"-p {n}", got, (want, "Profile内置"))

print("\n[2/4] Profile default (no -a): --live")
for n in C.PROFILE_IDS:
    want = C.PROFILES[str(n)]["account_id_live"]
    got = C.resolve_account_id(n, live=True)
    check(f"-p {n} --live", got, (want, "Profile内置"))

print("\n[3/4] Override: -p n -a m (demo and live)")
for live in (False, True):
    idx = indexed(live)
    env = "LIVE" if live else "DEMO"
    for n in C.PROFILE_IDS:
        for m in C.PROFILE_IDS:
            got = C.resolve_account_id(n, live, account_override=m, indexed_accounts=idx)
            check(f"-p {n} -a {m} {env}", got, (idx[m], f"-a {m}"))

print("\n[4/4] Sanity + error handling")
for pid, p in C.PROFILES.items():
    sfx = p["ACCOUNT_SUFFIX"]
    check(f"profile {pid} demo suffix", p["account_id_demo"].endswith(f"-{sfx}"), True)
    check(f"profile {pid} live suffix", p["account_id_live"].endswith(f"-{sfx}"), True)
    check(f"profile {pid} demo prefix", p["account_id_demo"].startswith(DEMO_ACCT_PREFIX), True)
    check(f"profile {pid} live prefix", p["account_id_live"].startswith(LIVE_ACCT_PREFIX), True)
    check(f"profile {pid} demo != live", p["account_id_demo"] != p["account_id_live"], True)

def raises(fn):
    try: fn(); return False
    except ValueError: return True

check("-a 99 (unknown) raises", raises(lambda: C.resolve_account_id(
    2, False, account_override=99, indexed_accounts=indexed(False))), True)
check("-a 2 with no mapping raises", raises(lambda: C.resolve_account_id(
    2, False, account_override=2)), True)
check("unknown profile 9 raises", raises(lambda: C.resolve_account_id(9, False)), True)

print("=" * 60)
print(f"RESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

