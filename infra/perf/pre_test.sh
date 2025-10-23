#!/usr/bin/env bash
# 压测前准备脚本
# 用于备份日志、清理旧数据等

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs"
BACKUP_DIR="perf_results/logs_backup"

echo "=========================================="
echo "压测前准备"
echo "时间戳: $TIMESTAMP"
echo "=========================================="

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 备份当前日志
if [ -f "$LOG_DIR/app.log" ]; then
    LOG_SIZE=$(du -h "$LOG_DIR/app.log" | cut -f1)
    echo "📦 备份当前日志 (大小: $LOG_SIZE)"
    cp "$LOG_DIR/app.log" "$BACKUP_DIR/app_backup_${TIMESTAMP}.log"
    echo "   ✅ 已保存到: $BACKUP_DIR/app_backup_${TIMESTAMP}.log"
    
    # 清空日志文件(保留文件本身)
    echo "🧹 清空日志文件"
    > "$LOG_DIR/app.log"
    echo "   ✅ 日志已清空,准备记录压测数据"
else
    echo "ℹ️  日志文件不存在,跳过备份"
fi

echo ""
echo "=========================================="
echo "✅ 准备完成!"
echo "=========================================="
echo "下一步:"
echo "  1. 确保服务正在运行"
echo "  2. 运行: bash infra/perf/run_baseline.sh"
echo "=========================================="
