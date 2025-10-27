# 前端开发指南（V1.0）

---

## 目录

* [开发环境搭建](#开发环境搭建)
* [项目初始化](#项目初始化)
* [开发工作流](#开发工作流)
* [API 对接详解](#api-对接详解)
* [状态管理最佳实践](#状态管理最佳实践)
* [性能优化清单](#性能优化清单)
* [测试策略](#测试策略)
* [调试技巧](#调试技巧)
* [常见问题排查](#常见问题排查)
* [生产部署检查清单](#生产部署检查清单)

---

## 开发环境搭建

### 1. 基础工具安装

#### Node.js（推荐 v18+）
```bash
# 使用 nvm 安装（推荐）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
nvm install 18
nvm use 18

# 验证版本
node --version  # v18.x.x
npm --version   # v9.x.x
```

#### pnpm（推荐，比 npm 快 2-3 倍）
```bash
npm install -g pnpm@8

# 验证版本
pnpm --version  # 8.x.x
```

#### 微信开发者工具（小程序开发必需）
1. 访问 [微信开放平台](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 下载对应平台的安装包
3. 安装并登录微信账号

#### VSCode 推荐插件
```json
// .vscode/extensions.json
{
  "recommendations": [
    "dbaeumer.vscode-eslint",          // ESLint
    "esbenp.prettier-vscode",          // Prettier
    "bradlc.vscode-tailwindcss",       // Tailwind CSS
    "styled-components.vscode-styled-components", // CSS-in-JS
    "ZixuanChen.vitest-explorer",      // Vitest 测试运行器
    "Orta.vscode-jest",                // Jest 支持
    "ms-playwright.playwright"         // Playwright E2E
  ]
}
```

---

### 2. 克隆仓库并安装依赖

```bash
# 克隆前端仓库
git clone https://github.com/YourOrg/naicha-frontend.git
cd naicha-frontend

# 安装依赖（Monorepo 统一管理）
pnpm install

# 或分别安装各子项目
cd miniapp && pnpm install
cd merchant && pnpm install
cd admin && pnpm install
```

---

### 3. 配置环境变量

#### 顾客端小程序
```bash
cd miniapp
cp .env.example .env.development

# 编辑 .env.development
TARO_APP_API_URL=http://localhost:8000
TARO_APP_WX_APPID=wx1234567890  # 测试 AppID
TARO_APP_DEBUG=true
```

#### 商家端 Web
```bash
cd merchant
cp .env.example .env.development

# 编辑 .env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws/merchant
VITE_WS_HEARTBEAT_INTERVAL=30000
```

#### 管理后台 Web
```bash
cd admin
cp .env.example .env.development

# 编辑 .env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_OSS_BUCKET=naicha-images-dev  # 开发环境 OSS
```

---

### 4. 启动后端服务

前端开发依赖后端 API，确保后端服务正常运行：

```bash
# 克隆后端仓库
git clone https://github.com/YourOrg/naicha-backend.git
cd naicha-backend

# 使用 Docker Compose 启动
docker compose up -d --build

# 等待服务启动（约 30 秒）
# 验证健康检查
curl http://localhost:8000/healthz
# 预期返回：{"status": "healthy"}

# 查看 API 文档
open http://localhost:8000/docs
```

---

### 5. 启动前端开发服务器

#### 顾客端小程序
```bash
cd miniapp
pnpm dev:weapp  # 微信小程序
# 或 pnpm dev:h5  # H5 调试（更快）

# 在微信开发者工具中导入项目
# 路径：miniapp/dist
# AppID：使用测试号或真实 AppID
```

#### 商家端 Web
```bash
cd merchant
pnpm dev

# 访问 http://localhost:3000
# 默认测试账号：
# 用户名：admin
# 密码：admin123
```

#### 管理后台 Web
```bash
cd admin
pnpm dev

# 访问 http://localhost:3001
# 默认测试账号：
# 用户名：admin
# 密码：admin123
```

---

## 项目初始化

### 创建新项目（从模板）

#### 1. 顾客端小程序（原生微信小程序 + TypeScript）
```bash
# 使用微信开发者工具创建项目
# 1. 打开微信开发者工具
# 2. 新建项目 → 选择"小程序" → "不使用云服务"
# 3. AppID：使用测试号或真实 AppID
# 4. 语言：TypeScript

# 或使用 CLI 快速创建（需要 wechat-miniprogram-cli）
npm install -g wechat-miniprogram-cli
wechat-miniprogram-cli create miniapp

# 进入项目目录
cd miniapp

# 安装依赖
npm install

# 安装核心依赖
npm install mobx-miniprogram mobx-miniprogram-bindings
npm install @vant/weapp
npm install zod
npm install miniprogram-api-typings --save-dev
```

**项目结构**：
```
miniapp/
├── pages/               # 页面
│   ├── menu/            # 菜单页（首页）
│   │   ├── menu.ts
│   │   ├── menu.wxml
│   │   ├── menu.wxss
│   │   └── menu.json
│   ├── cart/            # 购物车
│   ├── order/           # 订单列表
│   └── profile/         # 个人中心
├── components/          # 组件
│   ├── product-card/    # 商品卡片
│   ├── order-card/      # 订单卡片
│   └── spec-selector/   # 规格选择器
├── stores/              # MobX 状态管理
│   ├── cart.ts          # 购物车状态
│   ├── menu.ts          # 菜单缓存
│   └── user.ts          # 用户信息
├── utils/               # 工具函数
│   ├── request.ts       # wx.request 封装
│   ├── websocket.ts     # wx.connectSocket 封装
│   ├── storage.ts       # wx.storage 封装
│   └── theme.ts         # 主题切换
├── styles/              # 样式
│   ├── tokens.json      # 设计 tokens
│   ├── app.wxss         # 默认主题
│   └── app-elder.wxss   # 适老化主题
├── app.ts               # 入口文件
├── app.json             # 小程序配置
├── app.wxss             # 全局样式
├── project.config.json  # 项目配置
├── tsconfig.json        # TypeScript 配置
└── package.json
```

**安装 Vant Weapp**：
```bash
# 通过 npm 安装
npm i @vant/weapp -S --production

# 修改 project.config.json
{
  "setting": {
    "packNpmManually": true,
    "packNpmRelationList": [
      {
        "packageJsonPath": "./package.json",
        "miniprogramNpmDistDir": "./miniprogram/"
      }
    ]
  }
}

# 构建 npm
# 在微信开发者工具中：工具 → 构建 npm
```

**TypeScript 配置**：
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
    "types": ["miniprogram-api-typings"]
  },
  "include": ["**/*.ts"],
  "exclude": ["node_modules"]
}
```

#### 2. 商家端/管理后台 Web（React + Vite）
```bash
# 使用 Vite 创建
pnpm create vite merchant --template react-ts

cd merchant
pnpm install

# 安装依赖
pnpm add react-router-dom zustand @tanstack/react-query
pnpm add antd axios @ant-design/icons
pnpm add -D @types/node tailwindcss postcss autoprefixer
pnpm add -D vitest @testing-library/react @testing-library/jest-dom
pnpm add -D @playwright/test
```

**项目结构**：
```
merchant/
├── src/
│   ├── pages/          # 页面
│   │   ├── Dashboard/  # 数据看板
│   │   ├── Orders/     # 订单管理
│   │   ├── Login/      # 登录页
│   │   └── NotFound/   # 404
│   ├── components/     # 组件
│   │   ├── Layout/     # 布局组件
│   │   ├── OrderCard/  # 订单卡片
│   │   └── Chart/      # 图表组件
│   ├── store/          # 状态管理
│   │   ├── auth.ts     # 认证状态
│   │   └── ws.ts       # WebSocket 状态
│   ├── api/            # API 客户端
│   │   ├── client.ts   # Axios 配置
│   │   └── generated/  # OpenAPI 生成代码
│   ├── hooks/          # 自定义 Hooks
│   │   ├── useOrders.ts    # 订单查询
│   │   ├── useWebSocket.ts # WebSocket 连接
│   │   └── useDashboard.ts # 看板数据
│   ├── utils/          # 工具函数
│   ├── router.tsx      # 路由配置
│   ├── main.tsx        # 入口文件
│   └── App.tsx         # 根组件
├── public/             # 静态资源
├── tests/              # 测试
│   ├── unit/           # 单元测试
│   └── e2e/            # E2E 测试
├── vite.config.ts      # Vite 配置
├── tailwind.config.js  # Tailwind CSS 配置
└── package.json
```

---

## 开发工作流

### 1. 功能开发流程

#### Step 1: 创建功能分支
```bash
git checkout -b feature/order-list

# 命名规范
# feature/*  新功能
# fix/*      Bug 修复
# refactor/* 重构
# docs/*     文档更新
```

#### Step 2: 实现功能
```bash
# 1. 创建页面/组件
# 2. 实现业务逻辑
# 3. 编写单元测试
# 4. 本地调试验证

# 实时查看效果
pnpm dev  # 热更新自动刷新
```

#### Step 3: 代码检查
```bash
# ESLint 检查
pnpm lint

# TypeScript 类型检查
pnpm type-check

# 自动修复格式问题
pnpm lint:fix
```

#### Step 4: 运行测试
```bash
# 单元测试
pnpm test

# 测试覆盖率
pnpm test:coverage

# E2E 测试（关键流程）
pnpm test:e2e
```

#### Step 5: 提交代码
```bash
# 暂存更改
git add .

# 提交（遵循 Conventional Commits）
git commit -m "feat(miniapp): 添加订单列表分页功能"

# 推送到远程
git push origin feature/order-list
```

#### Step 6: 创建 Pull Request
1. 在 GitHub 创建 PR
2. 填写 PR 模板：
   - 功能描述
   - 测试结果截图
   - 相关 Issue 链接
   - 检查清单（已完成的勾选 ✅）
3. 请求代码审查

---

### 2. 日常开发技巧

#### 快速调试接口
```typescript
// src/api/debug.ts
import { apiClient } from './client';

// 快速测试 API
export const debugAPI = async () => {
  // 1. 测试菜单接口
  const menu = await apiClient.getMenu();
  console.log('Menu:', menu.data);

  // 2. 测试创建订单
  const order = await apiClient.createOrder({
    items: [
      {
        product_id: 1,
        quantity: 1,
        spec_option_ids: [1, 2],
      },
    ],
    order_type: 'pickup',
  });
  console.log('Order:', order.data);
};

// 在控制台调用
// debugAPI();
```

#### 使用 React DevTools
```bash
# 安装浏览器插件
# Chrome: https://chrome.google.com/webstore/detail/react-developer-tools
# Firefox: https://addons.mozilla.org/firefox/addon/react-devtools/

# 查看组件树、Props、State
# 性能分析：Profiler 标签
```

#### Zustand DevTools
```typescript
import { devtools } from 'zustand/middleware';

export const useCartStore = create<CartStore>()(
  devtools(
    persist(
      (set, get) => ({
        // ... store 实现
      }),
      { name: 'naicha-cart' }
    ),
    { name: 'CartStore' } // DevTools 中显示的名称
  )
);
```

---

## API 对接详解

### 1. 生成 API 客户端

#### 从后端获取 OpenAPI 规范
```bash
# 方式 1：直接下载
curl http://localhost:8000/openapi.json -o openapi.json

# 方式 2：从后端仓库复制
cp ../naicha-backend/naicha-openapi.json ./openapi.json
```

#### 使用 OpenAPI Generator 生成代码
```bash
# 安装工具（全局）
npm install -g @openapitools/openapi-generator-cli

# 生成 TypeScript Axios 客户端
openapi-generator-cli generate \
  -i openapi.json \
  -g typescript-axios \
  -o shared/api/generated \
  --additional-properties=supportsES6=true,npmName=@naicha/api-client

# 生成后的文件结构
# shared/api/generated/
# ├── api.ts           # API 类定义
# ├── base.ts          # 基础配置
# ├── common.ts        # 通用类型
# ├── configuration.ts # 配置类
# └── index.ts         # 导出
```

#### 封装 API 客户端
```typescript
// shared/api/client.ts
import axios, { AxiosError, AxiosRequestConfig } from 'axios';
import { Configuration, DefaultApi } from './generated';

// 创建 Axios 实例
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：注入 Token
axiosInstance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器：统一错误处理
axiosInstance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response) {
      const { status, data } = error.response;
      const errorData = data as { detail?: string; trace_id?: string };

      // 401：Token 过期，跳转登录
      if (status === 401) {
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      // 403：权限不足
      if (status === 403) {
        console.error('权限不足');
      }

      // 429：限流
      if (status === 429) {
        console.error('请求过于频繁，请稍后再试');
      }

      // 500+：服务器错误，自动重试
      if (status >= 500 && error.config) {
        const retryCount = (error.config as any).__retryCount || 0;
        if (retryCount < 3) {
          (error.config as any).__retryCount = retryCount + 1;
          await sleep(Math.pow(2, retryCount) * 1000); // 指数退避
          return axiosInstance.request(error.config);
        }
      }

      // 打印 trace_id 用于排查
      if (errorData.trace_id) {
        console.error(`[API Error] ${errorData.detail} (trace_id: ${errorData.trace_id})`);
      }
    } else if (error.request) {
      // 网络错误
      console.error('网络请求失败，请检查网络连接');
    }

    return Promise.reject(error);
  }
);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// 创建 API 实例
const apiConfig = new Configuration();
export const apiClient = new DefaultApi(apiConfig, undefined, axiosInstance);
```

---

### 2. 幂等性处理

创建订单等接口需要 `Idempotency-Key` 请求头：

```typescript
// shared/api/idempotency.ts
import { v4 as uuidv4 } from 'uuid';
import { apiClient } from './client';

/**
 * 创建订单（幂等）
 */
export const createOrderIdempotent = async (orderData: CreateOrderRequest) => {
  const idempotencyKey = uuidv4();

  const response = await apiClient.post('/api/v1/orders', orderData, {
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  });

  return response.data;
};
```

---

### 3. 使用 React Query 缓存

#### 封装自定义 Hook
```typescript
// merchant/src/hooks/useOrders.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

/**
 * 查询订单列表
 */
export const useOrders = (status?: string) => {
  return useQuery({
    queryKey: ['orders', status],
    queryFn: async () => {
      const response = await apiClient.getOrders({ status });
      return response.data;
    },
    staleTime: 30000, // 30 秒内复用缓存
    refetchInterval: 60000, // 每分钟自动刷新
    refetchOnWindowFocus: true, // 窗口聚焦时刷新
  });
};

/**
 * 更新订单状态
 */
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
    onError: (error) => {
      console.error('更新订单状态失败:', error);
    },
  });
};
```

#### 组件使用示例
```tsx
// merchant/src/pages/Orders.tsx
import { useOrders, useUpdateOrderStatus } from '@/hooks/useOrders';

export const OrdersPage = () => {
  const { data: orders, isLoading, error } = useOrders('paid');
  const { mutate: updateStatus, isLoading: isUpdating } = useUpdateOrderStatus();

  if (isLoading) return <div>加载中...</div>;
  if (error) return <div>加载失败，请重试</div>;

  return (
    <div>
      {orders?.map((order) => (
        <OrderCard
          key={order.order_id}
          order={order}
          onStatusChange={(status) => updateStatus({ orderId: order.order_id, status })}
          isUpdating={isUpdating}
        />
      ))}
    </div>
  );
};
```

---

## 状态管理最佳实践

### 1. Zustand Store 设计原则

#### 全局状态分类
- **认证状态**（`useAuthStore`）：Token、用户信息
- **购物车状态**（`useCartStore`）：商品列表、总价
- **菜单缓存**（`useMenuStore`）：分类、商品（可选，优先使用 React Query）
- **WebSocket 状态**（`useWSStore`）：连接状态、消息队列

#### Store 模板
```typescript
// shared/store/template.ts
import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';

interface TemplateState {
  // 状态字段
  count: number;

  // 操作方法
  increment: () => void;
  decrement: () => void;
  reset: () => void;
}

export const useTemplateStore = create<TemplateState>()(
  devtools(
    persist(
      (set, get) => ({
        // 初始状态
        count: 0,

        // 操作方法
        increment: () => set((state) => ({ count: state.count + 1 })),
        decrement: () => set((state) => ({ count: state.count - 1 })),
        reset: () => set({ count: 0 }),
      }),
      {
        name: 'template-store', // 本地存储 key
        partialize: (state) => ({ count: state.count }), // 只持久化部分字段
      }
    ),
    { name: 'TemplateStore' } // DevTools 显示名称
  )
);
```

---

### 2. 购物车状态管理实战

```typescript
// miniapp/src/store/cart.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface CartItem {
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
          // 检查是否已存在（相同商品 + 相同规格）
          const existingIndex = state.items.findIndex(
            (i) =>
              i.product_id === item.product_id &&
              JSON.stringify(i.selected_specs) === JSON.stringify(item.selected_specs)
          );

          if (existingIndex !== -1) {
            // 已存在，增加数量
            const newItems = [...state.items];
            newItems[existingIndex].quantity += item.quantity;
            return { items: newItems };
          }

          // 不存在，添加新项
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
      name: 'naicha-cart',
    }
  )
);
```

**使用示例**：
```tsx
import { useCartStore } from '@/store/cart';

export const CartPage = () => {
  const { items, updateQuantity, removeItem, getTotalPrice, clearCart } = useCartStore();

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
        <Button text="清空购物车" onClick={clearCart} />
        <Button text="去结算" type="primary" />
      </View>
    </View>
  );
};
```

---

## 性能优化清单

### 1. 打包优化

#### Vite 配置（Web 应用）
```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({ open: true }), // 打包分析
  ],
  build: {
    rollupOptions: {
      output: {
        // 代码分割
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'ui-vendor': ['antd', '@ant-design/icons'],
          'query-vendor': ['@tanstack/react-query'],
        },
      },
    },
    // 压缩
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true, // 移除 console.log
        drop_debugger: true,
      },
    },
  },
});
```

#### 分析打包体积
```bash
# 构建并生成分析报告
pnpm build

# 查看 stats.html（自动打开浏览器）
# 识别大文件并优化
```

---

### 2. 运行时优化

#### React.memo（避免不必要的重渲染）
```tsx
import { memo } from 'react';

interface ProductCardProps {
  product: Product;
  onAddToCart: (id: number) => void;
}

export const ProductCard = memo<ProductCardProps>(({ product, onAddToCart }) => {
  // 组件实现
}, (prevProps, nextProps) => {
  // 自定义比较逻辑（可选）
  return prevProps.product.product_id === nextProps.product.product_id;
});
```

#### useMemo / useCallback
```tsx
import { useMemo, useCallback } from 'react';

export const OrderList = ({ orders }) => {
  // 缓存计算结果
  const totalAmount = useMemo(() => {
    return orders.reduce((sum, order) => sum + order.total_price, 0);
  }, [orders]);

  // 缓存回调函数
  const handleOrderClick = useCallback((orderId: number) => {
    console.log('Order clicked:', orderId);
  }, []);

  return (
    <div>
      <div>总金额：¥{totalAmount.toFixed(2)}</div>
      {orders.map((order) => (
        <OrderCard key={order.order_id} order={order} onClick={handleOrderClick} />
      ))}
    </div>
  );
};
```

#### 虚拟滚动（长列表）
```tsx
import { FixedSizeList } from 'react-window';

export const OrderList = ({ orders }) => {
  const Row = ({ index, style }) => (
    <div style={style}>
      <OrderCard order={orders[index]} />
    </div>
  );

  return (
    <FixedSizeList
      height={600}       // 可视区域高度
      itemCount={orders.length}
      itemSize={120}     // 每项高度
      width="100%"
    >
      {Row}
    </FixedSizeList>
  );
};
```

---

### 3. 图片优化

#### 懒加载
```tsx
<img
  src={product.image_url}
  alt={product.name}
  loading="lazy"  // 原生懒加载
/>
```

#### WebP 格式 + 响应式
```tsx
<picture>
  <source srcSet={`${product.image_url}?format=webp`} type="image/webp" />
  <img src={product.image_url} alt={product.name} />
</picture>
```

#### 占位符（避免布局抖动）
```tsx
<img
  src={product.image_url}
  alt={product.name}
  style={{ aspectRatio: '1 / 1' }}  // 固定宽高比
  loading="lazy"
/>
```

---

### 4. 防抖/节流

```typescript
// shared/utils/debounce.ts
export const debounce = <T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): ((...args: Parameters<T>) => void) => {
  let timer: NodeJS.Timeout | null = null;

  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
};

// shared/utils/throttle.ts
export const throttle = <T extends (...args: any[]) => any>(
  fn: T,
  delay: number
): ((...args: Parameters<T>) => void) => {
  let lastTime = 0;

  return (...args: Parameters<T>) => {
    const now = Date.now();
    if (now - lastTime >= delay) {
      lastTime = now;
      fn(...args);
    }
  };
};
```

**使用示例**：
```tsx
import { debounce } from '@/utils/debounce';

export const SearchBar = () => {
  const handleSearch = debounce((keyword: string) => {
    // 搜索逻辑
    console.log('Search:', keyword);
  }, 300);

  return <input type="text" onChange={(e) => handleSearch(e.target.value)} />;
};
```

---

## 测试策略

### 1. 单元测试（Vitest）

#### 配置
```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: ['node_modules/', 'tests/'],
    },
  },
});
```

#### 测试示例
```typescript
// shared/utils/__tests__/price.test.ts
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

  it('应处理负数加价（折扣）', () => {
    const result = calculatePrice(10, [{ price_modifier: -2 }]);
    expect(result).toBe(8);
  });
});
```

---

### 2. 组件测试（React Testing Library）

```typescript
// miniapp/src/components/__tests__/ProductCard.test.tsx
import { render, fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
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
    render(<ProductCard product={mockProduct} onAddToCart={vi.fn()} />);

    expect(screen.getByText('珍珠奶茶')).toBeInTheDocument();
    expect(screen.getByText('¥12.50')).toBeInTheDocument();
    expect(screen.getByText('经典款')).toBeInTheDocument();
  });

  it('售罄商品应禁用按钮', () => {
    const soldOutProduct = { ...mockProduct, inventory_status: 'sold_out' };
    render(<ProductCard product={soldOutProduct} onAddToCart={vi.fn()} />);

    expect(screen.getByText('已售罄')).toBeInTheDocument();
    expect(screen.queryByText('加入购物车')).not.toBeInTheDocument();
  });

  it('点击加入购物车应触发回调', () => {
    const handleAddToCart = vi.fn();
    render(<ProductCard product={mockProduct} onAddToCart={handleAddToCart} />);

    fireEvent.click(screen.getByText('加入购物车'));
    expect(handleAddToCart).toHaveBeenCalledWith(1);
  });
});
```

---

### 3. E2E 测试（Playwright）

#### 配置
```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

#### 测试示例
```typescript
// tests/e2e/order.spec.ts
import { test, expect } from '@playwright/test';

test('完整下单流程', async ({ page }) => {
  // 1. 访问菜单页面
  await page.goto('/menu');
  await expect(page.locator('h1')).toContainText('菜单');

  // 2. 点击商品
  await page.click('text=珍珠奶茶');

  // 3. 选择规格
  await page.click('text=正常糖');
  await page.click('text=常温');

  // 4. 加入购物车
  await page.click('text=加入购物车');
  await expect(page.locator('.toast')).toContainText('已加入购物车');

  // 5. 进入购物车
  await page.click('[data-testid="cart-icon"]');
  await expect(page.locator('.cart-item')).toContainText('珍珠奶茶');

  // 6. 结算
  await page.click('text=去结算');

  // 7. 选择自取
  await page.click('text=自取');

  // 8. 提交订单
  await page.click('text=提交订单');

  // 9. 验证订单创建成功
  await expect(page.locator('.order-success')).toBeVisible();
  await expect(page.locator('.order-number')).toContainText(/\d{8,}/);
});

test('支付失败重试', async ({ page }) => {
  // 模拟支付失败场景
  await page.route('**/api/v1/orders/*/pay/jsapi', (route) => {
    route.fulfill({ status: 500 });
  });

  await page.goto('/order/123');
  await page.click('text=去支付');

  // 应显示重试按钮
  await expect(page.locator('text=重试')).toBeVisible();
});
```

---

## 调试技巧

### 1. 浏览器调试

#### 断点调试
```typescript
// 在代码中设置断点
const handleClick = () => {
  debugger; // 浏览器会在此处暂停
  console.log('Button clicked');
};
```

#### 条件断点
```javascript
// 在浏览器 DevTools 中设置
// 右键点击行号 → "Add conditional breakpoint"
// 输入条件：order.status === 'paid'
```

#### 网络请求监控
```javascript
// 在 Console 中监控所有 API 请求
const originalFetch = window.fetch;
window.fetch = async (...args) => {
  console.log('[Fetch]', args[0]);
  const response = await originalFetch(...args);
  console.log('[Response]', response.status, response.statusText);
  return response;
};
```

---

### 2. React DevTools

#### 查看组件 Props
1. 打开 React DevTools
2. 选择组件
3. 右侧面板查看 Props 和 State

#### 性能分析
1. 切换到 "Profiler" 标签
2. 点击 "Start profiling"
3. 执行操作（如加载订单列表）
4. 点击 "Stop profiling"
5. 查看火焰图，识别慢组件

---

### 3. Zustand DevTools

#### 查看状态变更
```typescript
// 安装 Redux DevTools 浏览器插件
// Zustand 会自动连接

// 在 Store 中启用 DevTools
import { devtools } from 'zustand/middleware';

export const useCartStore = create<CartStore>()(
  devtools(
    (set, get) => ({
      // ...
    }),
    { name: 'CartStore' }
  )
);
```

#### 时间旅行调试
1. 打开 Redux DevTools
2. 查看状态变更历史
3. 点击任意历史记录，应用程序会回到该状态

---

## 常见问题排查

### 1. API 请求失败

#### 检查后端服务
```bash
# 验证后端健康检查
curl http://localhost:8000/healthz
# 预期：{"status": "healthy"}

# 检查具体 API
curl http://localhost:8000/api/v1/menu
# 应返回菜单数据
```

#### 检查跨域配置
```typescript
// 后端需配置 CORS（已在 FastAPI 中设置）
// 前端确认环境变量正确
console.log('API Base URL:', import.meta.env.VITE_API_BASE_URL);
```

#### 检查 Token
```typescript
// 验证 Token 是否存在
const token = localStorage.getItem('auth_token');
console.log('Token:', token);

// 解码 JWT（仅用于调试）
const payload = JSON.parse(atob(token.split('.')[1]));
console.log('Token Payload:', payload);
console.log('Token Expiry:', new Date(payload.exp * 1000));
```

---

### 2. 小程序真机调试

#### 网络请求失败
1. **检查域名白名单**：
   - 登录微信公众平台
   - 进入"开发" → "开发管理" → "开发设置"
   - 在"服务器域名"中添加后端 API 域名

2. **检查 HTTPS**：
   - 小程序真机要求 HTTPS
   - 开发阶段可在"详情" → "本地设置"中勾选"不校验合法域名"

#### 支付失败
```typescript
// 检查 payer_open_id 是否正确
console.log('OpenID:', wx.getStorageSync('openid'));

// 检查支付参数
console.log('Payment Payload:', payload);

// 查看微信支付错误码
wx.requestPayment({
  ...payload,
  fail: (err) => {
    console.error('支付失败:', err.errMsg);
    // err.errMsg 可能的值：
    // 'requestPayment:fail cancel' - 用户取消
    // 'requestPayment:fail (detail message)' - 其他错误
  }
});
```

---

### 3. WebSocket 连接问题

#### 连接失败
```typescript
// 检查 WebSocket URL
console.log('WS URL:', import.meta.env.VITE_WS_URL);

// 验证 Token
const token = localStorage.getItem('auth_token');
console.log('Token for WS:', token);

// 检查浏览器控制台错误
// 常见错误：
// - WebSocket connection to 'ws://...' failed: Connection refused
//   → 后端服务未启动
// - WebSocket is closed before the connection is established
//   → URL 或 Token 错误
```

#### 连接频繁断开
```typescript
// 增加心跳频率
const HEARTBEAT_INTERVAL = 30000; // 30 秒
const HEARTBEAT_TIMEOUT = 35000; // 35 秒超时

// 启用重连逻辑
ws.onerror = () => {
  console.log('WebSocket error, reconnecting in 5s...');
  setTimeout(() => connectWebSocket(token), 5000);
};
```

---

## 生产部署检查清单

### 代码质量
- [ ] 所有组件都有 TypeScript 类型定义
- [ ] 无 ESLint 错误或警告（`pnpm lint`）
- [ ] 关键函数有单元测试覆盖（覆盖率 ≥ 70%）
- [ ] 关键流程有 E2E 测试
- [ ] 无 `console.log` 残留（生产环境自动移除）
- [ ] 无 TypeScript `any` 类型（除必要场景）

### 性能指标
- [ ] 小程序首屏加载 ≤ 2s（真机测试）
- [ ] Web 应用 Lighthouse 分数 ≥ 90
- [ ] 打包体积检查（主包 < 2MB，分包按需加载）
- [ ] 图片已压缩并启用 WebP 格式
- [ ] 长列表使用虚拟滚动

### 用户体验
- [ ] 所有网络请求有 loading 状态
- [ ] 失败请求有友好错误提示（含 trace_id）
- [ ] 离线状态有提示（购物车数据本地保存）
- [ ] 支付失败有重试入口
- [ ] 表单校验友好（实时提示，不阻塞提交）

### 安全检查
- [ ] Token 存储安全（小程序用加密存储）
- [ ] 敏感信息不打印到日志（手机号、订单号脱敏）
- [ ] HTTPS / WSS 强制使用
- [ ] API 请求签名验证（如需）
- [ ] 输入内容 XSS 过滤

### 环境配置
- [ ] 生产环境变量正确（API URL、AppID 等）
- [ ] CDN 配置正确（静态资源加速）
- [ ] 域名 DNS 解析正常
- [ ] SSL 证书有效（HTTPS）
- [ ] Nginx 配置正确（SPA 路由、WebSocket）

### 监控告警
- [ ] 错误日志上报（Sentry / 腾讯云 Rum）
- [ ] 性能监控（首屏加载时间、API 耗时）
- [ ] 用户行为埋点（页面访问、按钮点击）
- [ ] 关键指标告警（错误率 > 1%、加载时间 > 3s）

---

## 总结

本开发指南涵盖了前端项目的完整生命周期：

1. **开发环境搭建**：工具安装、项目初始化
2. **开发工作流**：分支管理、代码检查、提交规范
3. **API 对接**：自动生成客户端、幂等性处理、缓存策略
4. **状态管理**：Zustand 最佳实践、购物车实战
5. **性能优化**：打包优化、运行时优化、图片优化
6. **测试策略**：单元测试、组件测试、E2E 测试
7. **调试技巧**：浏览器调试、React DevTools、Zustand DevTools
8. **常见问题排查**：API 请求、小程序真机、WebSocket 连接
9. **生产部署**：代码质量、性能指标、安全检查

遵循本指南，可确保前端项目高质量、高性能、易维护。

---

**最后更新**：2025-10-27  
**版本**：V1.0  
**维护者**：frontend-team@naicha.com
