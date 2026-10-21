# example of csv analysis 
import pandas as pd
import glob

# 读全部账户
dfs = []
for f in glob.glob("./trade_data/fx_trades_*.csv"):
    dfs.append(pd.read_csv(f))
df = pd.concat(dfs, ignore_index=True)

# 按账户汇总
print(df.groupby("profile_id").agg(
    总单数=("trade_id","count"),
    TP=("cat",lambda x:(x=="TP").sum()),
    SL=("cat",lambda x:(x=="SL").sum()),
    提前平仓=("cat",lambda x:(x=="CLOSE").sum())
))

# 筛选某账户+某时间段
df[
    (df["profile_id"]=="101-003-39389016-002") &
    (df["date"]>="2026-10-01")
].to_csv("oct_analysis.csv", index=False)
