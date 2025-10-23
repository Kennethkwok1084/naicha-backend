#!/usr/bin/env bash
# 压测快速启动脚本 - 自动加载环境变量并执行压测

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "🚀 压测快速启动"
echo "=========================================="

# 检查 .env.perf 是否存在
if [ ! -f .env.perf ]; then
    echo "❌ 错误：.env.perf 文件不存在"
    echo "请先运行: python scripts/generate_test_tokens.py"
    exit 1
fi

# 加载环境变量
echo "📋 加载环境变量..."
source .env.perf

# 验证必需的环境变量
if [ -z "${PERF_BASE_URL:-}" ]; then
    echo "❌ PERF_BASE_URL 未设置"
    exit 1
fi

if [ -z "${PERF_USER_TOKEN:-}" ]; then
    echo "❌ PERF_USER_TOKEN 未设置"
    exit 1
fi

# 显示配置
echo "✅ 环境变量已加载"
echo "   BASE_URL: $PERF_BASE_URL"
echo "   USER_TOKEN: ${PERF_USER_TOKEN:0:30}..."
echo "   SECRET_KEY: $PERF_SECRET_KEY"
echo ""

# 检查服务是否运行
echo "🔍 检查服务状态..."
if ! curl -s "${PERF_BASE_URL}/healthz" > /dev/null 2>&1; then
    echo "❌ 服务未运行或无法访问: $PERF_BASE_URL"
    echo "请先启动服务: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    exit 1
fi
echo "✅ 服务正常运行"
echo ""

# 执行压测
echo "🚀 开始执行压测..."
bash infra/perf/run_baseline.sh

echo ""
echo "=========================================="
echo "✅ 压测完成！"
echo "=========================================="
