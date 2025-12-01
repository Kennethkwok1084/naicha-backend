# 微信小程序认证实现说明

## 概述

本实现为奶茶后端系统添加了完整的微信小程序登录和手机号绑定功能，遵循"如无必要不增加实体"原则，采用最小化、最优解、最低性能开销的设计。

## 核心功能

### 1. 微信登录 (`POST /api/v1/users/login`)
- ✅ 使用一次性code换取openid/unionid
- ✅ 防重放机制（SHA256哈希存储已用code）
- ✅ 自动创建/更新用户信息
- ✅ 昵称/头像输入过滤（XSS防护、长度限制）
- ✅ 返回JWT access_token（2小时）和refresh_token（30天）
- ✅ IP级别限流（10次/分钟）

### 2. 手机号绑定 (`POST /api/v1/users/phone/bind`)
- ✅ 使用微信getPhoneNumber的code换取手机号
- ✅ 支持已登录用户或游客会话绑定
- ✅ 防重放机制
- ✅ 手机号脱敏日志
- ✅ IP级别限流（5次/分钟）

## 安全特性

### 防重放攻击
- 所有微信code（登录/手机号）仅可使用一次
- 使用SHA256哈希存储于`wechat_used_codes`表
- 重复使用立即拒绝

### 敏感信息保护
- ❌ session_key 不落日志、不返回前端
- ❌ 手机号明文仅在业务逻辑中使用，日志中脱敏
- ✅ WECHAT_APPID/WECHAT_SECRET 仅走环境变量
- ✅ 所有用户输入经过过滤和限长

### Token机制
- JWT包含：user_id、openid、jti（JWT ID）、scope、exp
- access_token：2小时有效期
- refresh_token：30天有效期
- 支持token黑名单踢下线（通过`token_blacklist`表）

### 速率限制
- 登录接口：10次/分钟/IP
- 手机绑定：5次/分钟/IP
- 降级到IP级别（支持未来扩展到openid级别）

## 数据库变更

### 新增表
1. **wechat_used_codes** - 防重放
   - code_hash (SHA256)
   - code_type (login/phone)
   - used_by_openid
   - created_at

2. **token_blacklist** - token黑名单
   - token_jti
   - user_id
   - expires_at
   - reason

### 修改表
**users** 表新增字段:
- `union_id` - 微信unionid（可选）
- `phone` - 用户手机号（可选）

## 配置说明

### 环境变量（必填）
```bash
# 微信小程序凭证
WECHAT_APPID=wx1234567890abcdef
WECHAT_SECRET=your_wechat_secret_here

# Token过期时间（可选，有默认值）
ACCESS_TOKEN_EXPIRE_MINUTES=120  # 默认2小时
REFRESH_TOKEN_EXPIRE_DAYS=30     # 默认30天
WECHAT_API_TIMEOUT=5             # 默认5秒
```

### 微信后台配置
1. 在微信公众平台配置服务器域名（必须https）
2. 开启用户信息权限
3. 开启手机号快速验证权限

## 部署步骤

### 1. 更新环境变量
```bash
# 复制并修改.env文件
cp .env.example .env
# 填入真实的WECHAT_APPID和WECHAT_SECRET
```

### 2. 运行数据库迁移
```bash
make updb
# 或
alembic upgrade head
```

### 3. 运行测试
```bash
# 单元测试
make test

# 特定测试
pytest tests/services/test_wechat_auth_service.py -v
pytest tests/api/test_wechat_auth.py -v
```

### 4. 启动服务
```bash
make dev
```

## API使用示例

### 前端登录流程

```javascript
// 1. 获取微信登录code
wx.login({
  success: async (res) => {
    const { code } = res;
    
    // 2. 调用后端登录接口
    const response = await fetch('https://your-api.com/api/v1/users/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: code,
        nickname: '用户昵称',  // 可选
        avatar_url: 'https://...'  // 可选
      })
    });
    
    const data = await response.json();
    
    // 3. 保存token
    wx.setStorageSync('access_token', data.access_token);
    wx.setStorageSync('refresh_token', data.refresh_token);
  }
});
```

### 前端绑定手机号

```javascript
// 1. 获取手机号code
wx.login({
  success: (res) => {
    wx.getPhoneNumber({
      success: async (phoneRes) => {
        const { code } = phoneRes;
        
        // 2. 调用后端绑定接口
        const token = wx.getStorageSync('access_token');
        const response = await fetch('https://your-api.com/api/v1/users/phone/bind', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            code: code,
            guest_session_id: 'guest_abc123'  // 可选
          })
        });
        
        const data = await response.json();
        console.log('手机号:', data.phone);  // 脱敏显示
      }
    });
  }
});
```

## 错误处理

### 常见错误码
- `400` - code已使用或参数错误
- `401` - 未授权（token无效或过期）
- `429` - 超过速率限制
- `500` - 服务器错误（微信API失败等）

### 前端重试策略
```javascript
async function loginWithRetry(code, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await fetch('/api/v1/users/login', {
        method: 'POST',
        body: JSON.stringify({ code })
      });
      
      if (response.status === 400) {
        // code已使用，重新获取
        const newCode = await getNewWeChatCode();
        code = newCode;
        continue;
      }
      
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      await sleep(1000 * (i + 1));  // 指数退避
    }
  }
}
```

## 性能考量

### 优化点
1. **最小化数据库查询**
   - 登录流程：2次查询（防重放检查 + 用户查询/创建）
   - 手机绑定：3次查询（防重放 + 用户查询 + 更新）

2. **异步处理**
   - 微信API调用使用httpx异步客户端
   - 数据库操作全异步

3. **索引优化**
   - `wechat_used_codes.code_hash` - 唯一索引
   - `users.open_id` - 唯一索引
   - `users.union_id` - 普通索引
   - `users.phone` - 普通索引

### 监控指标
建议监控以下指标：
- 登录成功率
- 微信API调用延迟
- code重复使用频率
- 手机号绑定成功率

## 测试覆盖

### 单元测试
- ✅ 新用户登录
- ✅ 已有用户登录
- ✅ code防重放
- ✅ 微信API错误处理
- ✅ 昵称XSS防护
- ✅ 头像URL验证
- ✅ 手机号绑定
- ✅ 手机号code防重放

### 集成测试
- ✅ 完整登录流程
- ✅ 完整手机绑定流程
- ✅ token验证
- ✅ 限流测试

## 安全审计清单

- [x] 敏感配置仅走环境变量
- [x] session_key不落日志/不返回
- [x] 手机号日志脱敏
- [x] code防重放机制
- [x] 用户输入过滤（XSS防护）
- [x] 速率限制
- [x] JWT包含必要信息
- [x] 支持token黑名单
- [x] HTTPS only（微信要求）

## 回滚方案

如需回滚：
```bash
# 1. 回滚数据库
alembic downgrade -1

# 2. 回滚代码
git revert <commit-hash>

# 3. 重启服务
systemctl restart naicha-backend
```

## 文档更新

- ✅ `doc/api.md` - 新增接口文档
- ✅ `.env.example` - 新增配置说明
- ✅ `AGENTS.md` - 遵循项目规范
- ✅ 本README - 完整实现说明

## 联系与支持

如有问题或建议，请提交Issue或联系开发团队。

---

**实现日期**: 2025-11-29  
**版本**: v1.0.0  
**遵循规范**: AGENTS.md
