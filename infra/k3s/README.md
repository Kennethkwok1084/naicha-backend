# K3s 部署清单（Week 0.5 初稿）

> 目标：梳理云端 + 家庭双节点 K3s 集群的部署所需资源，提供可 `kubectl apply --dry-run=client` 校验的初稿。

目录结构：

- `base/`：通用资源（API、Worker、PgBouncer、Redis、Ingress、WAF）。
- `overlays/staging/`：Staging 集群覆盖项。
- `overlays/prod/`：生产集群覆盖项（云端主集群 + 家庭节点）。

---

## 前置依赖

- StorageClass：`local-path`（K3s 默认）或 `longhorn`，需至少 20Gi 可用空间。
- Secret：
  - `naicha-api-secrets`（数据库、Redis、第三方秘钥）。
  - `pgbouncer-auth`（`userlist.txt` 含 HBA 信息）。
  - `redis-auth`（如启用 `requirepass`）。
  - `tls-naicha`（HTTPS 证书，生产需泛域名）。
- ConfigMap：
  - `naicha-waf-snippet`（WAF 规则，可使用 base 提供模板）。
  - `pgbouncer-config`、`redis-config` 由 base 定义。

> ⚠️ 所有 Secret 均需手动创建或由 GitOps 注入，repo 内仅提供 `.example`。

---

## 部署顺序

1. **命名空间与基础对象**
   ```bash
   kubectl create namespace naicha-staging
   kubectl apply --dry-run=client -k infra/k3s/base
   ```
2. **Secrets / ConfigMaps**
   ```bash
   # 复制 example 文件，填写后执行（避免将真实值提交至仓库）
   cp infra/k3s/secrets/naicha-api-secrets.env.example infra/k3s/secrets/naicha-api-secrets.env
   cp infra/k3s/secrets/pgbouncer-userlist.txt.example infra/k3s/secrets/pgbouncer-userlist.txt

   kubectl create secret generic naicha-api-secrets \
     --from-env-file=infra/k3s/secrets/naicha-api-secrets.env \
     -n naicha-staging \
     --dry-run=client -o yaml | kubectl apply -f -

   kubectl create secret generic pgbouncer-auth \
     --from-file=userlist.txt=infra/k3s/secrets/pgbouncer-userlist.txt \
     -n naicha-staging \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
   > 使用 `pg_md5` 生成密码密文示例：`docker run --rm postgres:16-alpine bash -c "pg_md5 your-password"`。
3. **核心服务**
   ```bash
   kubectl apply -k infra/k3s/overlays/staging
   kubectl rollout status deployment/naicha-api -n naicha-staging
   kubectl rollout status deployment/naicha-worker -n naicha-staging
   kubectl rollout status deployment/pgbouncer -n naicha-staging
   kubectl rollout status statefulset/redis -n naicha-staging
   ```
4. **Ingress / WAF**
   ```bash
   kubectl describe ingress naicha-api -n naicha-staging
   kubectl exec -n ingress-nginx deploy/ingress-nginx-controller -- nginx -s reload
   ```
5. **家↔云混合校验（生产）**
   ```bash
   kubectl get nodes -L naicha.io/zone
   kubectl get pods -n naicha-prod -o wide
   ```

---

## 验收清单

- [ ] `kubectl apply --dry-run=client -k infra/k3s/overlays/staging` 无错误。
- [ ] `kubectl apply --dry-run=client -k infra/k3s/overlays/prod` 无错误。
- [ ] PgBouncer 服务监听 `6432`，`SHOW STATS;` 正常。
- [ ] Redis StatefulSet 挂载 PVC（`kubectl get pvc -n <ns>` 显示 `Bound`）。
- [ ] Ingress 生效（`curl https://api.example.com/healthz` 返回 200）。
- [ ] WAF 规则命中测试（`ab -n 100 -c 10` 触发限流日志）。
- [ ] `ws_runner.py` 在混合节点模式下心跳 P95 ≤ 2000ms。

---

## 回滚演练

- **Deployment 回滚**：`kubectl rollout undo deployment/naicha-api -n <ns>`，确认 `kubectl rollout status` 成功。
- **StatefulSet 回滚**：保留 `redis` PVC，使用 `kubectl rollout undo statefulset/redis -n <ns>`，必要时先 `scale 0` 再恢复。
- **ConfigMap / Secret 回滚**：通过 `kubectl get cm/secret -o yaml --revision=<id>` 导出旧版本并重新 apply。
- **Ingress 回退**：保留旧版清单，`kubectl apply -f infra/k3s/base/ingress.yaml --record` 后可使用 `rollout undo`。
- 演练完成后记录在 `doc/runbook.md` 对应章节。

---

## 监控接入

- **Prometheus**：确保 `infra/k8s/prometheus-rules.yaml` 已被 Operator 引用；若使用 kube-prometheus-stack，添加 `ServiceMonitor` 选择器 `app.kubernetes.io/part-of=naicha`。
- **Grafana**：将 `infra/k8s/grafana-dashboard.yaml` 导入实例，分配 `staging` / `prod` 文件夹。
- **Alertmanager**：设置 `naicha-api`/`naicha-worker` 告警接收人，校验 Slack Webhook 可达。
- **自定义指标**：确认 `PROMETHEUS_ENABLED=true`，`locust` 压测时观测 `http_request_duration_seconds`、`celery_task_latency_seconds`。

---

## 后续工作

- 填充 `secrets/*.example` 为实际值并在 CI 中校验格式。
- 与运维确认 TLS 证书分发路径。
- 对齐 `infra/k8s` 现有对象，避免资源重复创建。
