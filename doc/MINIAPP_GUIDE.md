# 微信小程序开发指南（原生 + TypeScript）

---

## 目录

* [技术栈概览](#技术栈概览)
* [项目初始化](#项目初始化)
* [网络请求封装](#网络请求封装)
* [状态管理（MobX）](#状态管理mobx)
* [WebSocket 实时通信](#websocket-实时通信)
* [主题系统（适老化）](#主题系统适老化)
* [性能优化](#性能优化)
* [常见问题](#常见问题)

---

## 技术栈概览

| 技术 | 版本 | 用途 |
|------|------|------|
| 原生微信小程序 | - | 框架基础 |
| TypeScript | 5.0+ | 类型安全 |
| MobX | 6.x | 状态管理 |
| Vant Weapp | 1.x | UI 组件库 |
| zod | 3.x | 运行时类型校验 |

---

## 项目初始化

### 1. 创建项目

使用微信开发者工具：
1. 打开微信开发者工具
2. 新建项目 → 小程序 → 不使用云服务
3. AppID：使用测试号或真实 AppID
4. 语言：TypeScript
5. 模板：不使用模板

### 2. 安装依赖

```bash
npm init -y

# 安装核心依赖
npm install mobx-miniprogram mobx-miniprogram-bindings
npm install @vant/weapp
npm install zod
npm install uuid

# 安装开发依赖
npm install --save-dev miniprogram-api-typings
npm install --save-dev @types/uuid
npm install --save-dev typescript
```

### 3. 配置 TypeScript

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "CommonJS",
    "lib": ["ES2020"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "types": ["miniprogram-api-typings"],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["**/*.ts"],
  "exclude": ["node_modules", "miniprogram_npm"]
}
```

### 4. 构建 npm

修改 `project.config.json`：
```json
{
  "description": "智能奶茶档口小程序",
  "setting": {
    "packNpmManually": true,
    "packNpmRelationList": [
      {
        "packageJsonPath": "./package.json",
        "miniprogramNpmDistDir": "./"
      }
    ]
  },
  "compileType": "miniprogram",
  "libVersion": "3.0.0",
  "appid": "your-appid",
  "projectname": "naicha-miniapp"
}
```

在微信开发者工具中：**工具 → 构建 npm**

---

## 网络请求封装

### 统一请求函数

```typescript
// utils/request.ts
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
  skipAuth?: boolean; // 是否跳过认证
}

interface RequestError {
  message: string;
  code: number;
  trace_id?: string;
}

// 基础 URL（从配置读取）
const BASE_URL = 'https://api.naicha.com';

/**
 * 统一请求函数
 */
export const request = async <T = any>(config: RequestConfig): Promise<T> => {
  const token = wx.getStorageSync('auth_token');

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${config.url}`,
      method: config.method || 'GET',
      data: config.data,
      header: {
        'Content-Type': 'application/json',
        ...(token && !config.skipAuth ? { Authorization: `Bearer ${token}` } : {}),
        ...config.header,
      },
      timeout: config.timeout || 30000,
      success: (res) => {
        // 校验响应格式
        const parsed = ResponseSchema.safeParse(res.data);
        if (!parsed.success) {
          const error: RequestError = {
            message: '响应格式错误',
            code: -1,
          };
          reject(error);
          return;
        }

        const response = parsed.data;

        // 业务错误
        if (response.code !== 0) {
          const error: RequestError = {
            message: response.message || '请求失败',
            code: response.code,
            trace_id: response.trace_id,
          };

          // 401：Token 过期，跳转登录
          if (res.statusCode === 401) {
            wx.removeStorageSync('auth_token');
            wx.redirectTo({ url: '/pages/login/login' });
          }

          // 显示错误提示
          wx.showToast({
            title: error.message,
            icon: 'none',
            duration: 2000,
          });

          reject(error);
          return;
        }

        resolve(response.data as T);
      },
      fail: (err) => {
        // 网络错误
        const error: RequestError = {
          message: '网络请求失败，请检查网络连接',
          code: -1,
        };

        wx.showToast({
          title: error.message,
          icon: 'none',
          duration: 2000,
        });

        reject(error);
      },
    });
  });
};

/**
 * 自动重试（指数退避）
 */
export const requestWithRetry = async <T = any>(
  config: RequestConfig,
  maxRetries = 3
): Promise<T> => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await request<T>(config);
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      // 指数退避：1s, 2s, 4s
      await sleep(Math.pow(2, i) * 1000);
    }
  }
  throw new Error('请求失败');
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * 带 Loading 的请求
 */
export const requestWithLoading = async <T = any>(
  config: RequestConfig,
  loadingText = '加载中...'
): Promise<T> => {
  wx.showLoading({ title: loadingText, mask: true });
  try {
    const result = await request<T>(config);
    wx.hideLoading();
    return result;
  } catch (err) {
    wx.hideLoading();
    throw err;
  }
};
```

### API 模块化

```typescript
// api/menu.ts
import { request } from '../utils/request';

export interface Category {
  category_id: number;
  name: string;
  sort_order: number;
}

export interface Product {
  product_id: number;
  name: string;
  description: string;
  image_url: string | null;
  base_price: number;
  status: string;
  inventory_status: 'in_stock' | 'sold_out';
}

export interface MenuResponse {
  categories: Category[];
  products: Product[];
}

/**
 * 获取菜单
 */
export const getMenu = () => {
  return request<MenuResponse>({
    url: '/api/v1/menu',
    method: 'GET',
  });
};
```

---

## 状态管理（MobX）

### 购物车 Store

```typescript
// stores/cart.ts
import { observable, action, computed } from 'mobx-miniprogram';

export interface CartItem {
  product_id: number;
  product_name: string;
  quantity: number;
  unit_price: number;
  selected_specs: Array<{
    group_id: number;
    group_name: string;
    option_id: number;
    option_name: string;
    price_modifier: number;
  }>;
}

// 本地存储 key
const CART_STORAGE_KEY = 'naicha_cart';

// 加载购物车
const loadCart = (): CartItem[] => {
  try {
    return wx.getStorageSync(CART_STORAGE_KEY) || [];
  } catch (err) {
    console.error('加载购物车失败:', err);
    return [];
  }
};

// 保存购物车
const saveCart = (items: CartItem[]) => {
  try {
    wx.setStorageSync(CART_STORAGE_KEY, items);
  } catch (err) {
    console.error('保存购物车失败:', err);
  }
};

export const cartStore = observable({
  // 状态
  items: loadCart(),

  // 计算属性：总价
  get totalPrice() {
    return this.items.reduce((sum, item) => {
      const specsTotal = item.selected_specs.reduce(
        (s, spec) => s + spec.price_modifier,
        0
      );
      return sum + (item.unit_price + specsTotal) * item.quantity;
    }, 0);
  },

  // 计算属性：总数量
  get totalQuantity() {
    return this.items.reduce((sum, item) => sum + item.quantity, 0);
  },

  // 操作：添加商品
  addItem: action(function (item: CartItem) {
    // 检查是否已存在（相同商品 + 相同规格）
    const existingIndex = this.items.findIndex(
      (i) =>
        i.product_id === item.product_id &&
        JSON.stringify(i.selected_specs) === JSON.stringify(item.selected_specs)
    );

    if (existingIndex !== -1) {
      // 已存在，增加数量
      this.items[existingIndex].quantity += item.quantity;
    } else {
      // 不存在，添加新项
      this.items.push(item);
    }

    saveCart(this.items);

    // 显示提示
    wx.showToast({
      title: '已加入购物车',
      icon: 'success',
      duration: 1500,
    });
  }),

  // 操作：更新数量
  updateQuantity: action(function (productId: number, quantity: number) {
    const item = this.items.find((i) => i.product_id === productId);
    if (item) {
      item.quantity = quantity;
      saveCart(this.items);
    }
  }),

  // 操作：移除商品
  removeItem: action(function (productId: number) {
    this.items = this.items.filter((i) => i.product_id !== productId);
    saveCart(this.items);
  }),

  // 操作：清空购物车
  clearAll: action(function () {
    this.items = [];
    saveCart(this.items);
  }),
});
```

### 页面绑定

```typescript
// pages/cart/cart.ts
import { createStoreBindings } from 'mobx-miniprogram-bindings';
import { cartStore, CartItem } from '../../stores/cart';

Page({
  data: {
    items: [] as CartItem[],
    totalPrice: 0,
    totalQuantity: 0,
  },

  onLoad() {
    // 绑定 Store
    this.storeBindings = createStoreBindings(this, {
      store: cartStore,
      fields: ['items', 'totalPrice', 'totalQuantity'],
      actions: ['updateQuantity', 'removeItem', 'clearAll'],
    });
  },

  onUnload() {
    // 解绑
    this.storeBindings?.destroyStoreBindings();
  },

  // 事件处理：数量变更
  handleQuantityChange(e: any) {
    const { productId, quantity } = e.detail;
    this.updateQuantity(productId, quantity);
  },

  // 事件处理：删除商品
  handleRemove(e: any) {
    const { productId } = e.currentTarget.dataset;
    wx.showModal({
      title: '确认删除',
      content: '确定要删除该商品吗？',
      success: (res) => {
        if (res.confirm) {
          this.removeItem(productId);
        }
      },
    });
  },

  // 结算
  handleCheckout() {
    if (this.data.totalQuantity === 0) {
      wx.showToast({
        title: '购物车为空',
        icon: 'none',
      });
      return;
    }

    wx.navigateTo({ url: '/pages/checkout/checkout' });
  },
});
```

---

## WebSocket 实时通信

### WebSocket 管理器

```typescript
// utils/websocket.ts
type MessageHandler = (data: any) => void;

export class WebSocketManager {
  private socket: WechatMiniprogram.SocketTask | null = null;
  private url: string;
  private token: string;
  private heartbeatTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private connected = false;

  constructor(url: string, token: string) {
    this.url = url;
    this.token = token;
  }

  /**
   * 连接 WebSocket
   */
  connect() {
    if (this.connected) {
      console.log('WebSocket 已连接');
      return;
    }

    console.log('WebSocket 连接中...', this.url);

    this.socket = wx.connectSocket({
      url: `${this.url}?token=${this.token}`,
      success: () => {
        console.log('WebSocket 连接请求已发送');
      },
      fail: (err) => {
        console.error('WebSocket 连接失败:', err);
        this.scheduleReconnect();
      },
    });

    this.socket.onOpen(() => {
      console.log('WebSocket 已连接');
      this.connected = true;
      this.reconnectAttempts = 0;
      this.startHeartbeat();

      // 触发连接成功事件
      this.dispatch('connection.ready', {});
    });

    this.socket.onMessage((res) => {
      try {
        const message = JSON.parse(res.data as string);
        console.log('WebSocket 收到消息:', message.type);

        // 心跳响应
        if (message.type === 'pong') {
          return;
        }

        // 分发消息
        this.dispatch(message.type, message);
      } catch (err) {
        console.error('WebSocket 消息解析失败:', err);
      }
    });

    this.socket.onError((err) => {
      console.error('WebSocket 错误:', err);
      this.connected = false;
      this.stopHeartbeat();
    });

    this.socket.onClose(() => {
      console.log('WebSocket 已断开');
      this.connected = false;
      this.stopHeartbeat();
      this.scheduleReconnect();
    });
  }

  /**
   * 发送消息
   */
  send(data: any) {
    if (!this.connected || !this.socket) {
      console.error('WebSocket 未连接，无法发送消息');
      return;
    }

    this.socket.send({
      data: JSON.stringify(data),
      success: () => {
        console.log('WebSocket 消息已发送');
      },
      fail: (err) => {
        console.error('WebSocket 发送失败:', err);
      },
    });
  }

  /**
   * 订阅消息
   */
  on(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type)!.push(handler);
  }

  /**
   * 取消订阅
   */
  off(type: string, handler: MessageHandler) {
    const handlers = this.handlers.get(type);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  /**
   * 事件分发
   */
  private dispatch(type: string, message: any) {
    const handlers = this.handlers.get(type);
    if (handlers) {
      handlers.forEach((handler) => handler(message));
    }
  }

  /**
   * 心跳（30 秒）
   */
  private startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.connected) {
        this.send({ type: 'ping' });
      }
    }, 30000) as any;
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /**
   * 重连（指数退避）
   */
  private scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('WebSocket 重连次数超限，停止重连');
      return;
    }

    // 指数退避：1s, 2s, 4s, 8s, 16s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`${delay}ms 后尝试重连（第 ${this.reconnectAttempts} 次）`);

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay) as any;
  }

  /**
   * 关闭连接
   */
  close() {
    console.log('WebSocket 主动关闭');
    this.connected = false;
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.socket) {
      this.socket.close({
        success: () => {
          console.log('WebSocket 已关闭');
        },
      });
      this.socket = null;
    }
  }

  /**
   * 是否已连接
   */
  isConnected(): boolean {
    return this.connected;
  }
}

// 创建全局实例
let wsInstance: WebSocketManager | null = null;

export const getWebSocket = (url: string, token: string): WebSocketManager => {
  if (!wsInstance) {
    wsInstance = new WebSocketManager(url, token);
  }
  return wsInstance;
};

export const closeWebSocket = () => {
  if (wsInstance) {
    wsInstance.close();
    wsInstance = null;
  }
};
```

### 使用示例

```typescript
// pages/order-detail/order-detail.ts
import { getWebSocket, closeWebSocket } from '../../utils/websocket';

Page({
  data: {
    orderId: 0,
    order: null as any,
  },

  onLoad(options: any) {
    this.setData({ orderId: parseInt(options.id) });
    this.loadOrderDetail();
    this.connectWebSocket();
  },

  onUnload() {
    closeWebSocket();
  },

  async loadOrderDetail() {
    // 加载订单详情
  },

  connectWebSocket() {
    const token = wx.getStorageSync('auth_token');
    const ws = getWebSocket('wss://api.naicha.com/ws/customer', token);

    // 连接
    ws.connect();

    // 监听订单状态更新
    ws.on('order.status_updated', (message) => {
      console.log('订单状态更新:', message);
      if (message.order.order_id === this.data.orderId) {
        this.setData({ order: message.order });
        wx.showToast({
          title: '订单状态已更新',
          icon: 'success',
        });
      }
    });
  },
});
```

---

## 主题系统（适老化）

### Design Tokens

```json
// styles/tokens.json
{
  "colors": {
    "primary": "#FF6B35",
    "text-primary": "#333333",
    "text-secondary": "#666666",
    "text-tertiary": "#999999",
    "bg-page": "#F5F5F5",
    "bg-card": "#FFFFFF",
    "border": "#E5E5E5"
  },
  "font-sizes": {
    "xs": "24rpx",
    "sm": "28rpx",
    "md": "32rpx",
    "lg": "36rpx",
    "xl": "40rpx",
    "xxl": "48rpx"
  },
  "spacing": {
    "xs": "8rpx",
    "sm": "16rpx",
    "md": "24rpx",
    "lg": "32rpx",
    "xl": "48rpx"
  },
  "radius": {
    "sm": "8rpx",
    "md": "16rpx",
    "lg": "24rpx"
  },
  "elder": {
    "font-sizes": {
      "xs": "32rpx",
      "sm": "36rpx",
      "md": "40rpx",
      "lg": "48rpx",
      "xl": "56rpx",
      "xxl": "64rpx"
    },
    "colors": {
      "text-primary": "#000000",
      "text-secondary": "#333333"
    },
    "touch-target": "88rpx",
    "spacing": {
      "xs": "12rpx",
      "sm": "20rpx",
      "md": "32rpx",
      "lg": "40rpx",
      "xl": "56rpx"
    }
  }
}
```

### 构建脚本

```javascript
// scripts/build-tokens.js
const fs = require('fs');
const path = require('path');
const tokens = require('../styles/tokens.json');

// 生成 CSS 变量
const generateCSSVars = (prefix, obj) => {
  let css = '';
  for (const [key, value] of Object.entries(obj)) {
    if (typeof value === 'object') {
      css += generateCSSVars(`${prefix}-${key}`, value);
    } else {
      css += `  --${prefix}-${key}: ${value};\n`;
    }
  }
  return css;
};

// 生成默认主题
let defaultCSS = '/* 自动生成，请勿手动修改 */\n';
defaultCSS += 'page {\n';
defaultCSS += generateCSSVars('color', tokens.colors);
defaultCSS += generateCSSVars('font-size', tokens['font-sizes']);
defaultCSS += generateCSSVars('spacing', tokens.spacing);
defaultCSS += generateCSSVars('radius', tokens.radius);
defaultCSS += '}\n';

fs.writeFileSync(path.join(__dirname, '../styles/app.wxss'), defaultCSS);
console.log('✅ 默认主题生成成功: styles/app.wxss');

// 生成适老化主题
let elderCSS = '/* 适老化主题，自动生成 */\n';
elderCSS += 'page {\n';
elderCSS += generateCSSVars('color', { ...tokens.colors, ...tokens.elder.colors });
elderCSS += generateCSSVars('font-size', tokens.elder['font-sizes']);
elderCSS += generateCSSVars('spacing', tokens.elder.spacing);
elderCSS += generateCSSVars('radius', tokens.radius);
elderCSS += `  --touch-target: ${tokens.elder['touch-target']};\n`;
elderCSS += '}\n';

fs.writeFileSync(path.join(__dirname, '../styles/app-elder.wxss'), elderCSS);
console.log('✅ 适老化主题生成成功: styles/app-elder.wxss');
```

在 `package.json` 中添加脚本：
```json
{
  "scripts": {
    "build:tokens": "node scripts/build-tokens.js"
  }
}
```

### 主题切换

```typescript
// utils/theme.ts
type Theme = 'default' | 'elder';

const THEME_STORAGE_KEY = 'naicha_theme';

/**
 * 获取当前主题
 */
export const getCurrentTheme = (): Theme => {
  try {
    return wx.getStorageSync(THEME_STORAGE_KEY) || 'default';
  } catch (err) {
    return 'default';
  }
};

/**
 * 设置主题
 */
export const setTheme = (theme: Theme) => {
  try {
    wx.setStorageSync(THEME_STORAGE_KEY, theme);
    // 重启小程序以应用新主题
    wx.reLaunch({ url: '/pages/menu/menu' });
  } catch (err) {
    console.error('设置主题失败:', err);
  }
};

/**
 * 切换主题
 */
export const toggleTheme = () => {
  const current = getCurrentTheme();
  const next = current === 'default' ? 'elder' : 'default';
  setTheme(next);
};
```

### app.json 配置

```json
{
  "pages": [
    "pages/menu/menu",
    "pages/cart/cart",
    "pages/order/order",
    "pages/profile/profile"
  ],
  "window": {
    "navigationBarTitleText": "智能奶茶档口",
    "navigationBarBackgroundColor": "#FF6B35",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#F5F5F5"
  },
  "tabBar": {
    "color": "#999999",
    "selectedColor": "#FF6B35",
    "backgroundColor": "#FFFFFF",
    "list": [
      {
        "pagePath": "pages/menu/menu",
        "text": "菜单",
        "iconPath": "images/tab-menu.png",
        "selectedIconPath": "images/tab-menu-active.png"
      },
      {
        "pagePath": "pages/order/order",
        "text": "订单",
        "iconPath": "images/tab-order.png",
        "selectedIconPath": "images/tab-order-active.png"
      },
      {
        "pagePath": "pages/profile/profile",
        "text": "我的",
        "iconPath": "images/tab-profile.png",
        "selectedIconPath": "images/tab-profile-active.png"
      }
    ]
  },
  "style": "v2",
  "sitemapLocation": "sitemap.json"
}
```

### 在 app.ts 中动态加载主题

```typescript
// app.ts
import { getCurrentTheme } from './utils/theme';

App({
  onLaunch() {
    // 加载主题
    const theme = getCurrentTheme();
    const themeFile = theme === 'elder' ? 'styles/app-elder.wxss' : 'styles/app.wxss';
    
    console.log('当前主题:', theme);
    // 注意：小程序不支持动态加载全局样式
    // 需要在编译时决定使用哪个主题文件
    // 可以通过重启小程序来切换主题
  },
});
```

---

## 性能优化

### 1. 图片优化

```typescript
// 使用云存储 CDN + 参数裁剪
const optimizeImageUrl = (url: string, width = 750) => {
  if (!url) return '';
  // 腾讯云 COS 图片处理参数
  return `${url}?imageMogr2/thumbnail/${width}x/format/webp`;
};
```

### 2. 列表优化（虚拟列表）

```xml
<!-- pages/order/order.wxml -->
<recycle-view batch="{{batchSetRecycleData}}" id="recycleId">
  <recycle-item wx:for="{{orders}}" wx:key="order_id">
    <order-card order="{{item}}" />
  </recycle-item>
</recycle-view>
```

### 3. 分包加载

```json
// app.json
{
  "pages": [
    "pages/menu/menu",
    "pages/cart/cart"
  ],
  "subPackages": [
    {
      "root": "packageProfile",
      "name": "profile",
      "pages": [
        "pages/profile/profile",
        "pages/address/address",
        "pages/coupon/coupon"
      ]
    }
  ],
  "preloadRule": {
    "pages/menu/menu": {
      "network": "all",
      "packages": ["profile"]
    }
  }
}
```

---

## 常见问题

### Q1: MobX 状态不更新？

**A**: 确保使用 `action` 包装状态修改：
```typescript
// ❌ 错误
cartStore.items.push(item);

// ✅ 正确
cartStore.addItem(item);
```

### Q2: WebSocket 频繁断开？

**A**: 检查心跳间隔和后端超时设置：
```typescript
// 心跳间隔应 < 后端超时时间
const HEARTBEAT_INTERVAL = 30000; // 30 秒
```

### Q3: 主题切换不生效？

**A**: 小程序不支持动态加载全局样式，需要：
1. 构建两份主题文件
2. 重启小程序以应用新主题

### Q4: 真机支付失败？

**A**: 检查：
1. `payer_open_id` 必须是真实用户 OpenID
2. 域名已在微信公众平台配置
3. HTTPS 证书有效

---

**最后更新**：2025-10-27  
**版本**：V1.0  
**维护者**：frontend-team@naicha.com
