import json, os, time

SIGNAL_FILE = "signal.json"
last = "WAIT"

def send(sig):
    with open(SIGNAL_FILE,"w") as f:
        json.dump({"signal":sig},f)
    time.sleep(0.3)

def clear():
    os.path.exists(SIGNAL_FILE) and os.remove(SIGNAL_FILE)

def decide(cur, has, side):
    global last
    if cur==last: return "KEEP"
    if cur=="BUY":
        if not has: return "OPEN_BUY"
        return "KEEP" if side=="BUY" else "CLOSE_SELL_OPEN_BUY"
    if cur=="SELL":
        if not has: return "OPEN_SELL"
        return "KEEP" if side=="SELL" else "CLOSE_BUY_OPEN_SELL"
    return "WAIT"

print("🧪 AUTO-TEST: BOT LOGIC")
print("="*40)
print("SIGNAL | POS | ACTION")
print("="*40)

cases = [
    ("BUY",False,"NONE","OPEN_BUY"),
    ("BUY",True,"BUY","KEEP"),
    ("SELL",True,"BUY","CLOSE_BUY_OPEN_SELL"),
    ("SELL",True,"SELL","KEEP"),
    ("BUY",True,"SELL","CLOSE_SELL_OPEN_BUY"),
    ("SELL",False,"NONE","OPEN_SELL"),
]

ok=True
for sig,has,side,exp in cases:
    send(sig)
    act=decide(sig,has,side)
    s="✅"if act==exp else"❌"
    if act!=exp:ok=False
    print(f"{s} {sig:4} | {side:4} | {act}")
    clear()

print("="*40)
print(f"RESULT: {'ALL PASS'if ok else'FAIL'}")