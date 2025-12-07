"""Admin RBAC 权限点定义与角色映射"""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    """权限点枚举"""

    # Dashboard
    DASHBOARD_VIEW = "dashboard.view"

    # 订单管理
    ORDERS_VIEW = "orders.view"
    ORDERS_EDIT = "orders.edit"
    ORDERS_REFUND = "orders.refund"
    ORDERS_CANCEL = "orders.cancel"
    ORDERS_POS_CREATE = "orders.pos.create"

    # 商品管理
    PRODUCTS_VIEW = "products.view"
    PRODUCTS_EDIT = "products.edit"
    PRODUCTS_DELETE = "products.delete"
    PRODUCTS_IMPORT = "products.import"

    # 分类管理
    CATEGORIES_VIEW = "categories.view"
    CATEGORIES_EDIT = "categories.edit"
    CATEGORIES_DELETE = "categories.delete"

    # 规格管理
    SPECS_VIEW = "specs.view"
    SPECS_EDIT = "specs.edit"
    SPECS_DELETE = "specs.delete"

    # 库存管理
    INVENTORY_VIEW = "inventory.view"
    INVENTORY_EDIT = "inventory.edit"

    # 会员管理
    MEMBERS_VIEW = "members.view"
    MEMBERS_EDIT = "members.edit"
    MEMBERS_ASSET_ADJUST = "members.asset.adjust"

    # 营销管理
    MARKETING_COUPONS_VIEW = "marketing.coupons.view"
    MARKETING_COUPONS_EDIT = "marketing.coupons.edit"
    MARKETING_COUPONS_ISSUE = "marketing.coupons.issue"

    # 广告管理
    ADS_VIEW = "ads.view"
    ADS_EDIT = "ads.edit"

    # 门店管理
    SHOP_SETTINGS_VIEW = "shop.settings.view"
    SHOP_SETTINGS_EDIT = "shop.settings.edit"

    # 设备管理
    DEVICES_MERCHANT_VIEW = "devices.merchant.view"
    DEVICES_MERCHANT_MANAGE = "devices.merchant.manage"
    DEVICES_POS_VIEW = "devices.pos.view"
    DEVICES_POS_MANAGE = "devices.pos.manage"

    # Webhook 管理
    WEBHOOKS_VIEW = "webhooks.view"
    WEBHOOKS_MANAGE = "webhooks.manage"

    # 系统管理
    SYSTEM_ADMINS_VIEW = "system.admins.view"
    SYSTEM_ADMINS_MANAGE = "system.admins.manage"
    SYSTEM_AUDIT_VIEW = "system.audit.view"
    SYSTEM_AUDIT_EXPORT = "system.audit.export"
    SYSTEM_CONFIG_EDIT = "system.config.edit"

    # 统计数据
    STATS_WANT_VIEW = "stats.want.view"

    # 支付匹配
    PAYMENTS_MATCH = "payments.match"


# 角色权限映射
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {p.value for p in Permission},  # SuperAdmin 拥有所有权限
    "manager": {
        # Dashboard
        Permission.DASHBOARD_VIEW.value,
        # 订单
        Permission.ORDERS_VIEW.value,
        Permission.ORDERS_EDIT.value,
        Permission.ORDERS_REFUND.value,
        Permission.ORDERS_CANCEL.value,
        Permission.ORDERS_POS_CREATE.value,
        # 商品
        Permission.PRODUCTS_VIEW.value,
        Permission.PRODUCTS_EDIT.value,
        Permission.PRODUCTS_IMPORT.value,
        Permission.CATEGORIES_VIEW.value,
        Permission.CATEGORIES_EDIT.value,
        Permission.SPECS_VIEW.value,
        Permission.SPECS_EDIT.value,
        # 库存
        Permission.INVENTORY_VIEW.value,
        Permission.INVENTORY_EDIT.value,
        # 会员
        Permission.MEMBERS_VIEW.value,
        Permission.MEMBERS_EDIT.value,
        Permission.MEMBERS_ASSET_ADJUST.value,
        # 营销
        Permission.MARKETING_COUPONS_VIEW.value,
        Permission.MARKETING_COUPONS_EDIT.value,
        Permission.MARKETING_COUPONS_ISSUE.value,
        # 广告
        Permission.ADS_VIEW.value,
        Permission.ADS_EDIT.value,
        # 门店
        Permission.SHOP_SETTINGS_VIEW.value,
        Permission.SHOP_SETTINGS_EDIT.value,
        # 设备
        Permission.DEVICES_MERCHANT_VIEW.value,
        Permission.DEVICES_MERCHANT_MANAGE.value,
        Permission.DEVICES_POS_VIEW.value,
        Permission.DEVICES_POS_MANAGE.value,
        # 统计
        Permission.STATS_WANT_VIEW.value,
        # 支付匹配
        Permission.PAYMENTS_MATCH.value,
    },
    "clerk": {
        # Dashboard
        Permission.DASHBOARD_VIEW.value,
        # 订单（只读 + POS 建单）
        Permission.ORDERS_VIEW.value,
        Permission.ORDERS_POS_CREATE.value,
        # 商品（只读）
        Permission.PRODUCTS_VIEW.value,
        Permission.CATEGORIES_VIEW.value,
        Permission.SPECS_VIEW.value,
        # 库存（只读）
        Permission.INVENTORY_VIEW.value,
        # 支付匹配（受限于现金/POS 刷卡）
        Permission.PAYMENTS_MATCH.value,
    },
}


def get_permissions_for_role(role: str) -> set[str]:
    """获取角色对应的权限点集合"""
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: str, permission: str) -> bool:
    """检查角色是否拥有指定权限"""
    return permission in get_permissions_for_role(role)
