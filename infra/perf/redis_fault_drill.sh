#!/usr/bin/env bash
# Redis 故障演练脚本
# 用途：在 Staging 环境模拟 Redis 网络故障，验证系统降级行为
# Redis 服务器: 172.21.48.1:6379
# 
# 使用方法:
#   ./redis_fault_drill.sh block   # 阻断 Redis 连接
#   ./redis_fault_drill.sh unblock # 恢复 Redis 连接
#   ./redis_fault_drill.sh status  # 检查当前规则状态

set -euo pipefail

REDIS_HOST="172.21.48.1"
REDIS_PORT="6379"
RULE_COMMENT="naicha-redis-fault-drill"

function block_redis() {
    echo "🚫 阻断到 Redis ($REDIS_HOST:$REDIS_PORT) 的网络连接..."
    
    # 阻断出站流量
    sudo iptables -A OUTPUT -p tcp -d "$REDIS_HOST" --dport "$REDIS_PORT" \
        -m comment --comment "$RULE_COMMENT" -j REJECT
    
    echo "✅ Redis 连接已阻断"
    echo "📊 开始观察以下日志/指标:"
    echo "   - distributed_lock.client_unavailable"
    echo "   - distributed_lock.redis_unavailable"
    echo "   - menu.cache.version_read_failed"
    echo "   - payment_match API 返回 409 (lock acquisition failed)"
    echo ""
    echo "💡 观察命令:"
    echo "   tail -f logs/app.log | grep -E 'distributed_lock|menu.cache'"
    echo "   curl -X POST http://localhost:8000/api/v1/admin/payments/match (should get 409)"
}

function unblock_redis() {
    echo "🔓 恢复到 Redis ($REDIS_HOST:$REDIS_PORT) 的网络连接..."
    
    # 删除阻断规则
    sudo iptables -D OUTPUT -p tcp -d "$REDIS_HOST" --dport "$REDIS_PORT" \
        -m comment --comment "$RULE_COMMENT" -j REJECT 2>/dev/null || true
    
    echo "✅ Redis 连接已恢复"
    echo "📊 验证恢复:"
    echo "   - 日志中 distributed_lock/menu.cache 警告应停止"
    echo "   - payment_match API 应恢复正常 (200/409 业务逻辑响应)"
    echo "   - Redis 命令延迟恢复正常"
}

function check_status() {
    echo "📋 当前 iptables 规则 (Redis 相关):"
    sudo iptables -L OUTPUT -n -v --line-numbers | grep -E "$REDIS_HOST|$RULE_COMMENT" || echo "  (无 Redis 阻断规则)"
    echo ""
    echo "🔍 测试 Redis 连接:"
    if timeout 2 bash -c "echo > /dev/tcp/$REDIS_HOST/$REDIS_PORT" 2>/dev/null; then
        echo "  ✅ Redis 可达 ($REDIS_HOST:$REDIS_PORT)"
    else
        echo "  ❌ Redis 不可达 ($REDIS_HOST:$REDIS_PORT)"
    fi
}

function show_help() {
    cat << EOF
Redis 故障演练脚本

用法: $0 {block|unblock|status}

命令:
  block     阻断到 Redis 的网络连接 (iptables REJECT)
  unblock   恢复 Redis 网络连接
  status    检查当前 iptables 规则和 Redis 连通性

演练流程建议:
  1. 启动小规模负载 (50-100 并发)
  2. 运行 './redis_fault_drill.sh block' 触发故障
  3. 观察 1-2 分钟日志和指标
  4. 运行 './redis_fault_drill.sh unblock' 恢复
  5. 验证系统恢复正常

关键观察点:
  - 日志: distributed_lock.client_unavailable, menu.cache.version_read_failed
  - 指标: payment_match_lock_failed_total, menu_cache_version_read_failed_total
  - API: 静态码匹配应返回 409, 菜单读取应仍可用 (TTL 缓存)

注意事项:
  - 需要 sudo 权限执行 iptables 命令
  - 仅在 Staging/测试环境执行，禁止在生产环境运行
  - 演练前确认有回滚计划和监控覆盖

EOF
}

case "${1:-help}" in
    block)
        block_redis
        ;;
    unblock)
        unblock_redis
        ;;
    status)
        check_status
        ;;
    *)
        show_help
        exit 1
        ;;
esac
