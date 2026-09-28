import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def build_mc_telegram(
    mc_results: list,
    mc_report_title: str,
    mc_tf: str,
    mc_lookback: int,
    mc_forecast: int,
    simulations: int,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"📊 **{mc_report_title}**",
        f"📅 Generated: {now}",
        f"🔹 TF: {mc_tf} | Lookback: {mc_lookback} | Forecast: {mc_forecast} | Sims: {simulations}",
        "",
    ]
    for r in mc_results:
        lo, hi = r["range_90"]
        lines.extend(
            [
                f"🔹 **{r['pair']}**",
                f"   💵 Last Close: `{r['current_price']}`",
                f"   📊 Percentile: `{r['percentile_rank']}%`",
                f"   🎯 UP: `{r['p_up_pct']}%` | DOWN: `{r['p_down_pct']}%`",
                f"   📏 90% Band: `{lo}` – `{hi}`",
                f"   🔍 Touch: Low `{r['touch_lower_pct']}%` | High `{r['touch_upper_pct']}%`",
                f"   {r['regime']}",
                "",
            ]
        )
    return "\n".join(lines)

def build_trade_telegram(trade_lines: list, mc_summary: list = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"🤖 MULTI‑PAIR UPDATE — {now}"]
    lines.extend(trade_lines)
    if mc_summary:
        lines.append("")
        lines.append("📊 *MC Context:*")
        for s in mc_summary:
            lines.append(f"   {s}")
    return "\n".join(lines)
