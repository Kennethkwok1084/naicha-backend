# 智能奶茶档口系统 · 前端（V1.0）

## 目录

* [项目简介](#项目简介)
* [系统架构](#系统架构)
* [核心特性](#核心特性)
* [技术栈](#技术栈)
* [快速开始](#快速开始)
* [项目结构](#项目结构)
* [环境变量](#环境变量)
* [开发指南](#开发指南)
* [API 对接](#api-对接)
* [状态管理](#状态管理)
* [性能优化](#性能优化)
* [测试](#测试)
* [部署](#部署)
* [开发规范](#开发规范)
* [常见问题](#常见问题)
* [路线图](#路线图)

---

## 项目简介

本仓库是"智能奶茶档口系统"的**前端应用集合**，包含三个独立项目：

1. **顾客端小程序**（`/miniapp`）：微信小程序，用户下单、支付、查询订单
2. **商家端 Web**（`/merchant`）：实时接单、订单管理、打印小票、数据看板
3. **管理后台 Web**（`/admin`）：商品管理、库存配置、数据分析、系统设置

配套后端基于 **FastAPI** 构建，已完成所有 API 实现并通过 100 并发压测验证（0% 错误率）。

---

## 系统架构

```
┌─────────────────┐
│  顾客端小程序    │──┐
└─────────────────┘  │
                     ├──► ┌──────────────┐      ┌─────────────┐
┌─────────────────┐  │    │  API Gateway │─────►│  后端服务   │
│  商家端 Web     │──┤    │   (WAF)      │      │  (FastAPI)  │
└─────────────────┘  │    └──────────────┘      └─────────────┘
                     │           │                      │
┌─────────────────┐  │           │                      ├─► PostgreSQL
│  管理后台 Web   │──┘           │                      ├─► Redis
└─────────────────┘              │                      └─► Celery Worker
                                 │
                        ┌────────▼────────┐
                        │  WebSocket      │
                        │  (商家端推送)    │
                        └─────────────────┘
```

**关键组件**：
- **API Gateway**：雷池 WAF，统一入口，限流 + 安全防护
- **后端服务**：K3s 部署（云端 + 家庭混合云），2+ 副本
- **数据库**：PostgreSQL + PgBouncer 连接池
- **缓存**：Redis（菜单缓存 + WebSocket 广播）
- **实时推送**：WebSocket（商家端新订单通知）

---

## 核心特性

### 顾客端小程序
- ✅ 商品菜单浏览（分类、规格、价格）
- ✅ 购物车管理（本地存储，离线可用）
- ✅ 下单流程（自取 / 配送，配送范围校验）
- ✅ 微信支付（JSAPI / Native）
- ✅ 订单查询（状态实时更新，WebSocket 推送）
- ✅ 会员积分（满 10 分自动发券）
- ✅ 优惠券使用（免费任意饮品）
- ✅ **适老化主题**（字号↑、对比↑、触控面积↑）
- 🚧 预约下单（指定时间段取货）
- 🚧 售罄商品"想要"提醒

### 商家端 Web
- ✅ 实时订单面板（WebSocket 推送）
- ✅ 新订单桌面通知 + 声音提示
- ✅ 订单状态流转（待制作 → 制作中 → 待取货 → 完成）
- ✅ 重打小票（失败重试）
- ✅ 数据看板（今日流水、订单数、客单价、Top 5 商品）
- ✅ 订单管理（筛选、排序、导出）
- 🚧 POS 快速建单（线下收银）
- 🚧 静态码匹配（人工确认支付）

### 管理后台 Web
- ✅ 商品管理（CRUD + 图片上传）
- ✅ 分类管理（拖拽排序）
- ✅ 规格管理（糖度、温度、小料等）
- ✅ 库存管理（在售 / 售罄一键切换）
- ✅ 售罄统计（"想要"数据分析）
- ✅ 数据看板（周 / 月维度，同比对比）
- 🚧 预约管理（时段配置、容量限制）
- 🚧 会员管理（积分记录、发券历史）

---

## 技术栈

| 项目 | 框架 | 语言 | UI 组件 | 状态管理 | 网络请求 | 构建工具 | 特性 |
|------|------|------|---------|----------|----------|----------|------|
| **顾客端小程序** | 原生微信小程序 | TypeScript | Vant Weapp | mobx-miniprogram | wx.request 封装 | 微信开发者工具 | 适老化主题 |
| **商家端 Web** | React 18 | TypeScript | Ant Design | Zustand | React Query | Vite | WebSocket 推送 |
| **管理后台 Web** | React 18 | TypeScript | Ant Design | Zustand | React Query | Vite | 图表可视化 |

**共享依赖**：
- **TypeScript**：类型安全
- **ESLint + Prettier**：代码质量
- **Vitest**：单元测试（Web 应用）
- **Playwright**：E2E 测试（Web 应用）
- **zod**：运行时类型校验（小程序）
- **OpenAPI Generator**：自动生成 API 客户端（Web 应用）

---

## 快速开始

### 前置条件
- Node.js 18+
- pnpm 8+（推荐）或 npm
- 微信开发者工具（小程序开发）

### 1. 克隆仓库
```bash
git clone https://github.com/YourOrg/naicha-frontend.git
cd naicha-frontend
```

### 2. 安装依赖
```bash
# 根目录安装（Monorepo 管理）
pnpm install

# 或分别安装
cd miniapp && pnpm install
cd merchant && pnpm install
cd admin && pnpm install
```

### 3. 配置环境变量
```bash
# 顾客端小程序
cp miniapp/.env.example miniapp/.env.development
# 修改 TARO_APP_API_URL 为本地后端地址

# 商家端 Web
cp merchant/.env.example merchant/.env.development
# 修改 VITE_API_BASE_URL 和 VITE_WS_URL

# 管理后台 Web
cp admin/.env.example admin/.env.development
# 修改 VITE_API_BASE_URL
```

### 4. 启动开发服务器

#### 顾客端小程序
```bash
cd miniapp
pnpm dev:weapp  # 微信小程序
# 或使用微信开发者工具打开 miniapp 目录
```
然后在微信开发者工具中导入项目（路径：`miniapp`）

#### 商家端 Web
```bash
cd merchant
pnpm dev
# 访问 http://localhost:3000
```

#### 管理后台 Web
```bash
cd admin
pnpm dev
# 访问 http://localhost:3001
```

### 5. 生成 API 客户端（可选）
如果后端 API 有更新：

```bash
# 从后端导出 OpenAPI 规范
curl http://localhost:8000/openapi.json > openapi.json

# 生成 TypeScript 客户端
pnpm generate-api
```

---

## 项目结构

```
naicha-frontend/
├── miniapp/              # 顾客端小程序
│   ├── src/
│   │   ├── pages/        # 页面（菜单、购物车、订单等）
│   │   ├── components/   # 组件（商品卡片、订单卡片等）
│   │   ├── store/        # 状态管理（Zustand）
│   │   ├── api/          # API 客户端
│   │   ├── utils/        # 工具函数（价格计算、日期格式化等）
│   │   └── app.ts        # 入口文件
│   ├── config/           # Taro 配置
│   └── project.config.json  # 微信小程序配置
│
├── merchant/             # 商家端 Web
│   ├── src/
│   │   ├── pages/        # 页面（订单面板、数据看板等）
│   │   ├── components/   # 组件（订单卡片、图表等）
│   │   ├── store/        # 状态管理（Zustand）
│   │   ├── api/          # API 客户端
│   │   ├── hooks/        # 自定义 Hooks（useWebSocket、useOrders 等）
│   │   └── main.tsx      # 入口文件
│   └── vite.config.ts    # Vite 配置
│
├── admin/                # 管理后台 Web
│   ├── src/
│   │   ├── pages/        # 页面（商品管理、库存管理等）
│   │   ├── components/   # 组件（表格、表单等）
│   │   ├── store/        # 状态管理（Zustand）
│   │   ├── api/          # API 客户端
│   │   └── main.tsx      # 入口文件
│   └── vite.config.ts    # Vite 配置
│
├── shared/               # 共享代码（类型定义、工具函数）
│   ├── types/            # TypeScript 类型
│   ├── utils/            # 通用工具函数
│   └── constants/        # 常量定义
│
├── scripts/              # 脚本（API 生成、构建等）
├── docs/                 # 文档（开发指南、API 对接等）
├── package.json          # Monorepo 配置
└── pnpm-workspace.yaml   # pnpm 工作区配置
```

---

## 环境变量

### 顾客端小程序（`.env.development` / `.env.production`）
```bash
# API 基础 URL
MINIAPP_API_URL=https://api.naicha.com

# 微信小程序 AppID
MINIAPP_WX_APPID=wx1234567890

# WebSocket URL
MINIAPP_WS_URL=wss://api.naicha.com/ws/customer

# 调试模式
MINIAPP_DEBUG=true

# 菜单缓存时间（分钟）
MINIAPP_MENU_CACHE_TTL=5

# 默认主题（default | elder）
MINIAPP_DEFAULT_THEME=default
```

### 商家端 Web（`.env.development` / `.env.production`）
```bash
# API 基础 URL
VITE_API_BASE_URL=http://localhost:8000

# WebSocket URL
VITE_WS_URL=ws://localhost:8000/ws/merchant

# 心跳间隔（毫秒）
VITE_WS_HEARTBEAT_INTERVAL=30000

# 订单轮询间隔（毫秒，WebSocket 断开时）
VITE_ORDER_POLL_INTERVAL=5000
```

### 管理后台 Web（`.env.development` / `.env.production`）
```bash
# API 基础 URL
VITE_API_BASE_URL=http://localhost:8000

# 图片上传 OSS 配置
VITE_OSS_BUCKET=naicha-images
VITE_OSS_REGION=oss-cn-shanghai
VITE_OSS_ENDPOINT=https://oss-cn-shanghai.aliyuncs.com
```

---

## 开发指南

### 1. 启动后端服务
前端开发前，确保后端服务运行中：

```bash
# 后端仓库
cd naicha-backend
docker compose up -d --build

# 验证
curl http://localhost:8000/healthz
# 预期返回：{"status": "healthy"}
```

### 2. 本地开发流程
```bash
# 1. 创建功能分支
git checkout -b feature/order-list

# 2. 启动开发服务器
cd miniapp && pnpm dev:weapp

# 3. 开发 + 热更新
# 修改代码后自动刷新

# 4. 代码检查
pnpm lint

# 5. 单元测试
pnpm test

# 6. 提交代码
git add .
git commit -m "feat: 添加订单列表分页"
git push origin feature/order-list

# 7. 创建 PR
# 在 GitHub 创建 Pull Request
```

### 3. 组件开发示例

**原子组件**（`miniapp/src/components/atoms/Button.tsx`）：
```tsx
import { View } from '@tarojs/components';
import './Button.scss';

interface ButtonProps {
  text: string;
  type?: 'primary' | 'default';
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

export const Button: React.FC<ButtonProps> = ({
  text,
  type = 'default',
  loading = false,
  disabled = false,
  onClick,
}) => {
  const className = `button button--${type} ${disabled ? 'button--disabled' : ''}`;

  return (
    <View className={className} onClick={disabled ? undefined : onClick}>
      {loading ? '加载中...' : text}
    </View>
  );
};
```

**业务组件**（`miniapp/src/components/ProductCard.tsx`）：
```tsx
import { View, Image, Text } from '@tarojs/components';
import { Button } from './atoms/Button';
import './ProductCard.scss';

interface ProductCardProps {
  product: {
    product_id: number;
    name: string;
    description: string;
    image_url: string | null;
    base_price: number;
    inventory_status: 'in_stock' | 'sold_out';
  };
  onAddToCart: (productId: number) => void;
}

export const ProductCard: React.FC<ProductCardProps> = ({ product, onAddToCart }) => {
  const isSoldOut = product.inventory_status === 'sold_out';

  return (
    <View className={`product-card ${isSoldOut ? 'product-card--sold-out' : ''}`}>
      {product.image_url && (
        <Image className="product-card__image" src={product.image_url} mode="aspectFill" />
      )}
      <View className="product-card__body">
        <Text className="product-card__name">{product.name}</Text>
        <Text className="product-card__desc">{product.description}</Text>
        <View className="product-card__footer">
          <Text className="product-card__price">¥{product.base_price.toFixed(2)}</Text>
          {isSoldOut ? (
            <Text className="product-card__sold-out">已售罄</Text>
          ) : (
            <Button text="加入购物车" type="primary" onClick={() => onAddToCart(product.product_id)} />
          )}
        </View>
      </View>
    </View>
  );
};
```

### 4. 状态管理示例

**Store 定义**（`miniapp/src/store/cart.ts`）：
```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface CartItem {
  product_id: number;
  product_name: string;
  quantity: number;
  unit_price: number;
  selected_specs: Array<{
    group_name: string;
    option_name: string;
    price_modifier: number;
  }>;
}

interface CartStore {
  items: CartItem[];
  addItem: (item: CartItem) => void;
  removeItem: (productId: number) => void;
  updateQuantity: (productId: number, quantity: number) => void;
  clearCart: () => void;
  getTotalPrice: () => number;
  getTotalQuantity: () => number;
}

export const useCartStore = create<CartStore>()(
  persist(
    (set, get) => ({
      items: [],

      addItem: (item) => {
        set((state) => {
          const existingItem = state.items.find((i) => i.product_id === item.product_id);
          if (existingItem) {
            return {
              items: state.items.map((i) =>
                i.product_id === item.product_id ? { ...i, quantity: i.quantity + item.quantity } : i
              ),
            };
          }
          return { items: [...state.items, item] };
        });
      },

      removeItem: (productId) => {
        set((state) => ({ items: state.items.filter((i) => i.product_id !== productId) }));
      },

      updateQuantity: (productId, quantity) => {
        set((state) => ({
          items: state.items.map((i) => (i.product_id === productId ? { ...i, quantity } : i)),
        }));
      },

      clearCart: () => {
        set({ items: [] });
      },

      getTotalPrice: () => {
        return get().items.reduce((sum, item) => {
          const specsTotal = item.selected_specs.reduce((s, spec) => s + spec.price_modifier, 0);
          return sum + (item.unit_price + specsTotal) * item.quantity;
        }, 0);
      },

      getTotalQuantity: () => {
        return get().items.reduce((sum, item) => sum + item.quantity, 0);
      },
    }),
    {
      name: 'naicha-cart', // 本地存储 key
    }
  )
);
```

**使用示例**（`miniapp/src/pages/cart/index.tsx`）：
```tsx
import { useCartStore } from '@/store/cart';

export const CartPage = () => {
  const { items, updateQuantity, removeItem, getTotalPrice } = useCartStore();

  return (
    <View>
      {items.map((item) => (
        <CartItem
          key={item.product_id}
          item={item}
          onQuantityChange={(qty) => updateQuantity(item.product_id, qty)}
          onRemove={() => removeItem(item.product_id)}
        />
      ))}
      <View className="cart-footer">
        <Text>总计：¥{getTotalPrice().toFixed(2)}</Text>
        <Button text="去结算" type="primary" />
      </View>
    </View>
  );
};
```

---

## API 对接

### 1. 自动生成 API 客户端

**生成脚本**（`scripts/generate-api.sh`）：
```bash
#!/bin/bash
set -e

# 从后端获取 OpenAPI 规范
curl http://localhost:8000/openapi.json -o openapi.json

# 生成 TypeScript 客户端
npx @openapitools/openapi-generator-cli generate \
  -i openapi.json \
  -g typescript-axios \
  -o shared/api/generated \
  --additional-properties=supportsES6=true,npmName=@naicha/api-client

echo "✅ API 客户端生成成功"
```

### 2. 封装 API 客户端

**基础配置**（`shared/api/client.ts`）：
```typescript
import axios, { AxiosError, AxiosRequestConfig } from 'axios';
import { Configuration, DefaultApi } from './generated';

// 创建 Axios 实例
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
});

// 请求拦截器：注入 Token
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 响应拦截器：统一错误处理
axiosInstance.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      const { status, data } = error.response;
      const errorData = data as { detail?: string; trace_id?: string };

      // 401：Token 过期，跳转登录
      if (status === 401) {
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
      }

      // 429：限流，提示稍后重试
      if (status === 429) {
        console.error('请求过于频繁，请稍后再试');
      }

      // 500+：服务器错误，自动重试
      if (status >= 500 && error.config) {
        return retryRequest(error.config);
      }

      // 打印 trace_id 用于排查
      if (errorData.trace_id) {
        console.error(`[API Error] ${errorData.detail} (trace_id: ${errorData.trace_id})`);
      }
    }
    return Promise.reject(error);
  }
);

// 自动重试逻辑
const retryRequest = async (config: AxiosRequestConfig, retries = 3): Promise<any> => {
  for (let i = 0; i < retries; i++) {
    try {
      await sleep(Math.pow(2, i) * 1000); // 指数退避
      return await axiosInstance.request(config);
    } catch (err) {
      if (i === retries - 1) throw err;
    }
  }
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// 创建 API 实例
const apiConfig = new Configuration();
export const apiClient = new DefaultApi(apiConfig, undefined, axiosInstance);
```

### 3. 使用 React Query 缓存

**封装 Hook**（`merchant/src/hooks/useOrders.ts`）：
```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

// 查询订单列表
export const useOrders = (status?: string) => {
  return useQuery({
    queryKey: ['orders', status],
    queryFn: async () => {
      const response = await apiClient.getOrders({ status });
      return response.data;
    },
    staleTime: 30000, // 30 秒内复用缓存
    refetchInterval: 60000, // 每分钟自动刷新
  });
};

// 更新订单状态
export const useUpdateOrderStatus = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ orderId, status }: { orderId: number; status: string }) => {
      await apiClient.updateOrderStatus(orderId, { status });
    },
    onSuccess: () => {
      // 刷新订单列表缓存
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
};
```

**组件使用**（`merchant/src/pages/Orders.tsx`）：
```tsx
import { useOrders, useUpdateOrderStatus } from '@/hooks/useOrders';

export const OrdersPage = () => {
  const { data: orders, isLoading } = useOrders('paid');
  const { mutate: updateStatus } = useUpdateOrderStatus();

  if (isLoading) return <div>加载中...</div>;

  return (
    <div>
      {orders?.map((order) => (
        <OrderCard
          key={order.order_id}
          order={order}
          onStatusChange={(status) => updateStatus({ orderId: order.order_id, status })}
        />
      ))}
    </div>
  );
};
```

---

## 状态管理

### 小程序状态管理（MobX）

**设计原则**：
1. **单一职责**：每个 Store 只管理一个领域（如购物车、用户信息、菜单缓存）
2. **响应式更新**：使用 MobX observable 自动触发视图更新
3. **持久化按需**：购物车、用户 Token 等使用 `wx.setStorageSync` 持久化

**购物车 Store 示例**（`miniapp/stores/cart.ts`）：
```typescript
import { observable, action, computed } from 'mobx-miniprogram';
import { saveCart, loadCart } from '../utils/storage';

export const cartStore = observable({
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

**页面绑定示例**（`miniapp/pages/cart/cart.ts`）：
```typescript
import { createStoreBindings } from 'mobx-miniprogram-bindings';
import { cartStore } from '../../stores/cart';

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

  // 事件处理
  handleQuantityChange(e) {
    const { productId, quantity } = e.detail;
    this.updateQuantity(productId, quantity);
  },
});
```

---

### Web 应用状态管理（Zustand）

**设计原则**：
1. **单一职责**：每个 Store 只管理一个领域（如用户信息、认证状态）
2. **最小状态**：只存储无法从 API 推导的状态
3. **持久化按需**：仅购物车、用户 Token 等需要持久化

**全局状态示例**（`shared/store/auth.ts`）：
```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthStore {
  token: string | null;
  user: {
    user_id: number;
    nickname: string;
    avatar_url: string;
    loyalty_points: number;
  } | null;
  setAuth: (token: string, user: any) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,

      setAuth: (token, user) => {
        set({ token, user });
        localStorage.setItem('auth_token', token);
      },

      logout: () => {
        set({ token: null, user: null });
        localStorage.removeItem('auth_token');
      },

      isAuthenticated: () => {
        return !!get().token;
      },
    }),
    {
      name: 'naicha-auth',
    }
  )
);
```

---

## 性能优化

### 1. 代码分割
```typescript
// 路由懒加载（React Router）
import { lazy, Suspense } from 'react';

const OrdersPage = lazy(() => import('@/pages/Orders'));
const DashboardPage = lazy(() => import('@/pages/Dashboard'));

const routes = [
  {
    path: '/orders',
    element: (
      <Suspense fallback={<div>加载中...</div>}>
        <OrdersPage />
      </Suspense>
    ),
  },
];
```

### 2. 虚拟滚动
```tsx
import { FixedSizeList } from 'react-window';

const OrderList = ({ orders }) => {
  const Row = ({ index, style }) => (
    <div style={style}>
      <OrderCard order={orders[index]} />
    </div>
  );

  return (
    <FixedSizeList
      height={600}
      itemCount={orders.length}
      itemSize={120}
      width="100%"
    >
      {Row}
    </FixedSizeList>
  );
};
```

### 3. 图片优化
```tsx
// 懒加载 + WebP
<Image
  src={product.image_url}
  alt={product.name}
  loading="lazy"
  srcSet={`${product.image_url}?format=webp 1x, ${product.image_url}?format=webp&w=800 2x`}
/>
```

### 4. 防抖/节流
```typescript
import { debounce } from 'lodash-es';

const handleSearch = debounce((keyword: string) => {
  // 搜索逻辑
}, 300);
```

---

## 测试

### 1. 单元测试（Vitest）

**工具函数测试**（`shared/utils/__tests__/price.test.ts`）：
```typescript
import { describe, it, expect } from 'vitest';
import { calculatePrice } from '../price';

describe('calculatePrice', () => {
  it('应正确计算基础价格', () => {
    const result = calculatePrice(10, []);
    expect(result).toBe(10);
  });

  it('应正确计算带规格加价的价格', () => {
    const result = calculatePrice(10, [
      { price_modifier: 2 },
      { price_modifier: 3 },
    ]);
    expect(result).toBe(15);
  });
});
```

**组件测试**（`miniapp/src/components/__tests__/ProductCard.test.tsx`）：
```typescript
import { render, fireEvent } from '@testing-library/react';
import { ProductCard } from '../ProductCard';

describe('ProductCard', () => {
  const mockProduct = {
    product_id: 1,
    name: '珍珠奶茶',
    description: '经典款',
    image_url: 'https://example.com/image.jpg',
    base_price: 12.5,
    inventory_status: 'in_stock',
  };

  it('应正确渲染商品信息', () => {
    const { getByText } = render(<ProductCard product={mockProduct} onAddToCart={vi.fn()} />);
    expect(getByText('珍珠奶茶')).toBeInTheDocument();
    expect(getByText('¥12.50')).toBeInTheDocument();
  });

  it('售罄商品应禁用按钮', () => {
    const soldOutProduct = { ...mockProduct, inventory_status: 'sold_out' };
    const { getByText } = render(<ProductCard product={soldOutProduct} onAddToCart={vi.fn()} />);
    expect(getByText('已售罄')).toBeInTheDocument();
  });

  it('点击加入购物车应触发回调', () => {
    const handleAddToCart = vi.fn();
    const { getByText } = render(<ProductCard product={mockProduct} onAddToCart={handleAddToCart} />);
    fireEvent.click(getByText('加入购物车'));
    expect(handleAddToCart).toHaveBeenCalledWith(1);
  });
});
```

### 2. E2E 测试（Playwright）

**下单流程测试**（`tests/e2e/order.spec.ts`）：
```typescript
import { test, expect } from '@playwright/test';

test('完整下单流程', async ({ page }) => {
  // 1. 访问菜单页面
  await page.goto('http://localhost:3000/menu');

  // 2. 点击商品
  await page.click('text=珍珠奶茶');

  // 3. 选择规格
  await page.click('text=正常糖');
  await page.click('text=常温');

  // 4. 加入购物车
  await page.click('text=加入购物车');

  // 5. 进入购物车
  await page.click('[data-testid="cart-icon"]');
  await expect(page.locator('text=珍珠奶茶')).toBeVisible();

  // 6. 结算
  await page.click('text=去结算');

  // 7. 选择自取
  await page.click('text=自取');

  // 8. 提交订单
  await page.click('text=提交订单');

  // 9. 验证订单创建成功
  await expect(page.locator('text=订单已创建')).toBeVisible();
});
```

**运行测试**：
```bash
# 单元测试
pnpm test

# E2E 测试
pnpm test:e2e

# 覆盖率报告
pnpm test:coverage
```

---

## 部署

### 顾客端小程序

#### 1. 构建
```bash
cd miniapp
pnpm build:weapp  # 微信小程序
```

#### 2. 上传代码
1. 打开微信开发者工具
2. 导入项目（路径：`miniapp/dist`）
3. 点击"上传"按钮
4. 填写版本号和备注

#### 3. 提交审核
1. 登录微信公众平台
2. 进入"版本管理"
3. 选择刚上传的版本，点击"提交审核"
4. 填写审核信息（功能描述、测试账号等）

#### 4. 发布
审核通过后，点击"全量发布"

---

### 商家端 & 管理后台 Web

#### 1. 构建
```bash
cd merchant
pnpm build  # 输出到 dist/

cd admin
pnpm build  # 输出到 dist/
```

#### 2. 部署到 CDN
```bash
# 上传到阿里云 OSS
ossutil cp -r dist/ oss://naicha-merchant/ --update

# 或使用腾讯云 COS
coscmd upload -r dist/ naicha-merchant/
```

#### 3. Nginx 配置
```nginx
# /etc/nginx/conf.d/merchant.conf
server {
    listen 443 ssl http2;
    server_name merchant.naicha.com;

    ssl_certificate /etc/ssl/certs/naicha.com.crt;
    ssl_certificate_key /etc/ssl/private/naicha.com.key;

    root /var/www/naicha-merchant;
    index index.html;

    # SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket 支持
    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 4. Docker 部署（可选）
```dockerfile
# Dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

```bash
# 构建镜像
docker build -t naicha-merchant:latest .

# 运行容器
docker run -d -p 80:80 naicha-merchant:latest
```

---

## 开发规范

### 1. 代码风格
- **TypeScript 强制**：所有文件必须使用 TypeScript
- **禁用 any**：使用 `unknown` 或具体类型
- **命名规范**：
  - 组件：PascalCase（`ProductCard.tsx`）
  - 函数：camelCase（`fetchMenu`）
  - 常量：UPPER_SNAKE_CASE（`API_BASE_URL`）
  - CSS 类：kebab-case（`product-card`）

### 2. 提交规范（Conventional Commits）
```bash
# 格式
<type>(<scope>): <subject>

# 类型
feat: 新功能
fix: 修复 Bug
docs: 文档更新
style: 代码格式（不影响逻辑）
refactor: 重构
test: 测试
chore: 构建/工具配置

# 示例
feat(miniapp): 添加订单列表分页
fix(merchant): 修复 WebSocket 重连逻辑
docs(readme): 更新部署指南
```

### 3. PR 检查清单
- [ ] 代码通过 ESLint 检查（`pnpm lint`）
- [ ] 所有测试通过（`pnpm test`）
- [ ] 新功能有单元测试覆盖
- [ ] 关键流程有 E2E 测试
- [ ] 无 TypeScript 错误（`pnpm type-check`）
- [ ] 无 console.log 残留
- [ ] 更新相关文档（README、开发指南等）

---

## 常见问题

### Q1: API 请求返回 401，但 Token 有效？
**A**: 检查 Token 是否正确注入到请求头：
```typescript
// 确认拦截器正确设置
axiosInstance.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  console.log('Token:', token); // 调试日志
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

### Q2: 小程序真机支付失败？
**A**: 检查以下几点：
1. `payer_open_id` 是否为真实用户的 OpenID（不能用 `mock-openid`）
2. 微信商户号配置是否正确
3. 域名是否已在微信公众平台配置为"服务器域名"
4. HTTPS 证书是否有效

### Q3: WebSocket 频繁断开？
**A**: 增加心跳频率和超时时间：
```typescript
const HEARTBEAT_INTERVAL = 30000; // 30 秒
const HEARTBEAT_TIMEOUT = 35000; // 35 秒超时

// 心跳逻辑见上文 WebSocket 实现
```

### Q4: 菜单缓存不刷新？
**A**: 检查缓存失效逻辑：
```typescript
// 后端更新库存后会自动触发菜单缓存失效
// 前端需设置合理的 staleTime（建议 5 分钟）
useQuery({
  queryKey: ['menu'],
  queryFn: fetchMenu,
  staleTime: 300000, // 5 分钟
});
```

### Q5: 订单状态不更新？
**A**: 使用 React Query 的自动失效机制：
```typescript
// 更新订单后失效缓存
const { mutate } = useMutation({
  mutationFn: updateOrderStatus,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['orders'] });
  },
});
```

---

## 路线图

### V1.0（当前版本）
- ✅ 顾客端小程序（菜单、购物车、下单、支付、订单查询）
- ✅ 商家端 Web（实时订单面板、订单管理、数据看板）
- ✅ 管理后台 Web（商品管理、库存管理、数据分析）

### V1.1（计划中）
- 🚧 预约下单功能
- 🚧 售罄商品"想要"提醒
- 🚧 POS 快速建单
- 🚧 静态码匹配人工确认
- 🚧 会员管理（积分记录、发券历史）

### V1.2（未来计划）
- 🔭 订单叫号屏（数字大屏）
- 🔭 会员等级系统
- 🔭 A/B 实验与推荐
- 🔭 多门店支持
- 🔭 优惠活动管理

---

## 许可证

本项目默认**私有**。如需开源，请联系项目负责人。

---

## 联系方式

- **技术支持**：frontend-team@naicha.com
- **产品需求**：product@naicha.com
- **紧急联系**：oncall@naicha.com（7×24）

---

**最后更新**：2025-10-27  
**版本**：V1.0  
**状态**：开发中
