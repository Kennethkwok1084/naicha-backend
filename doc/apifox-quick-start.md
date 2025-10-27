# Apifox API 测试快速上手指南

**适用系统**: naicha-backend V3.0.1+  
**工具**: Apifox (https://apifox.com)  
**预计时间**: 30 分钟

---

## 📋 目录

1. [为什么选择 Apifox](#为什么选择-apifox)
2. [安装 Apifox](#安装-apifox)
3. [导入 OpenAPI 文档](#导入-openapi-文档)
4. [配置测试环境](#配置测试环境)
5. [创建测试用例](#创建测试用例)
6. [编写自动化脚本](#编写自动化脚本)
7. [执行测试并生成报告](#执行测试并生成报告)
8. [CI/CD 集成](#cicd-集成)
9. [实战案例](#实战案例)

---

## 为什么选择 Apifox

相比 Postman 的优势:
- ✅ **原生支持 OpenAPI 3.0** - 自动同步文档和测试
- ✅ **内置 Mock 服务** - 前后端并行开发
- ✅ **团队协作免费** - 多人共享接口和用例
- ✅ **本地化支持** - 中文界面和文档
- ✅ **自动化测试** - 内置测试集和 CI/CD 集成

---

## 安装 Apifox

### 桌面版 (推荐)

1. 访问 https://apifox.com/download/
2. 下载对应操作系统版本:
   - Windows: `Apifox-Setup-x.x.x.exe`
   - macOS: `Apifox-x.x.x.dmg`
   - Linux: `Apifox-x.x.x.AppImage`
3. 安装并注册账号

### Web 版

直接访问 https://app.apifox.com (需注册账号)

---

## 导入 OpenAPI 文档

### 步骤 1: 导出 OpenAPI 文档

从本地或 Staging 环境导出:

```bash
# 方法 1: 从运行中的服务
curl http://localhost:8000/openapi.json > naicha-openapi.json

# 方法 2: 从 Staging 环境
curl https://staging-api.example.com/openapi.json > naicha-openapi.json

# 方法 3: 从代码生成
python3 << 'EOF'
from app.main import app
import json

with open('naicha-openapi.json', 'w', encoding='utf-8') as f:
    json.dump(app.openapi(), f, indent=2, ensure_ascii=False)
print("✅ OpenAPI 文档已生成: naicha-openapi.json")
EOF
```

### 步骤 2: 创建 Apifox 项目

1. 打开 Apifox
2. 点击 **"新建项目"**
3. 填写项目信息:
   - 项目名称: `naicha-backend`
   - 项目描述: `智能奶茶档口系统后端 API`
   - 选择 **"导入数据"**

### 步骤 3: 导入 OpenAPI

1. 选择 **"OpenAPI / Swagger"**
2. 点击 **"选择文件"** → 选择 `naicha-openapi.json`
3. 点击 **"确定"** 开始导入
4. 导入完成后，Apifox 会自动生成:
   - 所有 API 接口 (40+ 个)
   - 数据模型 (Schemas)
   - 示例请求和响应

---

## 配置测试环境

### 步骤 1: 创建环境

点击右上角 **"环境管理"** → **"新建环境"**

#### 本地环境 (Local)

```json
{
  "name": "Local",
  "variables": [
    {
      "key": "base_url",
      "value": "http://localhost:8000",
      "description": "API 基础 URL"
    },
    {
      "key": "admin_username",
      "value": "admin",
      "description": "管理员用户名"
    },
    {
      "key": "admin_password",
      "value": "admin123",
      "description": "管理员密码 (仅本地测试用)"
    },
    {
      "key": "user_openid",
      "value": "mock-user-001",
      "description": "测试用户 OpenID"
    },
    {
      "key": "admin_token",
      "value": "",
      "description": "管理员 JWT Token (自动更新)"
    },
    {
      "key": "user_token",
      "value": "",
      "description": "用户 JWT Token (自动更新)"
    }
  ]
}
```

#### Staging 环境

```json
{
  "name": "Staging",
  "variables": [
    {
      "key": "base_url",
      "value": "https://staging-api.example.com",
      "description": "Staging API 基础 URL"
    },
    {
      "key": "admin_username",
      "value": "admin",
      "description": "Staging 管理员用户名"
    },
    {
      "key": "admin_password",
      "value": "<从密钥管理获取>",
      "description": "Staging 管理员密码"
    },
    {
      "key": "user_openid",
      "value": "<真实微信 OpenID>",
      "description": "测试用户 OpenID"
    },
    {
      "key": "admin_token",
      "value": "",
      "description": "管理员 JWT Token (自动更新)"
    },
    {
      "key": "user_token",
      "value": "",
      "description": "用户 JWT Token (自动更新)"
    }
  ]
}
```

#### 生产环境 (仅查看，禁止测试)

```json
{
  "name": "Production (Read-Only)",
  "variables": [
    {
      "key": "base_url",
      "value": "https://api.example.com",
      "description": "生产 API (仅查看，禁止测试)"
    }
  ]
}
```

### 步骤 2: 设置默认环境

点击环境下拉框 → 选择 **"Local"** 作为默认环境

---

## 创建测试用例

### 方式 1: 使用接口直接测试

1. 在左侧接口列表中选择 **"POST /api/v1/admin/login"**
2. 点击 **"修改文档"** 标签
3. 在 **"请求示例"** 中填写:
   ```json
   {
     "username": "{{admin_username}}",
     "password": "{{admin_password}}"
   }
   ```
4. 点击 **"发送"** 按钮
5. 检查响应:
   - 状态码: 200
   - 响应体包含: `access_token`

### 方式 2: 创建测试用例集

1. 点击 **"测试管理"** → **"新建测试集"**
2. 测试集名称: `核心业务流程`
3. 点击 **"添加测试用例"**

#### 用例 1: 管理员登录

```yaml
用例名称: 管理员登录成功
测试步骤:
  1. 发送 POST /api/v1/admin/login
  2. 请求体: {"username": "{{admin_username}}", "password": "{{admin_password}}"}
预期结果:
  - 状态码: 200
  - 响应体包含 access_token 字段
  - token 长度 > 100
后置操作:
  - 保存 token 到环境变量 admin_token
```

#### 用例 2: 创建订单

```yaml
用例名称: 用户下单成功
前置条件: 
  - 用户已登录 (user_token 存在)
测试步骤:
  1. 发送 POST /api/v1/orders
  2. Headers: Authorization: Bearer {{user_token}}
  3. Headers: X-Idempotency-Key: test-{{$timestamp}}
  4. 请求体: 
     {
       "items": [{"product_id": 1, "quantity": 1}],
       "order_type": "pickup"
     }
预期结果:
  - 状态码: 201
  - 响应体包含 order_id
  - status 为 "pending_payment"
后置操作:
  - 保存 order_id 到环境变量
```

---

## 编写自动化脚本

### 前置脚本 (Pre-request Script)

#### 自动登录获取 Token

在任何需要 Admin Token 的接口添加前置脚本:

```javascript
// 检查 token 是否已存在且未过期
const token = pm.environment.get('admin_token');
const tokenExpiry = pm.environment.get('admin_token_expiry');
const now = Date.now();

if (!token || !tokenExpiry || now > tokenExpiry) {
    console.log('🔄 Token 不存在或已过期，重新登录...');
    
    pm.sendRequest({
        url: pm.environment.get('base_url') + '/api/v1/admin/login',
        method: 'POST',
        header: {
            'Content-Type': 'application/json',
        },
        body: {
            mode: 'raw',
            raw: JSON.stringify({
                username: pm.environment.get('admin_username'),
                password: pm.environment.get('admin_password')
            })
        }
    }, function (err, res) {
        if (!err && res.code === 200) {
            const responseJson = res.json();
            const newToken = responseJson.access_token;
            
            // 保存 token (假设有效期 24 小时)
            pm.environment.set('admin_token', newToken);
            pm.environment.set('admin_token_expiry', now + (24 * 60 * 60 * 1000));
            
            console.log('✅ 登录成功，Token 已更新');
        } else {
            console.error('❌ 登录失败:', err || res.body);
        }
    });
} else {
    console.log('✅ Token 仍有效，无需重新登录');
}
```

#### 自动生成幂等键

对于需要幂等键的接口 (如创建订单):

```javascript
// 生成唯一幂等键
const idempotencyKey = 'test-' + Date.now() + '-' + Math.random().toString(36).substring(7);

// 添加到请求头
pm.request.headers.add({
    key: 'X-Idempotency-Key',
    value: idempotencyKey
});

// 保存到环境变量供后续验证
pm.environment.set('last_idempotency_key', idempotencyKey);

console.log('生成幂等键:', idempotencyKey);
```

### 后置脚本 (Post-response Script)

#### 标准断言模板

```javascript
// 1. 检查状态码
pm.test("状态码为 200", function () {
    pm.response.to.have.status(200);
});

// 2. 检查响应时间
pm.test("响应时间 < 500ms", function () {
    pm.expect(pm.response.responseTime).to.be.below(500);
});

// 3. 检查响应格式
pm.test("返回 JSON 格式", function () {
    pm.response.to.be.json;
});

// 4. 检查响应内容
pm.test("响应包含必要字段", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('order_id');
    pm.expect(jsonData).to.have.property('order_number');
    pm.expect(jsonData).to.have.property('status');
});

// 5. 业务逻辑验证
pm.test("订单状态为 pending_payment", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData.status).to.eql('pending_payment');
});

// 6. 保存数据供后续接口使用
pm.test("保存订单 ID", function () {
    const jsonData = pm.response.json();
    pm.environment.set('last_order_id', jsonData.order_id);
    console.log('✅ 已保存订单 ID:', jsonData.order_id);
});
```

#### 订单创建专用断言

```javascript
pm.test("订单创建成功", function () {
    pm.response.to.have.status(201);
    
    const jsonData = pm.response.json();
    
    // 验证必要字段
    pm.expect(jsonData).to.have.property('order_id');
    pm.expect(jsonData).to.have.property('order_number');
    pm.expect(jsonData.status).to.eql('pending_payment');
    
    // 验证订单号格式 (例: 20251027123456-NA0001)
    pm.expect(jsonData.order_number).to.match(/^\d{14}-NA\d{4}$/);
    
    // 验证价格字段
    pm.expect(jsonData.total_price).to.be.a('number');
    pm.expect(jsonData.total_price).to.be.above(0);
    
    // 保存订单信息
    pm.environment.set('last_order_id', jsonData.order_id);
    pm.environment.set('last_order_number', jsonData.order_number);
    pm.environment.set('last_order_total', jsonData.total_price);
    
    console.log('✅ 订单创建成功:', jsonData.order_number);
});
```

#### 支付回调专用断言

```javascript
pm.test("支付回调处理成功", function () {
    pm.response.to.have.status(200);
    
    const jsonData = pm.response.json();
    pm.expect(jsonData.status).to.eql('SUCCESS');
});

pm.test("响应时间 < 1000ms (SLO)", function () {
    pm.expect(pm.response.responseTime).to.be.below(1000);
});

// 验证是否幂等 (重复发送相同回调)
pm.test("重复回调处理幂等", function () {
    // 此测试需在测试集中配置 "重复执行 2 次"
    // 两次请求应返回相同结果
    pm.response.to.have.status(200);
});
```

---

## 执行测试并生成报告

### 手动执行单个接口

1. 选择接口 → 点击 **"发送"**
2. 查看 **"响应"** 标签页
3. 查看 **"测试结果"** 标签页 (如果有后置脚本)

### 执行测试用例集

1. 点击 **"测试管理"**
2. 选择测试集 (例: `核心业务流程`)
3. 点击 **"运行"** 按钮
4. 配置运行参数:
   - 环境: Local / Staging
   - 迭代次数: 1 (单次) 或 10 (压力测试)
   - 延迟: 0ms (快速) 或 1000ms (模拟真实场景)
5. 点击 **"开始测试"**

### 查看测试报告

测试完成后:
1. 查看 **"测试报告"** 标签页
2. 报告包含:
   - ✅ 通过率 (例: 15/15 = 100%)
   - ⏱️ 总耗时
   - 📊 每个用例的详细结果
   - ❌ 失败用例的错误信息

### 导出测试报告

1. 点击报告页右上角 **"导出"**
2. 选择格式: HTML / PDF / JSON
3. 保存到本地 (例: `naicha-test-report-2025-10-27.html`)

---

## CI/CD 集成

### 方式 1: 使用 Apifox CLI

```bash
# 安装 Apifox CLI
npm install -g apifox-cli

# 导出测试集为 JSON
# 在 Apifox 中: 测试集 → 更多 → 导出 → JSON 格式

# 在 CI/CD 中运行
apifox run naicha-test-collection.json \
  --environment naicha-env-staging.json \
  --reporters cli,json \
  --reporter-json-export results/apifox-results.json

# 检查退出码
# 0 = 全部通过, 1 = 有失败用例
```

### 方式 2: 使用 Newman (Postman 兼容)

Apifox 支持导出为 Postman Collection 格式:

```bash
# 安装 Newman
npm install -g newman

# 在 Apifox 中: 测试集 → 导出 → Postman Collection v2.1

# 运行测试
newman run apifox-collection.json \
  -e apifox-env-staging.json \
  --reporters cli,htmlextra \
  --reporter-htmlextra-export results/newman-report.html

# 在 CI 中集成
# GitHub Actions 示例
```

### GitHub Actions 配置

```yaml
# .github/workflows/api-test.yml
name: API Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  api-test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Node.js
      uses: actions/setup-node@v3
      with:
        node-version: '18'
    
    - name: Install Newman
      run: npm install -g newman newman-reporter-htmlextra
    
    - name: Run API Tests
      env:
        ADMIN_PASSWORD: ${{ secrets.STAGING_ADMIN_PASSWORD }}
      run: |
        # 替换环境变量中的密码
        sed -i "s/<从密钥管理获取>/$ADMIN_PASSWORD/g" tests/apifox-env-staging.json
        
        # 运行测试
        newman run tests/apifox-collection.json \
          -e tests/apifox-env-staging.json \
          --reporters cli,htmlextra \
          --reporter-htmlextra-export results/api-test-report.html
    
    - name: Upload Test Report
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: api-test-report
        path: results/api-test-report.html
    
    - name: Notify on Failure
      if: failure()
      run: |
        echo "API 测试失败！请检查报告。"
        # 这里可以集成钉钉/企业微信通知
```

---

## 实战案例

### 案例 1: 完整订单流程测试

创建测试集: `完整订单流程`

**用例 1: 用户登录**
```javascript
// 请求
POST {{base_url}}/api/v1/users/login
{
  "code": "{{user_openid}}",
  "nickname": "测试用户",
  "avatar_url": "https://example.com/avatar.png"
}

// 后置脚本
pm.test("登录成功", function () {
    const jsonData = pm.response.json();
    pm.environment.set('user_token', jsonData.access_token);
    pm.environment.set('user_id', jsonData.user.user_id);
});
```

**用例 2: 获取菜单**
```javascript
// 请求
GET {{base_url}}/api/v1/menu

// 后置脚本
pm.test("菜单加载成功", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData.categories).to.be.an('array');
    pm.expect(jsonData.categories.length).to.be.above(0);
    
    // 保存第一个商品 ID
    const firstProduct = jsonData.categories[0].products[0];
    pm.environment.set('test_product_id', firstProduct.product_id);
});
```

**用例 3: 创建订单**
```javascript
// 前置脚本
const idempotencyKey = 'apifox-' + Date.now();
pm.request.headers.add({
    key: 'X-Idempotency-Key',
    value: idempotencyKey
});

// 请求
POST {{base_url}}/api/v1/orders
Authorization: Bearer {{user_token}}
{
  "items": [
    {
      "product_id": {{test_product_id}},
      "quantity": 1
    }
  ],
  "order_type": "pickup"
}

// 后置脚本
pm.test("订单创建成功", function () {
    const jsonData = pm.response.json();
    pm.environment.set('test_order_id', jsonData.order_id);
    pm.environment.set('test_order_total', jsonData.total_price);
});
```

**用例 4: 发起支付**
```javascript
// 请求
POST {{base_url}}/api/v1/orders/{{test_order_id}}/pay/jsapi
Authorization: Bearer {{user_token}}
{
  "payer_open_id": "{{user_openid}}"
}

// 后置脚本
pm.test("支付参数返回成功", function () {
    const jsonData = pm.response.json();
    pm.expect(jsonData.payload).to.have.property('prepay_id');
    pm.environment.set('test_prepay_id', jsonData.payload.prepay_id);
});
```

**用例 5: 模拟支付回调**
```javascript
// 请求 (需要签名，此处简化)
POST {{base_url}}/api/v1/payments/notify/wechat
X-Wechat-Signature: mock-signature
{
  "order_number": "{{test_order_number}}",
  "transaction_id": "wx-{{$timestamp}}",
  "amount": {{test_order_total}},
  "status": "SUCCESS",
  "paid_at": "{{$isoTimestamp}}"
}

// 后置脚本
pm.test("支付回调处理成功", function () {
    pm.response.to.have.status(200);
    const jsonData = pm.response.json();
    pm.expect(jsonData.status).to.eql('SUCCESS');
});
```

### 案例 2: 并发安全测试

**测试目标**: 验证相同幂等键并发请求只创建 1 个订单

**配置**:
1. 创建测试用例: `并发幂等性测试`
2. 设置迭代次数: `10` (模拟 10 个并发请求)
3. 使用相同的幂等键

```javascript
// 前置脚本 - 所有迭代使用相同幂等键
const sharedKey = 'concurrent-test-' + pm.environment.get('shared_idempotency_key');
if (!pm.environment.get('shared_idempotency_key')) {
    const newKey = Date.now().toString();
    pm.environment.set('shared_idempotency_key', newKey);
}

pm.request.headers.add({
    key: 'X-Idempotency-Key',
    value: 'concurrent-test-' + pm.environment.get('shared_idempotency_key')
});

// 后置脚本 - 验证返回相同订单
pm.test("并发请求返回相同订单", function () {
    const jsonData = pm.response.json();
    const existingOrderId = pm.environment.get('concurrent_test_order_id');
    
    if (!existingOrderId) {
        // 第一次请求
        pm.environment.set('concurrent_test_order_id', jsonData.order_id);
        console.log('✅ 首次创建订单:', jsonData.order_id);
    } else {
        // 后续请求应返回相同 order_id
        pm.expect(jsonData.order_id).to.eql(existingOrderId);
        console.log('✅ 幂等验证通过，订单 ID 一致:', jsonData.order_id);
    }
});
```

### 案例 3: 性能基准测试

**测试目标**: 验证 P95 响应时间 < 500ms

**配置**:
1. 迭代次数: `100`
2. 延迟: `0ms` (最大压力)

```javascript
// 后置脚本 - 收集响应时间
const responseTimes = pm.environment.get('response_times') || [];
responseTimes.push(pm.response.responseTime);
pm.environment.set('response_times', responseTimes);

// 在最后一次迭代计算 P95
const iteration = pm.info.iteration;
const totalIterations = pm.info.iterationCount;

if (iteration === totalIterations - 1) {
    // 计算 P95
    const sorted = responseTimes.sort((a, b) => a - b);
    const p95Index = Math.floor(sorted.length * 0.95);
    const p95 = sorted[p95Index];
    
    console.log('📊 性能统计:');
    console.log('  - 总请求数:', sorted.length);
    console.log('  - 平均响应时间:', (sorted.reduce((a, b) => a + b) / sorted.length).toFixed(2), 'ms');
    console.log('  - P95 响应时间:', p95.toFixed(2), 'ms');
    console.log('  - 最大响应时间:', sorted[sorted.length - 1].toFixed(2), 'ms');
    
    pm.test("P95 响应时间 < 500ms", function () {
        pm.expect(p95).to.be.below(500);
    });
    
    // 清理环境变量
    pm.environment.unset('response_times');
}
```

---

## 常见问题

### Q1: 如何处理需要动态签名的接口 (如支付回调)?

**解决方案**: 在前置脚本中计算签名

```javascript
const CryptoJS = require('crypto-js');

// 获取请求体
const body = pm.request.body.raw;

// 计算签名 (示例: HMAC-SHA256)
const secret = pm.environment.get('wechat_pay_secret');
const signature = CryptoJS.HmacSHA256(body, secret).toString();

// 添加签名头
pm.request.headers.add({
    key: 'X-Wechat-Signature',
    value: signature
});
```

### Q2: 如何测试文件上传接口?

**解决方案**: 使用 Apifox 的文件上传功能

1. 选择接口 → **"Body"** → **"form-data"**
2. 添加字段:
   - Key: `file`
   - Type: **"File"**
   - Value: 点击 **"选择文件"**
3. 发送请求

### Q3: 如何在测试中使用随机数据?

**解决方案**: 使用 Apifox 内置变量

```javascript
// 在请求体中使用
{
  "username": "user_{{$randomInt}}",
  "email": "{{$randomEmail}}",
  "phone": "138{{$randomInt(10000000,99999999)}}",
  "timestamp": "{{$timestamp}}"
}

// 更多内置变量:
// {{$guid}} - UUID
// {{$randomInt(min,max)}} - 随机整数
// {{$randomAlphaNumeric(length)}} - 随机字符串
// {{$timestamp}} - 当前时间戳
// {{$isoTimestamp}} - ISO 8601 格式时间
```

### Q4: 测试环境 Token 频繁过期怎么办?

**解决方案**: 在环境设置中启用 **"自动刷新 Token"**

或在每个请求前添加 Token 检查脚本 (见 [编写自动化脚本](#编写自动化脚本) 章节)

---

## 最佳实践

1. **使用环境变量** - 所有可变数据都用 `{{variable}}` 引用
2. **编写可复用脚本** - 将常用脚本保存为 "公共脚本"
3. **测试数据隔离** - 使用不同前缀区分环境 (如 `test-local-`, `test-staging-`)
4. **定期同步文档** - 代码更新后重新导入 OpenAPI
5. **版本管理** - 使用 Apifox 的版本管理功能跟踪接口变更
6. **团队协作** - 将项目分享给团队成员，统一测试标准

---

## 下一步

- ✅ 完成 Apifox 基础配置
- ✅ 导入 OpenAPI 文档
- ✅ 创建本地和 Staging 环境
- ✅ 编写核心业务流程测试集
- 🔄 执行测试并修复发现的问题
- 🔄 集成到 CI/CD 流程
- 🔄 编写性能基准测试

---

**相关文档**:
- [上线前验证完整指南](./pre-production-validation-guide.md)
- [API 文档](./api.md)
- [生产环境配置审查清单](./production-readiness-checklist.md)

**工具资源**:
- Apifox 官方文档: https://apifox.com/help/
- Apifox 视频教程: https://space.bilibili.com/735436156
