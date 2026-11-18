#!/usr/bin/env bash
# daily_exit_audit.sh — 每日 P0 Exit Audit 对账（cron 调用）
# ============================================================
# 功能：
#   1. 跑 utils/analyze_exit_audit.py，文本报告落盘 reports/exit_audit_YYYYMMDD.txt
#   2. 分析器执行失败（非零退出）→ 写 logs/ALERT_*.log + 退出码非零 + 可选 webhook
#
# 适配说明（本地版）：
#   本地 utils/analyze_exit_audit.py 输出**文本报告**（CLI 为 --logs-dir，无 --out）。
#   因此本脚本不再解析 JSON。Dola 原版的 JSON 对账告警（reconciliation_mismatch /
#   unknown_pct / incomplete_pct）依赖其自有 exit_audit schema（attribution_status /
#   incomplete 字段），仓库现有 audit_owned_closed_trades() 产出的日志无这些字段，
#   无法计算，故告警口径退化为「分析器执行失败即告警」。
#
# 用法（cron）：
#   0 1 * * * /path/to/scripts/daily_exit_audit.sh >> /path/to/logs/cron_daily.log 2>&1
#
# 环境变量（可选）：
#   PROJECT_ROOT    项目根目录（默认脚本所在目录的上一级）
#   ALERT_WEBHOOK   告警 webhook URL（飞书/钉钉/Slack，留空则只写文件）
#   PYTHON_BIN      python 路径（默认 python3）
#   DAYS            仅分析最近 N 个审计文件（默认空 = 全部历史）
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="$PROJECT_ROOT/logs"
REPORT_DIR="$PROJECT_ROOT/reports"
DATE_TAG="$(date -u +%Y%m%d)"
REPORT_FILE="$REPORT_DIR/exit_audit_${DATE_TAG}.txt"
ALERT_FILE="$LOG_DIR/ALERT_exit_audit_${DATE_TAG}.log"

mkdir -p "$REPORT_DIR" "$LOG_DIR"

notify() {
  local msg="$1"
  if [ -n "${ALERT_WEBHOOK:-}" ]; then
    curl -sS -X POST -H "Content-Type: application/json" \
      -d "{\"text\": \"[Exit Audit Alert] $msg\"}" \
      "$ALERT_WEBHOOK" >/dev/null 2>&1 || echo "WARN: webhook notify failed" >> "$ALERT_FILE"
  fi
}

echo "[$(date -u +%FT%TZ)] daily_exit_audit start, PROJECT_ROOT=$PROJECT_ROOT"

cd "$PROJECT_ROOT" || { echo "FATAL: cannot cd to $PROJECT_ROOT"; exit 2; }

if [ ! -f utils/analyze_exit_audit.py ]; then
  echo "[$(date -u +%FT%TZ)] FATAL: utils/analyze_exit_audit.py not found" | tee -a "$ALERT_FILE"
  exit 2
fi

# 1. 跑分析（文本报告落盘；tee 同时写 cron 日志）
DAYS_ARG=()
if [ -n "${DAYS:-}" ]; then DAYS_ARG=(--days "$DAYS"); fi

"$PYTHON_BIN" utils/analyze_exit_audit.py --logs-dir "$LOG_DIR" "${DAYS_ARG[@]}" | tee "$REPORT_FILE"
RC="${PIPESTATUS[0]}"
if [ "$RC" -ne 0 ]; then
  MSG="CRITICAL: analyze_exit_audit.py exited with code $RC (report=$REPORT_FILE)"
  echo "[$(date -u +%FT%TZ)] ALERT: $MSG" | tee -a "$ALERT_FILE"
  notify "$MSG"
  exit 1
fi

echo "[$(date -u +%FT%TZ)] daily_exit_audit OK, report=$REPORT_FILE"
exit 0
