#!/bin/bash
# 仪表盘 HTTP 服务 — 仅本机/内网访问，安全无认证
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT=${1:-8088}
BIND_ADDR="127.0.0.1"

# 获取本机首选IPv4（过滤docker/虚拟网卡，取第一个物理网卡）
get_local_ip() {
    ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1
}
LOCAL_IP=$(get_local_ip || echo "你的IP")

echo "=========================================="
echo "📊 Attribution V2 Dashboard"
echo "=========================================="
echo "访问地址："
echo "  本机:   http://localhost:${PORT}/attribution_v2/dashboard/"
if [[ "$LOCAL_IP" != "你的IP" ]]; then
echo "  内网:   http://${LOCAL_IP}:${PORT}/attribution_v2/dashboard/"
fi
echo ""
echo "绑定接口: ${BIND_ADDR} （仅本机访问，公网不可达）"
echo "按 Ctrl+C 停止服务"
echo "=========================================="

python3 -m http.server "$PORT" --bind "$BIND_ADDR"
