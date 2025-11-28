"""优惠券在订单创建中使用的测试"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.accounts import Coupon, User
from app.models.catalog import Category, Product
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def test_product(session: AsyncSession) -> Product:
    """创建测试商品"""
    category = Category(name="测试分类", sort_order=0)
    session.add(category)
    await session.flush()

    product = Product(
        category_id=category.category_id,
        name="测试奶茶",
        description="好喝的奶茶",
        base_price=Decimal("25.00"),
        status="active",
        inventory_status="in_stock",
        stock_quantity=100,
    )
    session.add(product)
    await session.commit()
    return product


@pytest.fixture
async def active_coupon(session: AsyncSession, test_user: User) -> Coupon:
    """创建一个 active 状态的优惠券"""
    coupon = Coupon(
        user_id=test_user.user_id,
        type="free_any_drink",
        status="active",
        issued_at=datetime.now(tz=UTC),
    )
    session.add(coupon)
    await session.commit()
    await session.refresh(coupon)
    return coupon


@pytest.mark.asyncio
async def test_create_order_with_valid_coupon(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试使用有效优惠券创建订单"""
    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "notes": "使用优惠券",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-coupon-order-1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "order_id" in data


@pytest.mark.asyncio
async def test_create_order_applies_coupon_discount(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试优惠券正确应用折扣"""
    # 创建订单, 单价25元, 数量2, 应扣除最便宜的一杯(25元)
    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "notes": "测试折扣",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 2,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-discount-1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    
    # 原价: 25 * 2 = 50
    # 优惠券免一杯: 50 - 25 = 25
    assert float(data["total_price"]) == 25.0


@pytest.mark.asyncio
async def test_create_order_marks_coupon_as_used(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试订单创建后优惠券被标记为已使用"""
    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-mark-used-1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    order_id = data["order_id"]

    # 检查优惠券状态
    await session.refresh(active_coupon)
    assert active_coupon.status == "used"
    assert active_coupon.used_at is not None
    assert active_coupon.used_in_order_id == order_id


@pytest.mark.asyncio
async def test_create_order_rejects_used_coupon(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试拒绝使用已使用的优惠券"""
    # 先标记优惠券为已使用
    active_coupon.status = "used"
    active_coupon.used_at = datetime.now(tz=UTC)
    active_coupon.used_in_order_id = 999
    await session.commit()

    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-used-coupon-1",
        },
    )

    assert response.status_code == 400
    assert "优惠券" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_order_rejects_other_user_coupon(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
):
    """测试拒绝使用其他用户的优惠券"""
    # 创建另一个用户及其优惠券
    other_user = User(
        open_id="other_openid_789",
        nickname="Other User",
        loyalty_points=0,
    )
    session.add(other_user)
    await session.flush()

    other_coupon = Coupon(
        user_id=other_user.user_id,
        type="free_any_drink",
        status="active",
        issued_at=datetime.now(tz=UTC),
    )
    session.add(other_coupon)
    await session.commit()

    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": other_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-other-coupon-1",
        },
    )

    assert response.status_code == 400
    assert "优惠券" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_order_rejects_expired_coupon(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试拒绝使用已过期的优惠券"""
    # 标记优惠券为过期
    active_coupon.status = "expired"
    await session.commit()

    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-expired-coupon-1",
        },
    )

    assert response.status_code == 400
    assert "优惠券" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_order_without_coupon_works(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
):
    """测试不使用优惠券也能正常创建订单"""
    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-no-coupon-1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    
    # 原价: 25 * 1 = 25
    assert float(data["total_price"]) == 25.0


@pytest.mark.asyncio
async def test_coupon_usage_is_atomic(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试优惠券使用的原子性 - 如果订单创建失败, 优惠券不应被使用"""
    # 使商品售罄以触发订单创建失败
    test_product.inventory_status = "sold_out"
    test_product.stock_quantity = 0
    await session.commit()

    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-atomic-1",
        },
    )

    # 订单创建应失败
    assert response.status_code == 400

    # 优惠券不应被标记为已使用
    await session.refresh(active_coupon)
    assert active_coupon.status == "active"
    assert active_coupon.used_at is None
    assert active_coupon.used_in_order_id is None


@pytest.mark.asyncio
async def test_coupon_discount_on_multiple_items(
    async_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    test_user_token: str,
    active_coupon: Coupon,
):
    """测试多个商品时优惠券免除最便宜的一杯"""
    # 创建不同价格的商品
    category = Category(name="测试分类", sort_order=0)
    session.add(category)
    await session.flush()

    product1 = Product(
        category_id=category.category_id,
        name="便宜奶茶",
        base_price=Decimal("15.00"),
        status="active",
        inventory_status="in_stock",
        stock_quantity=100,
    )
    product2 = Product(
        category_id=category.category_id,
        name="贵奶茶",
        base_price=Decimal("35.00"),
        status="active",
        inventory_status="in_stock",
        stock_quantity=100,
    )
    session.add_all([product1, product2])
    await session.commit()

    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "items": [
            {"product_id": product1.product_id, "quantity": 1, "spec_option_ids": []},
            {"product_id": product2.product_id, "quantity": 1, "spec_option_ids": []},
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Authorization": f"Bearer {test_user_token}",
            "Idempotency-Key": "test-multi-item-1",
        },
    )

    assert response.status_code == 201
    data = response.json()
    
    # 原价: 15 + 35 = 50
    # 优惠券免最便宜的: 50 - 15 = 35
    assert float(data["total_price"]) == 35.0


@pytest.mark.asyncio
async def test_guest_user_cannot_use_coupon(
    async_client: AsyncClient,
    session: AsyncSession,
    test_product: Product,
    active_coupon: Coupon,
):
    """测试游客用户不能使用优惠券"""
    order_payload = {
        "shop_id": 1,
        "delivery_type": "pickup",
        "user_phone": "13800000000",
        "guest_session_id": "guest_123456",
        "items": [
            {
                "product_id": test_product.product_id,
                "quantity": 1,
                "spec_option_ids": [],
            }
        ],
        "coupon_id": active_coupon.coupon_id,
    }

    response = await async_client.post(
        "/api/v1/orders",
        json=order_payload,
        headers={
            "Idempotency-Key": "test-guest-coupon-1",
        },
    )

    # 游客不能使用优惠券(因为没有 user)
    # 订单创建应该失败或忽略 coupon_id
    assert response.status_code in [400, 401]
