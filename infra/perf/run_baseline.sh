#!/usr/bin/env bash
# Week1 压测基线自动化执行脚本
# 用途：依次执行 Locust、wrk、WebSocket 压测，收集结果并生成 JSON 报告

set -euo pipefail

# ============================================
# 配置项（可通过环境变量覆盖）
# ============================================
PERF_BASE_URL="${PERF_BASE_URL:-http://127.0.0.1:8000}"
PERF_USER_TOKEN="${PERF_USER_TOKEN:-}"
PERF_ADMIN_TOKEN="${PERF_ADMIN_TOKEN:-}"
PERF_SECRET_KEY="${PERF_SECRET_KEY:-}"
OUTPUT_DIR="${OUTPUT_DIR:-./perf_results}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 并发配置
LOCUST_USERS_100=100
# LOCUST_USERS_200=200  # 暂时禁用高并发测试
# LOCUST_USERS_500=500  # 暂时禁用高并发测试
LOCUST_SPAWN_RATE=20
LOCUST_DURATION=30s

WS_CONNECTIONS=200
WS_DURATION=120

# ============================================
# 前置检查
# ============================================
echo "=========================================="
echo "Week1 压测基线执行脚本"
echo "时间戳: $TIMESTAMP"
echo "=========================================="

if [ -z "$PERF_BASE_URL" ]; then
    echo "❌ 错误：PERF_BASE_URL 未设置"
    exit 1
fi

if [ -z "$PERF_USER_TOKEN" ]; then
    echo "⚠️  警告：PERF_USER_TOKEN 未设置，下单接口将无法测试"
fi

if [ -z "$PERF_SECRET_KEY" ]; then
    echo "⚠️  警告：PERF_SECRET_KEY 未设置，支付回调接口将跳过"
fi

# 检查依赖
if ! command -v locust &> /dev/null; then
    echo "❌ locust 未安装，请运行: pip install locust"
    exit 1
fi

if ! command -v python &> /dev/null; then
    echo "❌ python 未安装"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# ============================================
# 1. Locust 压测
# ============================================
echo ""
echo "📊 [1/4] 开始 Locust 压测..."

for USERS in $LOCUST_USERS_100; do
    echo "  - 并发: ${USERS} 用户"
    REPORT_PREFIX="${OUTPUT_DIR}/locust_${USERS}u_${TIMESTAMP}"
    
    locust -f infra/perf/locustfile.py \
        --headless \
        --host "$PERF_BASE_URL" \
        --users "$USERS" \
        --spawn-rate "$LOCUST_SPAWN_RATE" \
        --run-time "$LOCUST_DURATION" \
        --html "${REPORT_PREFIX}.html" \
        --csv "${REPORT_PREFIX}" \
        2>&1 | tee "${REPORT_PREFIX}.log"
    
    echo "  ✅ 完成: ${USERS} 并发压测"
done

# ============================================
# 2. wrk 基线测试（如果已安装）
# ============================================
echo ""
echo "📊 [2/4] 开始 wrk 基线测试..."

if command -v wrk &> /dev/null; then
    WRK_OUTPUT="${OUTPUT_DIR}/wrk_${TIMESTAMP}.txt"
    
    echo "  - 测试接口: GET /api/v1/menu"
    wrk -t4 -c100 -d30s \
        -s infra/perf/scripts/menu.lua \
        "$PERF_BASE_URL" \
        2>&1 | tee -a "$WRK_OUTPUT"
    
    if [ -n "$PERF_USER_TOKEN" ]; then
        echo "  - 测试接口: POST /api/v1/orders"
        export WRK_BEARER_TOKEN="$PERF_USER_TOKEN"
        wrk -t2 -c30 -d60s \
            -s infra/perf/scripts/order_create.lua \
            "$PERF_BASE_URL" \
            2>&1 | tee -a "$WRK_OUTPUT"
    fi
    
    echo "  ✅ wrk 测试完成"
else
    echo "  ⚠️  wrk 未安装，跳过基线测试"
fi

# ============================================
# 3. WebSocket 连接测试
# ============================================
echo ""
echo "📊 [3/4] 开始 WebSocket 压测..."

if [ -n "$PERF_ADMIN_TOKEN" ]; then
    WS_OUTPUT="${OUTPUT_DIR}/ws_${TIMESTAMP}.txt"
    
    # 构建 WebSocket URL
    WS_URL="${PERF_BASE_URL/http/ws}/ws/merchant"
    
    python infra/perf/ws_runner.py \
        --connections "$WS_CONNECTIONS" \
        --duration "$WS_DURATION" \
        --base-url "$WS_URL" \
        --token "$PERF_ADMIN_TOKEN" \
        2>&1 | tee "$WS_OUTPUT"
    
    echo "  ✅ WebSocket 测试完成"
else
    echo "  ⚠️  PERF_ADMIN_TOKEN 未设置，跳过 WebSocket 测试"
fi

# ============================================
# 4. 收集 Prometheus 指标（可选）
# ============================================
echo ""
echo "📊 [4/4] 收集 Prometheus 指标..."

METRICS_OUTPUT="${OUTPUT_DIR}/prometheus_metrics_${TIMESTAMP}.txt"
if curl -s "${PERF_BASE_URL}/metrics" -o "$METRICS_OUTPUT" 2>/dev/null; then
    echo "  ✅ 指标已保存到: $METRICS_OUTPUT"
else
    echo "  ⚠️  无法访问 /metrics 端点"
fi

# ============================================
# 汇总报告
# ============================================
echo ""
echo "=========================================="
echo "✅ 压测完成！"
echo "=========================================="
echo "结果文件保存在: $OUTPUT_DIR"
echo ""
echo "下一步："
echo "  1. 运行解析脚本填充 perf-baseline.md:"
echo "     python infra/perf/parse_results.py --input $OUTPUT_DIR"
echo ""
echo "  2. 查看 Locust HTML 报告:"
echo "     open ${OUTPUT_DIR}/locust_*_${TIMESTAMP}.html"
echo ""
echo "  3. 检查 Prometheus 指标:"
echo "     cat ${METRICS_OUTPUT}"
echo "=========================================="
