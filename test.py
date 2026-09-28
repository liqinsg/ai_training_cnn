from dotenv import dotenv_values, load_dotenv
import os

print("=== 当前 env ===")
print(f"OANDA_API_TOKEN already in env: {'OANDA_API_TOKEN' in os.environ}")
print(f"OANDA_API_TOKEN_LIVE already in env: {'OANDA_API_TOKEN_LIVE' in os.environ}")

print("\n=== dotenv_values('.env') ===")
cfg = dotenv_values(".env")
for k in cfg:
    if "TOKEN" in k or "ACCOUNT_ID" in k:
        v = cfg[k]
        print(f"  {k} = {repr(v[:8]+'...' if v and len(v)>8 else v)}")

print("\n=== load_dotenv('.env', override=False) ===")
result = load_dotenv(".env", override=False)
print(f"  返回值: {result}")
print(f"  OANDA_API_TOKEN = {repr(os.getenv('OANDA_API_TOKEN'))}")
print(f"  OANDA_API_TOKEN_LIVE = {repr(os.getenv('OANDA_API_TOKEN_LIVE'))}")

print("\n=== load_dotenv('.env', override=True) ===")
result = load_dotenv(".env", override=True)
print(f"  返回值: {result}")
print(f"  OANDA_API_TOKEN = {repr(os.getenv('OANDA_API_TOKEN'))}")
print(f"  OANDA_API_TOKEN_LIVE = {repr(os.getenv('OANDA_API_TOKEN_LIVE'))}")
