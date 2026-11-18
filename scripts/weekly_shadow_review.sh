#!/usr/bin/env bash
# weekly_shadow_review.sh — 每周影子分析报告（L2 + Wide-range，供人工 review）
# =====================================================================
# 功能：
#   1. 跑 utils/analyze_sizing_shadow.py（L2 反事实，文本）
#   2. 跑 utils/analyze_wide_range.py（六项指标，JSON + 文本）
#   3. 汇总到 reports/weekly_review_YYYYMMDD/，只出报告，不做任何决策
#
# 适配说明（本地版）：
#   * analyze_sizing_shadow.py 本地为纯文本输出（CLI: --logs-dir，无 --out）→ tee 落盘 .txt
#   * analyze_wide_range.py    本地支持 --log-dir / --out → 落盘 .json + .txt
#
# 用法（cron，每周一 UTC 2:00）：
#   0 2 * * 1 /path/to/scripts/weekly_shadow_review.sh >> /path/to/logs/cron_weekly.log 2>&1
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$PROJECT_ROOT/logs"
WEEK_TAG="$(date -u +%Y%m%d)"
REPORT_DIR="$PROJECT_ROOT/reports/weekly_review_${WEEK_TAG}"

mkdir -p "$REPORT_DIR" "$LOG_DIR"
cd "$PROJECT_ROOT" || { echo "FATAL: cannot cd to $PROJECT_ROOT"; exit 2; }

echo "[$(date -u +%FT%TZ)] weekly_shadow_review start"

# 1. L2 反事实报告（文本）
echo "--- L2 sizing shadow ---"
if [ -f utils/analyze_sizing_shadow.py ]; then
  "$PYTHON_BIN" utils/analyze_sizing_shadow.py --logs-dir "$LOG_DIR" 2>&1 | tee "$REPORT_DIR/l2_counterfactual.txt"
else
  echo "SKIP: utils/analyze_sizing_shadow.py not found" | tee "$REPORT_DIR/l2_counterfactual.txt"
fi

# 2. Wide-range 六项指标（需 exit_audit + wide_range_shadow 数据；缺则跳过并提示）
echo "--- Wide-range loss clustering ---"
if ls "$LOG_DIR"/exit_audit_*.jsonl 1>/dev/null 2>&1 && ls "$LOG_DIR"/wide_range_shadow_*.jsonl 1>/dev/null 2>&1; then
  "$PYTHON_BIN" utils/analyze_wide_range.py --log-dir "$LOG_DIR" --out "$REPORT_DIR/wide_range.json" 2>&1 | tee "$REPORT_DIR/wide_range.txt"
else
  echo "SKIP: no exit_audit / wide_range_shadow records found (P0/P1-B 尚未产出)" | tee "$REPORT_DIR/wide_range.txt"
fi

# 3. 汇总提示
echo "=================================================================="
echo "Weekly shadow review reports saved to: $REPORT_DIR"
echo "  - l2_counterfactual.txt   (L2 反事实：rp_mult 分布 / 尾部削减 / EV 检查)"
echo "  - wide_range.json / .txt  (六项指标：wide vs normal 显著性)"
echo "NOTE: 报告仅供人工 review，不自动触发任何决策变更。"
echo "      L2 若 p90 下降≤10% → 停止 L2，回头查 Wide-range。"
echo "      Wide-range 若 wide 与 normal 无显著差异 → 判别量(ATR_pct)无效，换特征。"
echo "[$(date -u +%FT%TZ)] weekly_shadow_review done"
