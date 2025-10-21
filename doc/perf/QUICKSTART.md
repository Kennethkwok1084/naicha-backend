# Week1 压测快速开始

## 🚀 3 步完成压测

### 1️⃣ 配置环境变量

```bash
# 复制配置模板
cp .env.perf.example .env.perf

# 编辑配置文件，填写实际值
vim .env.perf

# 加载环境变量
source .env.perf
```

### 2️⃣ 执行压测

```bash
# 一键执行完整压测（推荐）
make perf-baseline

# 预计耗时：5-10 分钟
# 输出：perf_results/ 目录下的 HTML 报告和日志
```

### 3️⃣ 查看结果

```bash
# 查看 Locust HTML 报告
open perf_results/locust_100u_*.html

# 查看更新后的基线文档
cat doc/perf-baseline.md

# 验证 Prometheus 指标
curl http://127.0.0.1:8000/metrics | grep order_create_total
```

---

## 📋 必需的环境变量

| 变量名 | 说明 | 示例 |
|-------|------|------|
| `PERF_BASE_URL` | 压测目标地址 | `http://127.0.0.1:8000` |
| `PERF_USER_TOKEN` | 用户 Bearer Token | `Bearer eyJhbGc...` |
| `PERF_SECRET_KEY` | HMAC 密钥 | `super-secret-key` |
| `PERF_ADMIN_TOKEN` | 管理员 Token（可选） | `Bearer eyJhbGc...` |

---

## 📖 详细文档

完整操作指南请查看：**[`doc/perf/week1-guide.md`](./week1-guide.md)**

包含内容：
- ✅ 环境准备与依赖安装
- ✅ 手动执行各个压测模块
- ✅ Prometheus 指标验证方法
- ✅ 结果解读和判断标准
- ✅ 常见问题排查

---

## ⚡ 快速命令参考

```bash
# 仅 Locust 压测
make perf-locust

# 仅 WebSocket 测试
make perf-ws

# 完整压测 + 自动填充文档
make perf-baseline

# 手动解析结果
python infra/perf/parse_results.py --input ./perf_results

# 查看 Prometheus 指标
curl http://127.0.0.1:8000/metrics
```

---

## ✅ 验收清单

- [ ] 环境变量已正确配置
- [ ] `make perf-baseline` 执行成功
- [ ] `doc/perf-baseline.md` 已自动填充
- [ ] HTML 报告可正常打开
- [ ] `/metrics` 端点返回所有必需指标
- [ ] 所有关键接口 P95 达标

完成后即可提交到 Git 🎉
