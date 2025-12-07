"""商品管理后台路由"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.api.dependencies.auth import get_current_admin, require_permission
from app.core.permissions import Permission
from app.db.session import get_async_session
from app.models.accounts import Admin
from app.utils.audit import record_audit_log
from app.schemas.catalog_admin import (
    DeleteWithReasonSchema,
    CategoriesListResponseSchema,
    CategoryCreateSchema,
    CategoryResponseSchema,
    CategoryUpdateSchema,
    ProductBatchStatusUpdateSchema,
    ProductCreateSchema,
    ProductImportResponseSchema,
    ProductResponseSchema,
    ProductsListResponseSchema,
    ProductUpdateSchema,
    SpecGroupCreateSchema,
    SpecGroupResponseSchema,
    SpecGroupsListResponseSchema,
    SpecGroupUpdateSchema,
    SpecOptionCreateSchema,
    SpecOptionResponseSchema,
    SpecOptionsListResponseSchema,
    SpecOptionUpdateSchema,
)
from app.services import catalog as catalog_service

router = APIRouter()
logger = get_logger(__name__)


# ============ 分类管理 ============
@router.get("/categories", response_model=CategoriesListResponseSchema)
async def list_categories(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(require_permission(Permission.CATEGORIES_VIEW.value))],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> CategoriesListResponseSchema:
    """获取分类列表（需要 CATEGORIES_VIEW 权限）"""
    items, total = await catalog_service.get_categories(session, skip, limit)
    return CategoriesListResponseSchema(
        total=total,
        items=[CategoryResponseSchema.model_validate(c) for c in items],
    )


@router.get("/categories/{category_id}", response_model=CategoryResponseSchema)
async def get_category(
    category_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> CategoryResponseSchema:
    """获取分类详情"""
    category = await catalog_service.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")
    return CategoryResponseSchema.model_validate(category)


@router.post(
    "/categories", response_model=CategoryResponseSchema, status_code=status.HTTP_201_CREATED
)
async def create_category(
    data: CategoryCreateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> CategoryResponseSchema:
    """创建分类"""
    category = await catalog_service.create_category(session, data)

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="category_create",
        target_table="categories",
        target_id=str(category.category_id),
        after={"name": category.name, "sort_order": category.sort_order},
    )

    await session.commit()
    return CategoryResponseSchema.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponseSchema)
async def update_category(
    category_id: int,
    data: CategoryUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> CategoryResponseSchema:
    """更新分类"""
    old_category = await catalog_service.get_category_by_id(session, category_id)
    if not old_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    before = {"name": old_category.name, "sort_order": old_category.sort_order}

    category = await catalog_service.update_category(session, category_id, data)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="category_update",
        target_table="categories",
        target_id=str(category_id),
        before=before,
        after={"name": category.name, "sort_order": category.sort_order},
    )

    await session.commit()
    return CategoryResponseSchema.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> None:
    """删除分类"""
    old_category = await catalog_service.get_category_by_id(session, category_id)
    if not old_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    before = {"name": old_category.name, "sort_order": old_category.sort_order}

    success = await catalog_service.delete_category(session, category_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="category_delete",
        target_table="categories",
        target_id=str(category_id),
        before=before,
    )

    await session.commit()


# ============ 商品管理 ============
@router.get("/products", response_model=ProductsListResponseSchema)
async def list_products(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    category_id: int | None = Query(None),
    status: str | None = Query(None),
    inventory_status: str | None = Query(None),
    search: str | None = Query(None),
) -> ProductsListResponseSchema:
    """获取商品列表"""
    items, total = await catalog_service.get_products(
        session,
        skip,
        limit,
        category_id,
        status,
        inventory_status,
        search,
    )
    return ProductsListResponseSchema(
        total=total,
        items=[ProductResponseSchema.model_validate(p) for p in items],
    )


@router.get("/products/{product_id}", response_model=ProductResponseSchema)
async def get_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> ProductResponseSchema:
    """获取商品详情"""
    product = await catalog_service.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")
    return ProductResponseSchema.model_validate(product)


@router.post("/products", response_model=ProductResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> ProductResponseSchema:
    """创建商品"""
    product = await catalog_service.create_product(session, data)

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="product_create",
        target_table="products",
        target_id=str(product.product_id),
        after={
            "name": product.name,
            "base_price": float(product.base_price),
            "status": product.status,
            "inventory_status": product.inventory_status,
        },
    )

    await session.commit()
    return ProductResponseSchema.model_validate(product)


@router.patch("/products/{product_id}", response_model=ProductResponseSchema)
async def update_product(
    product_id: int,
    data: ProductUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> ProductResponseSchema:
    """更新商品"""
    old_product = await catalog_service.get_product_by_id(session, product_id)
    if not old_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")

    before = {
        "name": old_product.name,
        "base_price": float(old_product.base_price),
        "status": old_product.status,
        "inventory_status": old_product.inventory_status,
    }

    product = await catalog_service.update_product(session, product_id, data)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="product_update",
        target_table="products",
        target_id=str(product_id),
        before=before,
        after={
            "name": product.name,
            "base_price": float(product.base_price),
            "status": product.status,
            "inventory_status": product.inventory_status,
        },
    )

    await session.commit()
    return ProductResponseSchema.model_validate(product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> None:
    """删除商品"""
    old_product = await catalog_service.get_product_by_id(session, product_id)
    if not old_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")

    before = {"name": old_product.name, "status": old_product.status}

    success = await catalog_service.delete_product(session, product_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="商品不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="product_delete",
        target_table="products",
        target_id=str(product_id),
        before=before,
    )

    await session.commit()


@router.post("/products/batch-status", status_code=status.HTTP_200_OK)
async def batch_update_product_status(
    data: ProductBatchStatusUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> dict:
    """批量更新商品状态"""
    updated_count = await catalog_service.batch_update_product_status(
        session,
        data.product_ids,
        data.status,
        data.inventory_status,
    )

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="product_batch_status_update",
        target_table="products",
        target_id=",".join(str(pid) for pid in data.product_ids),
        after={
            "status": data.status,
            "inventory_status": data.inventory_status,
            "count": updated_count,
        },
    )

    await session.commit()
    return {"updated_count": updated_count}


# ============ 批量导入 ============
@router.post("/products/import", response_model=ProductImportResponseSchema)
async def import_products(
    file: Annotated[UploadFile, File(description="Excel 或 CSV 文件")],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> ProductImportResponseSchema:
    """批量导入商品"""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名缺失")

    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 Excel (.xlsx, .xls) 或 CSV 文件",
        )

    try:
        rows = await catalog_service.parse_product_import_file(file)
        result = await catalog_service.batch_import_products(session, rows)

        # 审计日志
        create_audit_log(
            session,
            admin_user,
            action="product_batch_import",
            target_table="products",
            target_id="batch",
            after={
                "filename": file.filename,
                "success_count": result.success_count,
                "error_count": result.error_count,
            },
        )

        await session.commit()
        return ProductImportResponseSchema(result=result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============ 规格组管理 ============
@router.get("/spec-groups", response_model=SpecGroupsListResponseSchema)
async def list_spec_groups(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> SpecGroupsListResponseSchema:
    """获取规格组列表"""
    items, total = await catalog_service.get_spec_groups(session, skip, limit)
    return SpecGroupsListResponseSchema(
        total=total,
        items=[SpecGroupResponseSchema.model_validate(g) for g in items],
    )


@router.get("/spec-groups/{group_id}", response_model=SpecGroupResponseSchema)
async def get_spec_group(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecGroupResponseSchema:
    """获取规格组详情"""
    group = await catalog_service.get_spec_group_by_id(session, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格组不存在")
    return SpecGroupResponseSchema.model_validate(group)


@router.post(
    "/spec-groups", response_model=SpecGroupResponseSchema, status_code=status.HTTP_201_CREATED
)
async def create_spec_group(
    data: SpecGroupCreateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecGroupResponseSchema:
    """创建规格组"""
    group = await catalog_service.create_spec_group(session, data)

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_group_create",
        target_table="spec_groups",
        target_id=str(group.group_id),
        after={"name": group.name, "sort_order": group.sort_order},
    )

    await session.commit()
    return SpecGroupResponseSchema.model_validate(group)


@router.patch("/spec-groups/{group_id}", response_model=SpecGroupResponseSchema)
async def update_spec_group(
    group_id: int,
    data: SpecGroupUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecGroupResponseSchema:
    """更新规格组"""
    old_group = await catalog_service.get_spec_group_by_id(session, group_id)
    if not old_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格组不存在")

    before = {"name": old_group.name, "sort_order": old_group.sort_order}

    group = await catalog_service.update_spec_group(session, group_id, data)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格组不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_group_update",
        target_table="spec_groups",
        target_id=str(group_id),
        before=before,
        after={"name": group.name, "sort_order": group.sort_order},
    )

    await session.commit()
    return SpecGroupResponseSchema.model_validate(group)


@router.delete("/spec-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec_group(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> None:
    """删除规格组"""
    old_group = await catalog_service.get_spec_group_by_id(session, group_id)
    if not old_group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格组不存在")

    before = {"name": old_group.name, "sort_order": old_group.sort_order}

    success = await catalog_service.delete_spec_group(session, group_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格组不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_group_delete",
        target_table="spec_groups",
        target_id=str(group_id),
        before=before,
    )

    await session.commit()


# ============ 规格选项管理 ============
@router.get("/spec-options", response_model=SpecOptionsListResponseSchema)
async def list_spec_options(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
    group_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> SpecOptionsListResponseSchema:
    """获取规格选项列表"""
    items, total = await catalog_service.get_spec_options(session, group_id, skip, limit)
    return SpecOptionsListResponseSchema(
        total=total,
        items=[SpecOptionResponseSchema.model_validate(o) for o in items],
    )


@router.get("/spec-options/{option_id}", response_model=SpecOptionResponseSchema)
async def get_spec_option(
    option_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecOptionResponseSchema:
    """获取规格选项详情"""
    option = await catalog_service.get_spec_option_by_id(session, option_id)
    if not option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格选项不存在")
    return SpecOptionResponseSchema.model_validate(option)


@router.post(
    "/spec-options", response_model=SpecOptionResponseSchema, status_code=status.HTTP_201_CREATED
)
async def create_spec_option(
    data: SpecOptionCreateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecOptionResponseSchema:
    """创建规格选项"""
    option = await catalog_service.create_spec_option(session, data)

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_option_create",
        target_table="spec_options",
        target_id=str(option.option_id),
        after={
            "name": option.name,
            "group_id": option.group_id,
            "price_modifier": float(option.price_modifier),
        },
    )

    await session.commit()
    return SpecOptionResponseSchema.model_validate(option)


@router.patch("/spec-options/{option_id}", response_model=SpecOptionResponseSchema)
async def update_spec_option(
    option_id: int,
    data: SpecOptionUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> SpecOptionResponseSchema:
    """更新规格选项"""
    old_option = await catalog_service.get_spec_option_by_id(session, option_id)
    if not old_option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格选项不存在")

    before = {
        "name": old_option.name,
        "price_modifier": float(old_option.price_modifier),
        "inventory_status": old_option.inventory_status,
    }

    option = await catalog_service.update_spec_option(session, option_id, data)
    if not option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格选项不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_option_update",
        target_table="spec_options",
        target_id=str(option_id),
        before=before,
        after={
            "name": option.name,
            "price_modifier": float(option.price_modifier),
            "inventory_status": option.inventory_status,
        },
    )

    await session.commit()
    return SpecOptionResponseSchema.model_validate(option)


@router.delete("/spec-options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spec_option(
    option_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin_user: Annotated[Admin, Depends(get_current_admin)],
) -> None:
    """删除规格选项"""
    old_option = await catalog_service.get_spec_option_by_id(session, option_id)
    if not old_option:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格选项不存在")

    before = {"name": old_option.name, "group_id": old_option.group_id}

    success = await catalog_service.delete_spec_option(session, option_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规格选项不存在")

    # 审计日志
    create_audit_log(
        session,
        admin_user,
        action="spec_option_delete",
        target_table="spec_options",
        target_id=str(option_id),
        before=before,
    )

    await session.commit()
