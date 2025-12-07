"""商品管理后台 API 测试"""

from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Category, Product, SpecGroup, SpecOption
from app.models.orders import AuditLog


@pytest.mark.asyncio
class TestCategoryManagement:
    """分类管理测试"""

    async def test_create_category_success(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试创建分类成功"""
        data = {"name": "测试分类", "sort_order": 10}
        response = await async_client.post(
            "/admin/products/categories", json=data, headers=admin_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert result["name"] == "测试分类"
        assert result["sort_order"] == 10
        assert "category_id" in result

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='category_create' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_list_categories(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试获取分类列表"""
        # 创建测试数据
        await async_client.post(
            "/admin/products/categories",
            json={"name": "分类1", "sort_order": 1},
            headers=admin_headers,
        )
        await async_client.post(
            "/admin/products/categories",
            json={"name": "分类2", "sort_order": 2},
            headers=admin_headers,
        )

        response = await async_client.get("/admin/products/categories", headers=admin_headers)
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["total"] >= 2
        assert len(result["items"]) >= 2

    async def test_update_category(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试更新分类"""
        # 创建分类
        create_resp = await async_client.post(
            "/admin/products/categories",
            json={"name": "旧分类", "sort_order": 1},
            headers=admin_headers,
        )
        category_id = create_resp.json()["category_id"]

        # 更新分类
        update_data = {"name": "新分类", "sort_order": 99}
        response = await async_client.patch(
            f"/admin/products/categories/{category_id}",
            json=update_data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["name"] == "新分类"
        assert result["sort_order"] == 99

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='category_update' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_delete_category(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试删除分类"""
        # 创建分类
        create_resp = await async_client.post(
            "/admin/products/categories",
            json={"name": "待删除分类"},
            headers=admin_headers,
        )
        category_id = create_resp.json()["category_id"]

        # 删除分类
        response = await async_client.delete(
            f"/admin/products/categories/{category_id}",
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # 验证已删除
        get_resp = await async_client.get(
            f"/admin/products/categories/{category_id}",
            headers=admin_headers,
        )
        assert get_resp.status_code == status.HTTP_404_NOT_FOUND

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='category_delete' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_create_category_without_permission(
        self,
        async_client: AsyncClient,
    ):
        """测试无权限创建分类"""
        data = {"name": "无权限分类"}
        response = await async_client.post("/admin/products/categories", json=data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
class TestProductManagement:
    """商品管理测试"""

    async def test_create_product_success(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试创建商品成功"""
        # 先创建分类
        cat_resp = await async_client.post(
            "/admin/products/categories",
            json={"name": "测试分类"},
            headers=admin_headers,
        )
        category_id = cat_resp.json()["category_id"]

        # 创建商品
        data = {
            "name": "测试商品",
            "description": "这是一个测试商品",
            "base_price": 29.90,
            "category_id": category_id,
            "status": "active",
            "inventory_status": "in_stock",
            "stock_quantity": 100,
        }
        response = await async_client.post(
            "/admin/products/products", json=data, headers=admin_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert result["name"] == "测试商品"
        assert result["base_price"] == 29.90
        assert "product_id" in result

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='product_create' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_list_products_with_filters(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试带过滤条件的商品列表"""
        # 创建测试商品
        await async_client.post(
            "/admin/products/products",
            json={"name": "珍珠奶茶", "base_price": 18.0, "status": "active"},
            headers=admin_headers,
        )
        await async_client.post(
            "/admin/products/products",
            json={"name": "红茶拿铁", "base_price": 22.0, "status": "inactive"},
            headers=admin_headers,
        )

        # 过滤 active 商品
        response = await async_client.get(
            "/admin/products/products?status=active",
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert all(item["status"] == "active" for item in result["items"])

        # 搜索商品
        response = await async_client.get(
            "/admin/products/products?search=珍珠",
            headers=admin_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert any("珍珠" in item["name"] for item in result["items"])

    async def test_update_product(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试更新商品"""
        # 创建商品
        create_resp = await async_client.post(
            "/admin/products/products",
            json={"name": "旧商品", "base_price": 10.0},
            headers=admin_headers,
        )
        product_id = create_resp.json()["product_id"]

        # 更新商品
        update_data = {"name": "新商品", "base_price": 25.0, "status": "inactive"}
        response = await async_client.patch(
            f"/admin/products/products/{product_id}",
            json=update_data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["name"] == "新商品"
        assert result["base_price"] == 25.0
        assert result["status"] == "inactive"

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='product_update' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_batch_update_product_status(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试批量更新商品状态"""
        # 创建多个商品
        product_ids = []
        for i in range(3):
            resp = await async_client.post(
                "/admin/products/products",
                json={"name": f"商品{i}", "base_price": 10.0, "status": "active"},
                headers=admin_headers,
            )
            product_ids.append(resp.json()["product_id"])

        # 批量下架
        data = {"product_ids": product_ids, "status": "inactive"}
        response = await async_client.post(
            "/admin/products/products/batch-status",
            json=data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["updated_count"] == 3

        # 验证状态已更新
        for product_id in product_ids:
            resp = await async_client.get(
                f"/admin/products/products/{product_id}",
                headers=admin_headers,
            )
            assert resp.json()["status"] == "inactive"

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='product_batch_status_update' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_delete_product(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试删除商品"""
        # 创建商品
        create_resp = await async_client.post(
            "/admin/products/products",
            json={"name": "待删除商品", "base_price": 10.0},
            headers=admin_headers,
        )
        product_id = create_resp.json()["product_id"]

        # 删除商品
        response = await async_client.delete(
            f"/admin/products/products/{product_id}",
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # 验证已删除
        get_resp = await async_client.get(
            f"/admin/products/products/{product_id}",
            headers=admin_headers,
        )
        assert get_resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
class TestProductImport:
    """商品批量导入测试"""

    async def test_import_products_from_excel(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试从 Excel 文件批量导入商品"""
        # 创建 Excel 文件
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["分类名", "商品名", "描述", "价格", "状态", "库存状态", "库存数量", "规格组"])
        ws.append(["奶茶", "珍珠奶茶", "经典珍珠奶茶", 18.0, "active", "in_stock", 100, ""])
        ws.append(["奶茶", "红茶拿铁", "香浓红茶拿铁", 22.0, "active", "in_stock", 50, ""])
        ws.append(["", "无分类商品", "", 15.0, "active", "in_stock", 0, ""])

        # 保存到内存
        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        # 上传导入
        files = {
            "file": (
                "products.xlsx",
                excel_buffer,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        response = await async_client.post(
            "/admin/products/products/import",
            files=files,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["result"]["success_count"] == 3
        assert result["result"]["error_count"] == 0

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='product_batch_import' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_import_products_with_errors(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试导入包含错误的商品数据"""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["分类名", "商品名", "描述", "价格", "状态", "库存状态", "库存数量", "规格组"])
        ws.append(["奶茶", "正常商品", "描述", 18.0, "active", "in_stock", 100, ""])
        ws.append(["", "", "", 0, "active", "in_stock", 0, ""])  # 缺少商品名和价格无效

        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        files = {
            "file": (
                "products_errors.xlsx",
                excel_buffer,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        response = await async_client.post(
            "/admin/products/products/import",
            files=files,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["result"]["success_count"] == 1
        assert result["result"]["error_count"] == 1
        assert len(result["result"]["errors"]) == 1

    async def test_import_invalid_file_type(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试上传不支持的文件类型"""
        files = {"file": ("test.txt", b"invalid content", "text/plain")}
        response = await async_client.post(
            "/admin/products/products/import",
            files=files,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
class TestSpecManagement:
    """规格管理测试"""

    async def test_create_spec_group(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试创建规格组"""
        data = {"name": "温度", "sort_order": 1}
        response = await async_client.post(
            "/admin/products/spec-groups", json=data, headers=admin_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert result["name"] == "温度"
        assert "group_id" in result

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='spec_group_create' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_create_spec_option(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
        db_session: AsyncSession,
    ):
        """测试创建规格选项"""
        # 先创建规格组
        group_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "温度"},
            headers=admin_headers,
        )
        group_id = group_resp.json()["group_id"]

        # 创建规格选项
        data = {
            "group_id": group_id,
            "name": "热饮",
            "price_modifier": 0.0,
            "inventory_status": "in_stock",
        }
        response = await async_client.post(
            "/admin/products/spec-options", json=data, headers=admin_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert result["name"] == "热饮"
        assert result["group_id"] == group_id

        # 验证审计日志
        audit_log = (
            await db_session.execute(
                "SELECT * FROM audit_logs WHERE action='spec_option_create' ORDER BY created_at DESC LIMIT 1"
            )
        ).first()
        assert audit_log is not None

    async def test_update_spec_option(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试更新规格选项"""
        # 创建规格组和选项
        group_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "糖度"},
            headers=admin_headers,
        )
        group_id = group_resp.json()["group_id"]

        option_resp = await async_client.post(
            "/admin/products/spec-options",
            json={"group_id": group_id, "name": "正常糖", "price_modifier": 0.0},
            headers=admin_headers,
        )
        option_id = option_resp.json()["option_id"]

        # 更新规格选项
        update_data = {"name": "半糖", "price_modifier": -1.0}
        response = await async_client.patch(
            f"/admin/products/spec-options/{option_id}",
            json=update_data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["name"] == "半糖"
        assert result["price_modifier"] == -1.0

    async def test_list_spec_options_by_group(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试按规格组过滤选项列表"""
        # 创建规格组和多个选项
        group_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "尺寸"},
            headers=admin_headers,
        )
        group_id = group_resp.json()["group_id"]

        for name, modifier in [("中杯", 0.0), ("大杯", 3.0), ("超大杯", 5.0)]:
            await async_client.post(
                "/admin/products/spec-options",
                json={"group_id": group_id, "name": name, "price_modifier": modifier},
                headers=admin_headers,
            )

        # 查询该规格组的选项
        response = await async_client.get(
            f"/admin/products/spec-options?group_id={group_id}",
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["total"] == 3
        assert all(item["group_id"] == group_id for item in result["items"])


@pytest.mark.asyncio
class TestProductSpecMapping:
    """商品规格关联测试"""

    async def test_create_product_with_spec_groups(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试创建商品时关联规格组"""
        # 创建规格组
        group1_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "温度"},
            headers=admin_headers,
        )
        group1_id = group1_resp.json()["group_id"]

        group2_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "糖度"},
            headers=admin_headers,
        )
        group2_id = group2_resp.json()["group_id"]

        # 创建商品并关联规格组
        product_data = {
            "name": "测试商品",
            "base_price": 20.0,
            "spec_group_ids": [group1_id, group2_id],
        }
        response = await async_client.post(
            "/admin/products/products",
            json=product_data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        result = response.json()
        assert set(result["spec_group_ids"]) == {group1_id, group2_id}

    async def test_update_product_spec_groups(
        self,
        async_client: AsyncClient,
        admin_headers: dict[str, str],
    ):
        """测试更新商品的规格组关联"""
        # 创建商品
        product_resp = await async_client.post(
            "/admin/products/products",
            json={"name": "测试商品", "base_price": 20.0},
            headers=admin_headers,
        )
        product_id = product_resp.json()["product_id"]

        # 创建规格组
        group_resp = await async_client.post(
            "/admin/products/spec-groups",
            json={"name": "尺寸"},
            headers=admin_headers,
        )
        group_id = group_resp.json()["group_id"]

        # 更新商品规格关联
        update_data = {"spec_group_ids": [group_id]}
        response = await async_client.patch(
            f"/admin/products/products/{product_id}",
            json=update_data,
            headers=admin_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["spec_group_ids"] == [group_id]
