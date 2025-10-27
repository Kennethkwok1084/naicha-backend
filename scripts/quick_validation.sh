#!/bin/bash
# 快速验证脚本 - 用于本地环境快速检查系统可用性
# 使用方法: ./scripts/quick_validation.sh [base_url]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="${1:-http://localhost:8000}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 naicha-backend 快速验证"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "目标环境: $BASE_URL"
echo ""

# 检查依赖
if ! command -v curl &> /dev/null; then
    echo -e "${RED}❌ 未安装 curl，请先安装${NC}"
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo -e "${YELLOW}⚠️  未安装 jq，JSON 输出将不会格式化${NC}"
    JQ_INSTALLED=false
else
    JQ_INSTALLED=true
fi

# 测试计数器
PASSED=0
FAILED=0

# 辅助函数：执行测试
run_test() {
    local test_name="$1"
    local url="$2"
    local method="${3:-GET}"
    local data="${4:-}"
    local headers="${5:-}"
    local expected_status="${6:-200}"
    
    echo -n "🔍 $test_name ... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$url" $headers)
    else
        response=$(curl -s -w "\n%{http_code}" -X POST "$url" \
            -H "Content-Type: application/json" \
            $headers \
            -d "$data")
    fi
    
    # 提取状态码（最后一行）
    status_code=$(echo "$response" | tail -n1)
    # 提取响应体（除最后一行）
    body=$(echo "$response" | sed '$d')
    
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}✅ PASS${NC} (HTTP $status_code)"
        ((PASSED++))
        
        # 如果安装了 jq，格式化输出 JSON
        if [ "$JQ_INSTALLED" = true ] && [ -n "$body" ]; then
            echo "$body" | jq '.' 2>/dev/null | head -n 5
            echo "..."
        fi
    else
        echo -e "${RED}❌ FAIL${NC} (期望 HTTP $expected_status，实际 HTTP $status_code)"
        ((FAILED++))
        echo "响应: $body" | head -n 3
    fi
    echo ""
}

# ============================================
# 基础健康检查
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 第一阶段: 基础健康检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

run_test "健康检查" "$BASE_URL/health"
run_test "获取门店状态" "$BASE_URL/api/v1/shop/status"
run_test "获取菜单" "$BASE_URL/api/v1/menu"

# ============================================
# 认证功能检查
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 第二阶段: 认证功能检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 管理员登录
ADMIN_LOGIN_DATA='{"username":"admin","password":"admin123"}'
run_test "管理员登录" "$BASE_URL/api/v1/admin/login" "POST" "$ADMIN_LOGIN_DATA"

# 提取 Token (如果安装了 jq)
if [ "$JQ_INSTALLED" = true ]; then
    ADMIN_TOKEN=$(curl -s -X POST "$BASE_URL/api/v1/admin/login" \
        -H "Content-Type: application/json" \
        -d "$ADMIN_LOGIN_DATA" | jq -r '.access_token')
    
    if [ "$ADMIN_TOKEN" != "null" ] && [ -n "$ADMIN_TOKEN" ]; then
        echo -e "${GREEN}✅ 成功获取管理员 Token${NC}"
        echo ""
        
        # 测试需要认证的接口
        run_test "获取订单列表 (需要 Token)" \
            "$BASE_URL/api/v1/admin/orders?limit=5" \
            "GET" \
            "" \
            "-H 'Authorization: Bearer $ADMIN_TOKEN'"
    else
        echo -e "${YELLOW}⚠️  无法获取 Token，跳过认证测试${NC}"
        echo ""
    fi
fi

# 用户登录
USER_LOGIN_DATA='{"code":"mock-user-001","nickname":"测试用户","avatar_url":"https://example.com/avatar.png"}'
run_test "用户登录" "$BASE_URL/api/v1/users/login" "POST" "$USER_LOGIN_DATA"

# ============================================
# API 错误处理检查
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🛡️  第三阶段: 错误处理检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

run_test "无效登录凭据" \
    "$BASE_URL/api/v1/admin/login" \
    "POST" \
    '{"username":"admin","password":"wrong"}' \
    "" \
    "401"

run_test "缺少认证头" \
    "$BASE_URL/api/v1/me/profile" \
    "GET" \
    "" \
    "" \
    "401"

run_test "不存在的资源" \
    "$BASE_URL/api/v1/orders/99999999" \
    "GET" \
    "" \
    "" \
    "404"

# ============================================
# 性能基准检查
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ 第四阶段: 性能基准检查 (连续 10 次请求)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo -n "测试菜单接口性能 ... "
times=()
for i in {1..10}; do
    time=$(curl -s -w "%{time_total}" -o /dev/null "$BASE_URL/api/v1/menu")
    times+=($time)
done

# 计算平均值
total=0
for t in "${times[@]}"; do
    total=$(echo "$total + $t" | bc)
done
avg=$(echo "scale=3; $total / 10" | bc)
avg_ms=$(echo "$avg * 1000" | bc)

echo -e "${GREEN}✅ 完成${NC}"
echo "平均响应时间: ${avg_ms}ms"

if (( $(echo "$avg_ms < 100" | bc -l) )); then
    echo -e "${GREEN}✅ 性能优秀 (< 100ms)${NC}"
elif (( $(echo "$avg_ms < 500" | bc -l) )); then
    echo -e "${YELLOW}⚠️  性能一般 (100-500ms)${NC}"
else
    echo -e "${RED}❌ 性能较差 (> 500ms)${NC}"
fi
echo ""

# ============================================
# 总结报告
# ============================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 验证总结"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "通过测试: ${GREEN}$PASSED${NC}"
echo "失败测试: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ 所有测试通过！系统可用。${NC}"
    echo ""
    echo "📋 下一步:"
    echo "   1. 导出 OpenAPI 文档: make export-openapi"
    echo "   2. 导入 Apifox 进行完整 API 测试"
    echo "   3. 执行性能压测: cd infra/perf && ./run_150_concurrent_test.sh"
    echo "   4. 查看上线指南: doc/pre-production-validation-guide.md"
    exit 0
else
    echo -e "${RED}❌ 发现 $FAILED 个失败测试！请检查系统配置。${NC}"
    echo ""
    echo "🔧 排查建议:"
    echo "   1. 检查服务是否正常运行: curl $BASE_URL/health"
    echo "   2. 查看日志: tail -f logs/app.log"
    echo "   3. 检查数据库连接: alembic current"
    echo "   4. 确认测试数据已创建: make seed-data"
    exit 1
fi
