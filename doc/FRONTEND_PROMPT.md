# 智能奶茶档口系统 · 前端开发提示词（V1.0）

## 项目背景

你是一位资深的前端架构师，负责为"智能奶茶档口系统"设计并实现**三端前端应用**：

1. **顾客端小程序**（微信小程序，主营业务）
2. **商家端 Web 应用**（实时接单、订单管理、数据看板）
3. **管理后台 Web 应用**（商品配置、库存管理、数据分析）

后端基于 **FastAPI** 构建，已完成所有 API 实现并通过压测验证（100 并发 0% 错误率）。你的任务是构建高性能、易维护的前端应用，与后端无缝对接。

---

## 核心设计原则

### 1. 最小化开发
- **组件复用优先**：相同业务逻辑（如商品卡片、订单列表）必须抽象为通用组件
- **状态管理精简**：仅全局状态使用 Context/Redux，局部状态用 useState
- **依赖控制**：避免引入大而全的 UI 框架，优先使用轻量级库
- **代码生成**：利用 OpenAPI 规范自动生成 API 客户端，减少手写代码

### 2. 最优解原则
- **性能优先**：
  - 小程序首屏加载 ≤ 2s
  - 菜单页面缓存命中率 ≥ 95%
  - 订单列表虚拟滚动（100+ 订单场景）
- **用户体验**：
  - 网络请求必须有 loading 状态
  - 失败请求自动重试（最多 3 次，指数退避）
  - 离线数据缓存（购物车、用户信息）

### 3. 最低性能开销
- **打包优化**：
  - 代码分割（按路由懒加载）
  - Tree-shaking 去除未使用代码
  - 图片懒加载 + WebP 格式
- **运行时优化**：
  - 防抖/节流（搜索、滚动事件）
  - Memo 缓存（React.memo、useMemo、useCallback）
  - 避免不必要的重渲染

---

## 技术栈要求

### 顾客端小程序
- **框架**：原生微信小程序 + TypeScript
- **状态管理**：mobx-miniprogram（轻量级响应式）
- **UI 组件**：Vant Weapp（按需引入）
- **校验**：zod（运行时类型校验）
- **网络封装**：wx.request 统一包装（兼容后端 `{code, message, data}` 规范）
- **实时通信**：wx.connectSocket 二次封装（30s 心跳、指数退避、事件分发）
- **主题系统**：
  - **设计 tokens**：`tokens.json` → `build-tokens.js` 自动生成
  - **默认主题**：`styles/app.wxss`
  - **适老化主题**：`styles/app-elder.wxss`（字号↑、对比↑、触控面积↑）

### 商家端 & 管理后台 Web
- **框架**：React 18 + TypeScript（或 Vue 3 + TypeScript）
- **路由**：React Router v6 / Vue Router 4
- **状态管理**：Zustand / Pinia
- **UI 组件**：Ant Design / Element Plus（按需引入）
- **网络请求**：TanStack Query（React Query）自动缓存 + 失效
- **实时通信**：WebSocket + 心跳机制（商家端订单推送）
- **构建工具**：Vite（快速热更新）

---

## API 对接规范

### 1. OpenAPI 代码生成（Web 应用）
使用后端导出的 `naicha-openapi.json` 自动生成 Web API 客户端：

```bash
# 安装工具
npm install -g @openapitools/openapi-generator-cli

# 生成 TypeScript 客户端（用于 Web 应用）
openapi-generator-cli generate \
  -i naicha-openapi.json \
  -g typescript-axios \
  -o src/api/generated
```

**小程序 API 封装**：
由于微信小程序不支持 Axios，需手动封装 `wx.request`：

```typescript
// miniapp/utils/request.ts
import { z } from 'zod';

// 后端统一响应格式
const ResponseSchema = z.object({
  code: z.number().default(0),
  message: z.string().optional(),
  data: z.any().optional(),
  trace_id: z.string().optional(),
});

interface RequestConfig {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: any;
  header?: Record<string, string>;
  timeout?: number;
}

export const request = async <T = any>(config: RequestConfig): Promise<T> => {
  const baseURL = 'https://api.naicha.com';
  const token = wx.getStorageSync('auth_token');

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseURL}${config.url}`,
      method: config.method || 'GET',
      data: config.data,
      header: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
        ...config.header,
      },
      timeout: config.timeout || 30000,
      success: (res) => {
        // 校验响应格式
        const parsed = ResponseSchema.safeParse(res.data);
        if (!parsed.success) {
          reject(new Error('响应格式错误'));
          return;
        }

        const response = parsed.data;

        // 业务错误
        if (response.code !== 0) {
          wx.showToast({
            title: response.message || '请求失败',
            icon: 'none',
          });
          reject(new Error(response.message));
          return;
        }

        resolve(response.data as T);
      },
      fail: (err) => {
        // 网络错误
        wx.showToast({
          title: '网络请求失败',
          icon: 'none',
        });
        reject(err);
      },
    });
  });
};

// 自动重试逻辑（指数退避）
export const requestWithRetry = async <T = any>(
  config: RequestConfig,
  maxRetries = 3
): Promise<T> => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await request<T>(config);
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      await sleep(Math.pow(2, i) * 1000); // 1s, 2s, 4s
    }
  }
  throw new Error('请求失败');
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
```

**Web 应用配置要点**：
- 基础 URL：从环境变量读取（`VITE_API_BASE_URL`）
- 请求拦截器：自动注入 JWT Token（`Authorization: Bearer <token>`）
- 响应拦截器：统一处理错误（401 跳转登录，500 提示重试）

### 2. 幂等性处理
创建订单等接口需要 `Idempotency-Key` 请求头：

```typescript
// 小程序版本
import { v4 as uuidv4 } from 'uuid';
import { request } from '@/utils/request';

const createOrder = async (orderData: CreateOrderRequest) => {
  const idempotencyKey = uuidv4();
  return request<Order>({
    url: '/api/v1/orders',
    method: 'POST',
    data: orderData,
    header: { 'Idempotency-Key': idempotencyKey },
  });
};
```

### 3. 错误处理标准
后端返回格式：

```json
{
  "detail": "Order not found",
  "trace_id": "abc123",
  "status_code": 404
}
```

前端需要：
- 捕获 `trace_id` 并显示在错误提示中（方便排查）
- 根据 `status_code` 区分错误类型：
  - `401`：跳转登录
  - `403`：权限不足提示
  - `404`：资源不存在
  - `409`：冲突（如重复下单）
  - `429`：限流（显示稍后重试）
  - `500+`：服务器错误（自动重试 3 次）

---

## 核心功能实现指南

### 顾客端小程序

#### 1. 菜单页面（首页）
**需求**：
- 展示商品分类 + 商品列表
- 支持售罄商品置灰/隐藏（根据 `SOLDOUT_STYLE` 配置）
- 商品卡片显示：图片、名称、价格、库存状态
- 点击商品进入规格选择页面

**性能要求**：
- 菜单数据缓存 5 分钟（与后端 TTL 一致）
- 使用虚拟列表（商品数 > 20 时）

**API**：`GET /api/v1/menu`

**状态管理（MobX）**：
```typescript
// miniapp/stores/menu.ts
import { observable, action, runInAction } from 'mobx-miniprogram';

export const menuStore = observable({
  // 状态
  categories: [] as Category[],
  products: [] as Product[],
  loading: false,
  lastFetched: 0,

  // 计算属性
  get isStale() {
    const TTL = 5 * 60 * 1000; // 5 分钟
    return Date.now() - this.lastFetched > TTL;
  },

  // 操作方法
  fetchMenu: action(async function () {
    if (this.loading || !this.isStale) return;

    this.loading = true;
    try {
      const response = await request<MenuResponse>({
        url: '/api/v1/menu',
        method: 'GET',
      });

      runInAction(() => {
        this.categories = response.categories;
        this.products = response.products;
        this.lastFetched = Date.now();
        this.loading = false;
      });
    } catch (err) {
      runInAction(() => {
        this.loading = false;
      });
      throw err;
    }
  }),

  // 清除缓存
  clearCache: action(function () {
    this.lastFetched = 0;
  }),
});
```

**页面绑定**：
```typescript
// miniapp/pages/menu/menu.ts
import { createStoreBindings } from 'mobx-miniprogram-bindings';
import { menuStore } from '../../stores/menu';

Page({
  data: {
    categories: [] as Category[],
    products: [] as Product[],
    loading: false,
  },

  onLoad() {
    // 绑定 Store
    this.storeBindings = createStoreBindings(this, {
      store: menuStore,
      fields: ['categories', 'products', 'loading'],
      actions: ['fetchMenu'],
    });

    // 加载菜单
    this.fetchMenu();
  },

  onUnload() {
    // 解绑
    this.storeBindings?.destroyStoreBindings();
  },
});
```

#### 2. 规格选择页面
**需求**：
- 多规格组合（如：糖度 + 温度 + 小料）
- 动态计算价格（基础价 + 规格加价）
- 数量选择（默认 1，最多 10）
- 加入购物车 / 立即购买

**价格计算逻辑**：
```typescript
const calculatePrice = (basePrice: number, selectedOptions: SpecOption[]) => {
  const modifiers = selectedOptions.reduce((sum, opt) => sum + opt.price_modifier, 0);
  return basePrice + modifiers;
};
```

#### 3. 购物车页面
**需求**：
- 商品列表（名称、规格、单价、数量）
- 修改数量 / 删除商品
- 总价计算（实时）
- 结算按钮 → 跳转订单确认页

**本地存储（小程序）**：
```typescript
// miniapp/utils/storage.ts
const CART_KEY = 'naicha_cart';

export const saveCart = (cart: CartItem[]) => {
  wx.setStorageSync(CART_KEY, cart);
};

export const loadCart = (): CartItem[] => {
  try {
    return wx.getStorageSync(CART_KEY) || [];
  } catch (err) {
    return [];
  }
};

export const clearCart = () => {
  wx.removeStorageSync(CART_KEY);
};
```

**购物车 Store（MobX）**：
```typescript
// miniapp/stores/cart.ts
import { observable, action, computed } from 'mobx-miniprogram';
import { saveCart, loadCart } from '../utils/storage';

export const cartStore = observable({
  items: loadCart(),

  // 总价
  get totalPrice() {
    return this.items.reduce((sum, item) => {
      const specsTotal = item.selected_specs.reduce(
        (s, spec) => s + spec.price_modifier,
        0
      );
      return sum + (item.unit_price + specsTotal) * item.quantity;
    }, 0);
  },

  // 总数量
  get totalQuantity() {
    return this.items.reduce((sum, item) => sum + item.quantity, 0);
  },

  // 添加商品
  addItem: action(function (item: CartItem) {
    const existingIndex = this.items.findIndex(
      (i) =>
        i.product_id === item.product_id &&
        JSON.stringify(i.selected_specs) === JSON.stringify(item.selected_specs)
    );

    if (existingIndex !== -1) {
      this.items[existingIndex].quantity += item.quantity;
    } else {
      this.items.push(item);
    }

    saveCart(this.items);
  }),

  // 更新数量
  updateQuantity: action(function (productId: number, quantity: number) {
    const item = this.items.find((i) => i.product_id === productId);
    if (item) {
      item.quantity = quantity;
      saveCart(this.items);
    }
  }),

  // 移除商品
  removeItem: action(function (productId: number) {
    this.items = this.items.filter((i) => i.product_id !== productId);
    saveCart(this.items);
  }),

  // 清空购物车
  clearAll: action(function () {
    this.items = [];
    saveCart(this.items);
  }),
});
```

#### 4. 订单确认 & 支付
**需求**：
- 订单类型选择（自取 / 配送）
- 配送地址选择（调用 `GET /api/v1/me/addresses`）
- 配送范围校验（`POST /api/v1/shop/delivery/check`）
- 备注输入
- 提交订单 → 获取支付参数 → 调起微信支付

**流程**：
```typescript
// 1. 创建订单（带 Idempotency-Key）
const order = await createOrder(orderData);

// 2. 发起支付
const { payload } = await initiatePayment(order.order_id, {
  payer_open_id: wx.getStorageSync('openid')
});

// 3. 调起微信支付
wx.requestPayment({
  ...payload,
  success: () => {
    // 跳转订单详情页，轮询订单状态
    pollOrderStatus(order.order_id);
  }
});
```

**轮询逻辑**：
```typescript
const pollOrderStatus = async (orderId: number) => {
  const maxRetries = 60; // 最多轮询 60 次（30 秒）
  for (let i = 0; i < maxRetries; i++) {
    const order = await getOrderDetail(orderId);
    if (order.status !== 'pending_payment') {
      // 支付成功，跳转结果页
      return;
    }
    await sleep(500);
  }
  // 超时提示用户刷新
};
```

#### 5. 订单列表 & 详情
**需求**：
- Tab 筛选（全部 / 待支付 / 制作中 / 已完成）
- 订单卡片：订单号、商品列表、状态、金额
- 下拉刷新 + 上拉加载更多
- 待支付订单显示"去支付"按钮
- 已完成订单显示"再来一单"按钮

**API**：`GET /api/v1/orders?status=<status>&page=<page>`

#### 6. WebSocket 封装（小程序实时通信）

**需求**：
- 订单状态实时更新（商家接单、制作中、已完成）
- 30 秒心跳保活
- 断线自动重连（指数退避）
- 事件分发机制

**封装实现**：
```typescript
// miniapp/utils/websocket.ts
type MessageHandler = (data: any) => void;

class WebSocketManager {
  private socket: WechatMiniprogram.SocketTask | null = null;
  private url: string;
  private token: string;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private handlers: Map<string, MessageHandler[]> = new Map();

  constructor(url: string, token: string) {
    this.url = url;
    this.token = token;
  }

  connect() {
    this.socket = wx.connectSocket({
      url: `${this.url}?token=${this.token}`,
      success: () => {
        console.log('WebSocket 连接中...');
      },
      fail: (err) => {
        console.error('WebSocket 连接失败:', err);
        this.scheduleReconnect();
      },
    });

    this.socket.onOpen(() => {
      console.log('WebSocket 已连接');
      this.reconnectAttempts = 0;
      this.startHeartbeat();
    });

    this.socket.onMessage((res) => {
      try {
        const message = JSON.parse(res.data as string);
        this.dispatch(message.type, message);
      } catch (err) {
        console.error('WebSocket 消息解析失败:', err);
      }
    });

    this.socket.onError((err) => {
      console.error('WebSocket 错误:', err);
      this.stopHeartbeat();
    });

    this.socket.onClose(() => {
      console.log('WebSocket 已断开');
      this.stopHeartbeat();
      this.scheduleReconnect();
    });
  }

  // 发送消息
  send(data: any) {
    if (this.socket) {
      this.socket.send({
        data: JSON.stringify(data),
        fail: (err) => {
          console.error('WebSocket 发送失败:', err);
        },
      });
    }
  }

  // 订阅消息
  on(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type)!.push(handler);
  }

  // 取消订阅
  off(type: string, handler: MessageHandler) {
    const handlers = this.handlers.get(type);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  // 事件分发
  private dispatch(type: string, message: any) {
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.forEach((handler) => handler(message));
    }
  }

  // 心跳
  private startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000) as any; // 30 秒
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  // 重连（指数退避）
  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('WebSocket 重连次数超限');
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`${delay}ms 后尝试重连（第 ${this.reconnectAttempts} 次）`);

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay) as any;
  }

  // 关闭连接
  close() {
    this.stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.socket) {
      this.socket.close({
        success: () => {
          console.log('WebSocket 主动关闭');
        },
      });
    }
  }
}

// 导出单例
export const createWebSocket = (url: string, token: string) => {
  return new WebSocketManager(url, token);
};
```

**使用示例**：
```typescript
// miniapp/pages/order-detail/order-detail.ts
const ws = createWebSocket('wss://api.naicha.com/ws/customer', token);

// 连接
ws.connect();

// 监听订单状态更新
ws.on('order.status_updated', (message) => {
  console.log('订单状态更新:', message.order);
  this.setData({ order: message.order });
});

// 页面卸载时关闭连接
onUnload() {
  ws.close();
}
```

#### 7. 主题系统（适老化支持）

**Design Tokens（设计变量）**：
```json
// miniapp/styles/tokens.json
{
  "colors": {
    "primary": "#FF6B35",
    "text-primary": "#333333",
    "text-secondary": "#666666",
    "bg-page": "#F5F5F5"
  },
  "font-sizes": {
    "xs": "24rpx",
    "sm": "28rpx",
    "md": "32rpx",
    "lg": "36rpx",
    "xl": "40rpx"
  },
  "spacing": {
    "xs": "8rpx",
    "sm": "16rpx",
    "md": "24rpx",
    "lg": "32rpx"
  },
  "elder": {
    "font-sizes": {
      "xs": "32rpx",
      "sm": "36rpx",
      "md": "40rpx",
      "lg": "48rpx",
      "xl": "56rpx"
    },
    "colors": {
      "text-primary": "#000000",
      "text-secondary": "#333333"
    },
    "touch-target": "88rpx"
  }
}
```

**自动生成 WXSS（构建脚本）**：
```javascript
// scripts/build-tokens.js
const fs = require('fs');
const tokens = require('../miniapp/styles/tokens.json');

// 生成默认主题
let defaultCSS = '/* 自动生成，请勿手动修改 */\n';
defaultCSS += 'page {\n';
defaultCSS += `  --color-primary: ${tokens.colors.primary};\n`;
defaultCSS += `  --color-text-primary: ${tokens.colors['text-primary']};\n`;
defaultCSS += `  --font-size-md: ${tokens['font-sizes'].md};\n`;
// ... 更多变量
defaultCSS += '}\n';

fs.writeFileSync('./miniapp/styles/app.wxss', defaultCSS);

// 生成适老化主题
let elderCSS = '/* 适老化主题，自动生成 */\n';
elderCSS += 'page {\n';
elderCSS += `  --font-size-md: ${tokens.elder['font-sizes'].md};\n`;
elderCSS += `  --color-text-primary: ${tokens.elder.colors['text-primary']};\n`;
elderCSS += `  --touch-target: ${tokens.elder['touch-target']};\n`;
// ... 更多变量
elderCSS += '}\n';

fs.writeFileSync('./miniapp/styles/app-elder.wxss', elderCSS);

console.log('✅ 主题文件生成成功');
```

**主题切换逻辑**：
```typescript
// miniapp/utils/theme.ts
export const applyTheme = (theme: 'default' | 'elder') => {
  const themeFile = theme === 'elder' ? 'app-elder' : 'app';
  
  // 注意：小程序不支持动态切换全局样式
  // 需要在 app.json 中配置多个主题文件
  wx.setStorageSync('theme', theme);
  
  // 重启小程序以应用新主题
  wx.reLaunch({ url: '/pages/menu/menu' });
};

export const getCurrentTheme = (): 'default' | 'elder' => {
  return wx.getStorageSync('theme') || 'default';
};
```

**app.json 配置**：
```json
{
  "pages": ["pages/menu/menu", "pages/cart/cart"],
  "window": {
    "navigationBarTitleText": "智能奶茶档口"
  },
  "style": "v2",
  "sitemapLocation": "sitemap.json",
  "themeLocation": "theme.json"
}
```

**theme.json（微信官方适老化）**：
```json
{
  "light": {
    "pageBackgroundColor": "#F5F5F5",
    "primaryColor": "#FF6B35"
  },
  "elder": {
    "pageBackgroundColor": "#FFFFFF",
    "primaryColor": "#FF6B35",
    "fontSize": 120
  }
}
```

---

### 商家端 Web 应用

#### 1. 实时订单面板
**需求**：
- WebSocket 连接（`WS /ws/merchant?token=<jwt>`）
- 新订单桌面通知 + 声音提示
- 订单卡片展示：订单号、商品、金额、下单时间
- 操作按钮：开始制作 / 完成 / 重打小票

**WebSocket 实现**：
```typescript
const connectWebSocket = (token: string) => {
  const ws = new WebSocket(`wss://api.example.com/ws/merchant?token=${token}`);

  ws.onopen = () => {
    console.log('WebSocket connected');
    startHeartbeat(ws);
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === 'order.paid') {
      // 新订单推送
      showNotification(message.order);
      playSound();
    }
  };

  ws.onerror = () => {
    // 5 秒后重连
    setTimeout(() => connectWebSocket(token), 5000);
  };

  return ws;
};

const startHeartbeat = (ws: WebSocket) => {
  setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 30000); // 30 秒心跳
};
```

#### 2. 订单管理页面
**需求**：
- 筛选：日期范围、状态、支付渠道
- 排序：下单时间、金额
- 批量操作：导出 CSV
- 订单详情抽屉（点击卡片展开）

**状态更新**：
```typescript
const updateOrderStatus = async (orderId: number, status: string) => {
  await api.put(`/api/v1/admin/orders/${orderId}/status`, { status });
  // 刷新列表
  refetchOrders();
};
```

#### 3. 数据看板
**需求**：
- 核心指标卡片：今日营业额、订单数、客单价
- 折线图：近 7 天趋势（使用 ECharts / Chart.js）
- 饼图：支付渠道分布
- Top 5 商品排行榜

**API**：`GET /api/v1/admin/dashboard?range=day&compare=true`

**缓存策略**：
```typescript
import { useQuery } from '@tanstack/react-query';

const useDashboard = (range: string) => {
  return useQuery({
    queryKey: ['dashboard', range],
    queryFn: () => fetchDashboard(range),
    staleTime: 60000, // 1 分钟内复用缓存
    refetchInterval: 60000, // 每分钟自动刷新
  });
};
```

---

### 管理后台 Web 应用

#### 1. 商品管理
**需求**：
- 商品列表（CRUD）
- 分类管理（拖拽排序）
- 规格组管理（糖度、温度、小料等）
- 库存状态快速切换（在售 / 售罄）

**库存更新**：
```typescript
const toggleInventoryStatus = async (productId: number, status: 'in_stock' | 'sold_out') => {
  await api.put(`/api/v1/admin/inventory/products/${productId}`, {
    inventory_status: status
  });
  // 触发菜单缓存刷新（后端自动）
};
```

#### 2. 售罄管理页面
**需求**：
- 商品 / 规格售罄状态一键切换
- 售罄后显示"想要"统计数据
- 恢复供应时推送消息给关注用户（后端实现）

**API**：
- 更新商品：`PUT /api/v1/admin/inventory/products/{id}`
- 更新规格：`PUT /api/v1/admin/inventory/spec-options/{id}`
- 查看统计：`GET /api/v1/admin/want/stats?range=7d`

#### 3. 预约管理
**需求**：
- 预约时段配置（开始时间、结束时间、容量）
- 预约订单列表（时段、联系人、状态）
- 到期提醒记录（查看已发送的提醒）

**API**：
- 订单列表：`GET /api/v1/admin/orders?is_scheduled=true`

---

## 开发规范

### 1. 代码风格
- **TypeScript 强制**：所有 `.ts/.tsx` 文件，禁用 `any`
- **ESLint + Prettier**：统一格式化
- **命名规范**：
  - 组件：PascalCase（`ProductCard.tsx`）
  - 函数：camelCase（`fetchMenu`）
  - 常量：UPPER_SNAKE_CASE（`API_BASE_URL`）
  - CSS 类：kebab-case（`product-card`）

### 2. 组件设计
- **原子设计**：Atoms（按钮、输入框）→ Molecules（表单项）→ Organisms（表单）→ Templates（页面布局）
- **Props 类型严格**：每个组件必须定义 `interface Props`
- **默认导出禁止**：统一使用命名导出（便于重构）

### 3. 状态管理
- **全局状态**：用户信息、Token、购物车
- **服务端状态**：使用 React Query（自动缓存 + 失效）
- **表单状态**：使用 React Hook Form（性能优化）

### 4. 测试要求
- **单元测试**：所有工具函数、Hooks 必须有测试（Vitest / Jest）
- **组件测试**：关键业务组件（如购物车、订单流程）必须测试（React Testing Library）
- **E2E 测试**：核心流程（下单 → 支付 → 订单查询）使用 Playwright

---

## 环境变量配置

### 顾客端小程序
```bash
# .env.development
TARO_APP_API_URL=http://localhost:8000
TARO_APP_WX_APPID=wx1234567890

# .env.production
TARO_APP_API_URL=https://api.naicha.com
TARO_APP_WX_APPID=wx_prod_id
```

### 商家端 & 管理后台
```bash
# .env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/merchant

# .env.production
VITE_API_BASE_URL=https://api.naicha.com
VITE_WS_URL=wss://api.naicha.com/ws/merchant
```

---

## 部署清单

### 顾客端小程序
1. **构建**：`npm run build:weapp`
2. **上传**：微信开发者工具 → 上传代码
3. **审核**：微信公众平台提交审核
4. **发布**：审核通过后全量发布

### Web 应用（商家端 + 管理后台）
1. **构建**：`npm run build`
2. **静态资源**：上传 `dist/` 到 OSS / CDN
3. **Nginx 配置**：
```nginx
server {
  listen 80;
  server_name admin.naicha.com;

  location / {
    root /var/www/html;
    try_files $uri $uri/ /index.html;
  }

  location /api {
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
}
```

---

## 质量检查清单

### 代码质量
- [ ] 所有组件都有 TypeScript 类型定义
- [ ] 无 ESLint 错误或警告
- [ ] 关键函数有单元测试覆盖
- [ ] 无 console.log 残留（使用日志库）

### 性能指标
- [ ] 小程序首屏加载 ≤ 2s（真机测试）
- [ ] 菜单页面缓存命中率 ≥ 95%
- [ ] Web 应用 Lighthouse 分数 ≥ 90

### 用户体验
- [ ] 所有网络请求有 loading 状态
- [ ] 失败请求有友好错误提示（含 trace_id）
- [ ] 离线状态有提示（购物车数据本地保存）
- [ ] 支付失败有重试入口

### 安全检查
- [ ] Token 存储安全（小程序用加密存储）
- [ ] 敏感信息不打印到日志
- [ ] HTTPS / WSS 强制使用
- [ ] API 请求签名验证（如需）

---

## 参考资源

- **后端 API 文档**：`/docs`（OpenAPI Swagger UI）
- **API 变更记录**：`doc/api.md`
- **后端开发指南**：`doc/develop.md`
- **运维手册**：`doc/runbook.md`
- **后端仓库**：`https://github.com/YourOrg/naicha-backend`

---

## 联系方式

技术支持：backend-team@naicha.com  
产品需求：product@naicha.com  
紧急联系：oncall@naicha.com（7×24）

---

**最后更新**：2025-10-27  
**版本**：V1.0  
**状态**：生产就绪
