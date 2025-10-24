#!/usr/bin/env bash
# 150 并发压测执行脚本
# 
# 功能: 使用 Locust 对后端进行 150 并发压测，验证 P0 修复效果
# Redis 服务器: 172.21.48.1:6379
# 
# 使用方法:
#   ./run_150_concurrent_test.sh <backend_url> [duration]
#   例如: ./run_150_concurrent_test.sh http://staging.example.com 10m

set -euo pipefail

BACKEND_URL="${1:-http://localhost:8000}"
DURATION="${2:-10m}"
USERS=150
SPAWN_RATE=10
OUTPUT_DIR="../../perf_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_PREFIX="150u_${TIMESTAMP}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 150 并发压测启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "目标后端: $BACKEND_URL"
echo "并发用户: $USERS"
echo "启动速率: $SPAWN_RATE users/s"
echo "测试时长: $DURATION"
echo "结果目录: $OUTPUT_DIR"
echo "Redis 服务器: 172.21.48.1:6379"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Locust 是否安装
if ! command -v locust &> /dev/null; then
    echo "❌ Locust 未安装，请先安装: pip install locust"
    exit 1
fi

# 检查压测脚本是否存在
if [ ! -f "test_payment_only.py" ]; then
    echo "❌ 找不到 test_payment_only.py，请在 infra/perf 目录下执行此脚本"
    exit 1
fi

# 创建结果目录
mkdir -p "$OUTPUT_DIR"

echo "📊 开始压测 (预计运行时间: $DURATION)..."
echo "💡 建议同时监控以下指标:"
echo "   - Prometheus: payment_callback_latency_ms (P95/P99)"
echo "   - Prometheus: order_create_errors_total, payment_callback_errors_total"
echo "   - Prometheus: db_pool_connections_used"
echo "   - Prometheus: payment_match_lock_failed_total"
echo "   - Redis: MONITOR 观察命令延迟"
echo "   - 日志: tail -f logs/app.log | grep -E 'ERROR|WARNING'"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 运行 Locust
locust \
    -f test_payment_only.py \
    --headless \
    --host="$BACKEND_URL" \
    --users="$USERS" \
    --spawn-rate="$SPAWN_RATE" \
    --run-time="$DURATION" \
    --csv="$OUTPUT_DIR/$RESULT_PREFIX" \
    --html="$OUTPUT_DIR/$RESULT_PREFIX.html" \
    --loglevel INFO

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 压测完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 结果文件:"
echo "   - HTML 报告: $OUTPUT_DIR/$RESULT_PREFIX.html"
echo "   - CSV 统计: $OUTPUT_DIR/$RESULT_PREFIX_stats.csv"
echo "   - CSV 历史: $OUTPUT_DIR/$RESULT_PREFIX_stats_history.csv"
echo "   - CSV 失败: $OUTPUT_DIR/$RESULT_PREFIX_failures.csv"
echo ""

# 分析结果
if [ -f "$OUTPUT_DIR/${RESULT_PREFIX}_stats.csv" ]; then
    echo "📊 快速分析 (基于 CSV 统计):"
    echo ""
    
    # 提取关键指标 (假设 CSV 格式: Type,Name,Request Count,Failure Count,...)
    # 注意: 实际 CSV 格式可能不同，需要根据 Locust 版本调整
    awk -F',' 'NR>1 && $1!="Aggregated" {
        total_requests += $3;
        total_failures += $4;
    }
    END {
        error_rate = (total_requests > 0) ? (total_failures / total_requests * 100) : 0;
        printf "   总请求数: %d\n", total_requests;
        printf "   失败请求: %d\n", total_failures;
        printf "   错误率: %.2f%%\n", error_rate;
        printf "\n";
        if (error_rate > 0.5) {
            printf "   ⚠️  错误率超过目标 (0.5%%), 需要排查!\n";
        } else {
            printf "   ✅ 错误率符合目标 (<0.5%%)\n";
        }
    }' "$OUTPUT_DIR/${RESULT_PREFIX}_stats.csv"
    
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 验收检查清单:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[ ] 错误率 < 0.5% (关注 5xx 错误)"
echo "[ ] P99 延迟 < 1000ms (下单与支付回调路径)"
echo "[ ] 无 DB 连接池耗尽错误 (pool wait timeout)"
echo "[ ] 无 Redis 命令超时或连接错误"
echo "[ ] payment_match_lock_failed_total 无异常增长"
echo "[ ] print_job 表无大量 failed 状态堆积"
echo "[ ] 无订单丢失或重复扣款"
echo ""
echo "📖 详细报告请查看: $OUTPUT_DIR/$RESULT_PREFIX.html"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
