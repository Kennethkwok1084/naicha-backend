# V3.0.1 上线准备完成报告

**Redis 服务器**: 172.21.48.1:6379  
**生成时间**: 2025-10-25  
**状态**: ✅ 就绪待压测验证

---

## 📋 已完成工作概览

### 1. 压测与演练脚本 ✅
| 脚本 | 路径 | 用途 |
|------|------|------|
| Redis 故障演练 | `infra/perf/redis_fault_drill.sh` | 模拟 Redis 网络故障（iptables 阻断/恢复） |
| 150 并发压测 | `infra/perf/run_150_concurrent_test.sh` | Locust 压测自动化脚本 |

### 2. 监控配置 ✅
| 文件 | 路径 | 说明 |
|------|------|------|
| Prometheus 告警规则 | `infra/k3s/prometheus-rules.yaml` | 20+ 条告警规则（P0/P1/P2） |
| Grafana Dashboard | `infra/k3s/grafana-dashboard.json` | 9 个面板覆盖业务/延迟/并发安全/基础设施 |

### 3. 上线文档 ✅
| 文档 | 路径 | 说明 |
|------|------|------|
| 生产配置审查清单 | `doc/production-readiness-checklist.md` | 10 大类 60+ 检查项 |
| 回滚应急 Runbook | `doc/rollback-runbook.md` | 回滚步骤 + 故障排查 + 应急联系 |

---

## 🚀 下一步执行指南

### Step 1: Redis 故障演练（Staging）

#### 执行命令
```bash
cd /home/kwok/coder/naicha-backend/infra/perf

# 1. 检查当前 Redis 连通性
./redis_fault_drill.sh status

# 2. 启动小规模负载（另一个终端）
cd .. && locust -f infra/perf/test_payment_only.py \
  --headless -u 50 -r 5 -t 5m --host=http://staging.example.com

# 3. 触发 Redis 故障（运行 1-2 分钟后执行）
./redis_fault_drill.sh block

# 4. 观察降级行为（持续 2 分钟）
tail -f ../../logs/app.log | grep -E "distributed_lock|menu.cache"

# 5. 恢复 Redis 连接
./redis_fault_drill.sh unblock

# 6. 验证系统恢复
./redis_fault_drill.sh status
```

#### 验收标准
- [ ] 日志中出现 `distributed_lock.client_unavailable`
- [ ] 日志中出现 `menu.cache.version_read_failed`
- [ ] 静态码匹配 API 返回 409 (Concurrent match request detected)
- [ ] 菜单读取 API 仍返回 200 (TTL 缓存降级)
- [ ] 恢复后 1 分钟内告警消失

---

### Step 2: 150 并发压测（Staging）

#### 执行命令
```bash
cd /home/kwok/coder/naicha-backend/infra/perf

# 运行 150 并发压测（10 分钟）
./run_150_concurrent_test.sh http://staging.example.com 10m

# 或者自定义参数
locust -f test_payment_only.py \
  --headless \
  --host=http://staging.example.com \
  --users=150 \
  --spawn-rate=10 \
  --run-time=10m \
  --csv=../../perf_results/150u_$(date +%Y%m%d_%H%M%S) \
  --html=../../perf_results/150u_$(date +%Y%m%d_%H%M%S).html
```

#### 同步监控观察
在压测过程中，同时监控以下指标：

**Prometheus 关键指标** (http://<prometheus_url>/graph):
```promql
# 错误率（目标 < 0.5%）
rate(order_create_errors_total[1m]) / rate(order_create_total[1m])
rate(payment_callback_total{result="error"}[1m]) / rate(payment_callback_total[1m])

# P99 延迟（目标 < 1000ms）
histogram_quantile(0.99, rate(order_create_latency_seconds_bucket[5m]))
histogram_quantile(0.99, rate(payment_callback_latency_ms_bucket[5m]))

# DB 连接池使用率（目标 < 85%）
db_pool_connections_used / (db_pool_size + db_pool_max_overflow)

# 分布式锁失败率（目标 < 5/min）
rate(payment_match_attempt_total{result="lock_failed"}[1m])
```

**日志实时监控**:
```bash
# 错误日志
kubectl logs -n staging -l app=naicha-backend -f | grep ERROR

# 慢查询
kubectl logs -n staging -l app=naicha-backend -f | grep "slow_query"

# 连接池告警
kubectl logs -n staging -l app=naicha-backend -f | grep "pool.*timeout"
```

#### 验收标准
- [ ] 错误率 < 0.5% (关注 5xx 错误)
- [ ] P99 延迟 < 1000ms (下单与支付回调)
- [ ] 无 DB 连接池耗尽错误
- [ ] 无 Redis 连接超时
- [ ] `payment_match_lock_failed_total` 无异常增长
- [ ] 无订单丢失或重复扣款

---

### Step 3: 部署监控配置

#### Prometheus 告警规则
```bash
# 应用告警规则到 Prometheus
kubectl apply -f infra/k3s/prometheus-rules.yaml -n monitoring

# 或者如果使用 Prometheus Operator
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: naicha-backend-alerts
  namespace: monitoring
spec:
  $(cat infra/k3s/prometheus-rules.yaml)
EOF

# 验证规则加载成功
curl http://<prometheus_url>/api/v1/rules | jq '.data.groups[] | select(.name=="naicha_backend_alerts")'
```

#### Grafana Dashboard
```bash
# 方式 1: 通过 Grafana UI 导入
# 1. 登录 Grafana (http://<grafana_url>)
# 2. 点击 "+" → "Import"
# 3. 上传 infra/k3s/grafana-dashboard.json
# 4. 选择数据源: Prometheus
# 5. 点击 "Import"

# 方式 2: 通过 API 导入
curl -X POST http://<grafana_url>/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_token>" \
  -d @infra/k3s/grafana-dashboard.json

# 验证 Dashboard 可访问
# 访问: http://<grafana_url>/d/naicha-backend-p0
```

---

### Step 4: 生产配置审查

#### 执行检查清单
按照 `doc/production-readiness-checklist.md` 逐项检查：

**快速自动检查脚本**:
```bash
#!/bin/bash
# 保存为 check_prod_config.sh

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 生产环境配置检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查环境变量（在 Pod 内执行）
kubectl exec -n production <pod_name> -- bash -c '
echo "=== 限流配置 ==="
echo "RATE_LIMIT_DEFAULT_LIMITS: $RATE_LIMIT_DEFAULT_LIMITS"
echo "PERF_DISABLE_HTTP_OVERHEADS: ${PERF_DISABLE_HTTP_OVERHEADS:-未设置(正确)}"

echo ""
echo "=== JWT 配置 ==="
echo "JWT_EXPIRE_MINUTES: $JWT_EXPIRE_MINUTES"

echo ""
echo "=== Redis 配置 ==="
echo "CELERY_BROKER_URL: $CELERY_BROKER_URL"
'

# 检查 Redis 连通性
echo ""
echo "=== Redis 连通性 ==="
redis-cli -h 172.21.48.1 PING && echo "✅ Redis 可达" || echo "❌ Redis 不可达"

# 检查数据库迁移
echo ""
echo "=== 数据库迁移状态 ==="
kubectl exec -n production <pod_name> -- alembic current

# 检查 Prometheus 指标暴露
echo ""
echo "=== Prometheus 指标 ==="
curl -s http://<service_url>/metrics | grep -c "order_create_total" && echo "✅ 指标已暴露" || echo "❌ 指标未暴露"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

#### 关键检查项
- [ ] 限流已启用 (`PERF_DISABLE_HTTP_OVERHEADS` 未设置或为 0)
- [ ] DB 连接池配置正确 (`DATABASE_POOL_SIZE=20`, `DATABASE_MAX_OVERFLOW=30`)
- [ ] JWT 有效期为 1 天 (`JWT_EXPIRE_MINUTES=1440`，如需更短请在灰度前调整)
- [ ] Redis 连接正常 (172.21.48.1:6379)
- [ ] 数据库迁移版本正确 (20251024_0002)
- [ ] Prometheus 指标可访问

---

### Step 5: 灰度上线计划

#### 上线节奏建议
```
Day 0 (今天)
  └─ Staging 验证
      ├─ Redis 故障演练 ✅
      ├─ 150 并发压测 ✅
      ├─ 监控配置部署 ✅
      └─ 配置审查完成 ✅

Day 1 (明天)
  └─ 生产灰度 10% 流量
      ├─ 08:00 部署到生产环境
      ├─ 09:00 灰度 10% 用户流量
      ├─ 全天密切监控 (每 2 小时检查指标)
      └─ 18:00 评审 (无严重问题则继续)

Day 2
  └─ 扩大至 50% 流量
      ├─ 10:00 扩大至 50%
      ├─ 全天监控
      └─ 18:00 评审

Day 3
  └─ 全量上线
      ├─ 10:00 全量 100%
      ├─ 持续监控 72 小时
      └─ Day 5 收尾评审
```

#### 灰度流量控制（示例）
```yaml
# Kubernetes Ingress 灰度配置
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: naicha-backend-canary
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "10"  # 10% 流量
spec:
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: naicha-backend-v3
            port:
              number: 8000
```

---

## 📊 监控面板速查

### Grafana Dashboard 面板说明

| 面板名称 | 观察指标 | 正常阈值 |
|---------|---------|---------|
| 请求吞吐量 (QPS) | 下单/支付回调 QPS | - |
| 错误率 | 下单/支付回调错误率 | < 0.5% |
| 下单延迟 | P50/P95/P99 | P99 < 1s |
| 支付回调延迟 | P50/P95/P99 | P99 < 1000ms |
| 静态码匹配结果分布 | 成功/锁失败/多候选 | 锁失败 < 5/min |
| DB 连接池使用率 | 使用率 | < 85% |
| 打印任务失败监控 | 重试耗尽/执行失败 | < 1/min |
| 菜单缓存监控 | 命中/未命中/版本同步失败 | 同步失败 < 5/min |
| Redis 命令延迟 | P99 延迟 | < 10ms |

### Prometheus 告警级别

| 级别 | 响应时间 | 示例告警 |
|------|---------|---------|
| **P0 (Critical)** | 5 分钟内 | HighOrderCreateErrorRate, RedisDown |
| **P1 (Warning)** | 15 分钟内 | DistributedLockAcquisitionFailed, DatabaseConnectionPoolNearLimit |
| **P2 (Info)** | 1 小时内 | HighOrderCreateLatency, CeleryQueueBacklog |

---

## 🔧 常用命令速查

### 压测相关
```bash
# Redis 故障演练
cd infra/perf
./redis_fault_drill.sh block   # 阻断 Redis
./redis_fault_drill.sh unblock # 恢复 Redis
./redis_fault_drill.sh status  # 检查状态

# 150 并发压测
./run_150_concurrent_test.sh http://staging.example.com 10m
```

### 监控相关
```bash
# 查看 Prometheus 告警
curl http://<prometheus_url>/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing")'

# 查询关键指标
curl "http://<prometheus_url>/api/v1/query?query=rate(order_create_errors_total[5m])"

# 查看 Grafana Dashboard
open http://<grafana_url>/d/naicha-backend-p0
```

### 故障排查
```bash
# 检查 Redis 连通性
redis-cli -h 172.21.48.1 PING

# 检查数据库迁移状态
kubectl exec -n production <pod> -- alembic current

# 查看实时错误日志
kubectl logs -n production -l app=naicha-backend -f | grep ERROR

# 查看 DB 连接池状态
curl http://<service_url>/metrics | grep db_pool_connections_used
```

### 回滚操作
```bash
# Kubernetes 快速回滚
kubectl rollout undo deployment/naicha-backend -n production
kubectl rollout status deployment/naicha-backend -n production

# 数据库迁移回滚（谨慎操作）
kubectl exec -it -n production <pod> -- alembic downgrade -1
```

---

## ✅ 验收签字表

| 检查项 | 负责人 | 完成状态 | 签名 | 日期 |
|--------|--------|---------|------|------|
| Redis 故障演练通过 | ________ | [ ] | ________ | ________ |
| 150 并发压测通过 | ________ | [ ] | ________ | ________ |
| Prometheus 告警规则生效 | ________ | [ ] | ________ | ________ |
| Grafana Dashboard 可访问 | ________ | [ ] | ________ | ________ |
| 生产配置审查完成 | ________ | [ ] | ________ | ________ |
| 回滚流程演练完成 | ________ | [ ] | ________ | ________ |
| On-call 轮值表更新 | ________ | [ ] | ________ | ________ |
| 应急联系方式确认 | ________ | [ ] | ________ | ________ |

---

## 📞 应急联系方式

**Redis 服务器故障**: ____________  
**数据库故障**: ____________  
**技术 On-call**: ____________  
**产品负责人**: ____________  

---

**文档版本**: V1.0  
**生成时间**: 2025-10-25  
**下次更新**: 压测完成后
