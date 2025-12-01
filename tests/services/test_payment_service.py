from __future__ import annotations

import asyncio
import hmac
from datetime import UTC, datetime
from decimal import Decimal

import app.services.payments
import pytest
from app.core.settings import get_settings
from app.models.accounts import User
from app.models.orders import Order, OrderItem, PaymentRecord, PrintJob
from app.models.shop import ShopSetting
from app.schemas import WechatPaymentNotifySchema
from app.services.payments import (
    PaymentConflictError,
    PaymentService,
)
from app.workers.print_jobs import recover_print_jobs
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture
def enqueue_spy(monkeypatch):
    calls: list[int] = []

    def fake(job_id: int) -> None:
        calls.append(job_id)

    monkeypatch.setattr("app.services.payments.enqueue_print_job", fake)
    return calls


@pytest.fixture
def payment_side_effects_spy(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake(order_id: int, source: str) -> None:
        calls.append({"order_id": order_id, "source": source})

    monkeypatch.setattr("app.services.payments.enqueue_payment_side_effects", fake)
    return calls


def _sign(body: bytes) -> str:
    settings = get_settings()
    return hmac.new(settings.secret_key.encode("utf-8"), body, "sha256").hexdigest()


@pytest.mark.asyncio
async def test_payment_service_amount_mismatch(
    db_session, enqueue_spy, payment_side_effects_spy
) -> None:
    order = Order(
        order_id=10,
        order_number="202510170010-NA0001",
        total_price=Decimal("20.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    await db_session.flush()

    service = PaymentService(db_session, get_settings())
    payload = WechatPaymentNotifySchema(
        event_id="evt_mismatch",
        order_number=order.order_number,
        transaction_id="txn_mismatch",
        amount=25.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )

    raw_body = payload.model_dump_json().encode("utf-8")

    with pytest.raises(PaymentConflictError):
        await service.handle_wechat_notification(
            payload, raw_body=raw_body, signature=_sign(raw_body)
        )

    payment = await db_session.execute(
        select(PaymentRecord).where(PaymentRecord.txn_id == "txn_mismatch")
    )
    assert payment.scalars().first() is None
    assert enqueue_spy == []
    assert payment_side_effects_spy == []


@pytest.mark.asyncio
async def test_payment_service_nested_transaction(
    db_session, enqueue_spy, payment_side_effects_spy
) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        order = Order(
            order_id=20,
            order_number="202510170020-NA0001",
            total_price=Decimal("28.00"),
            status="pending_payment",
            order_type="pickup",
        )
        setup_session.add(order)
        setup_session.add(
            OrderItem(
                item_id=2001,
                order_id=order.order_id,
                product_id=None,
                product_name="测试饮品",
                quantity=1,
                unit_price=Decimal("28.00"),
            )
        )
        await setup_session.flush()
        order_id = order.order_id
        order_number = order.order_number
        await setup_session.commit()

    payload = WechatPaymentNotifySchema(
        event_id="evt_nested",
        order_number=order_number,
        transaction_id="txn_nested",
        amount=28.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        async with session.begin():
            response = await service.handle_wechat_notification(
                payload,
                raw_body=raw_body,
                signature=_sign(raw_body),
            )

        assert response["status"] == "SUCCESS"

        refreshed = await session.get(Order, order_id)
        assert refreshed is not None
        assert refreshed.status == "paid"
        assert refreshed.pickup_code

        payment_record = await session.scalar(
            select(PaymentRecord).where(PaymentRecord.txn_id == "txn_nested")
        )
        assert payment_record is not None

    assert payment_side_effects_spy == [{"order_id": order_id, "source": "payment_callback"}]
    assert len(enqueue_spy) == 1


async def _prepare_order_for_loyalty(
    session, *, user_id: int, quantity: int, order_id: int
) -> Order:
    order = Order(
        order_id=order_id,
        order_number=f"LOYALTY-{order_id}",
        total_price=Decimal("12.00"),
        status="pending_payment",
        order_type="pickup",
        user_id=user_id,
    )
    session.add(order)
    session.add(
        OrderItem(
            item_id=order_id * 10,
            order_id=order.order_id,
            product_id=None,
            product_name="积分饮品",
            quantity=quantity,
            unit_price=Decimal("6.00"),
        )
    )
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_payment_service_awards_loyalty_points(
    db_session, enqueue_spy, payment_side_effects_spy
) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        user = User(user_id=300, open_id="openid-loyalty")
        setup_session.add(user)
        await setup_session.flush()
        await _prepare_order_for_loyalty(
            setup_session, user_id=user.user_id, quantity=2, order_id=30
        )
        await setup_session.commit()

    payload = WechatPaymentNotifySchema(
        event_id="evt_loyalty",
        order_number="LOYALTY-30",
        transaction_id="txn_loyalty",
        amount=12.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        response = await service.handle_wechat_notification(
            payload,
            raw_body=raw_body,
            signature=_sign(raw_body),
        )

        assert response["status"] == "SUCCESS"

        assert len(enqueue_spy) == 1
        assert payment_side_effects_spy == [{"order_id": 30, "source": "payment_callback"}]


@pytest.mark.asyncio
async def test_payment_service_loyalty_issues_coupon_and_is_idempotent(
    db_session, enqueue_spy, payment_side_effects_spy
) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        user = User(user_id=400, open_id="openid-coupon", loyalty_points=9)
        setup_session.add(user)
        await setup_session.flush()
        await _prepare_order_for_loyalty(
            setup_session, user_id=user.user_id, quantity=2, order_id=40
        )
        await setup_session.commit()

    payload = WechatPaymentNotifySchema(
        event_id="evt_coupon",
        order_number="LOYALTY-40",
        transaction_id="txn_coupon",
        amount=12.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        await service.handle_wechat_notification(
            payload, raw_body=raw_body, signature=_sign(raw_body)
        )
        await service.handle_wechat_notification(
            payload, raw_body=raw_body, signature=_sign(raw_body)
        )

        assert enqueue_spy  # 多次通知可触发多次入队,至少保证有入队行为
        assert payment_side_effects_spy == [{"order_id": 40, "source": "payment_callback"}]


@pytest.mark.asyncio
async def test_payment_notification_creates_single_print_job(
    model_test_engine, monkeypatch, enqueue_spy
) -> None:
    session_factory = async_sessionmaker(model_test_engine, expire_on_commit=False)

    if model_test_engine.dialect.name == "sqlite":
        pytest.skip("SQLite 无法可靠模拟并发打印队列。")

    async with session_factory() as setup_session:
        async with setup_session.begin():
            order = Order(
                order_id=970,
                order_number="PRINT-970",
                total_price=Decimal("22.00"),
                status="pending_payment",
                order_type="pickup",
            )
            setup_session.add(order)
            setup_session.add(
                OrderItem(
                    item_id=9701,
                    order_id=order.order_id,
                    product_id=None,
                    product_name="并发打印测试",
                    quantity=1,
                    unit_price=Decimal("22.00"),
                )
            )
            order_id = order.order_id
            order_number = order.order_number
    payload = WechatPaymentNotifySchema(
        event_id="evt_print_race",
        order_number=order_number,
        transaction_id="txn-print-race",
        amount=22.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async def process_once():
        async with session_factory() as session:
            service = PaymentService(session, get_settings())
            return await service.handle_wechat_notification(
                payload,
                raw_body=raw_body,
                signature=_sign(raw_body),
            )

    results = await asyncio.gather(process_once(), process_once())
    assert all(result["status"] == "SUCCESS" for result in results)

    async with session_factory() as verify_session:
        job_rows = list(
            (
                await verify_session.execute(select(PrintJob).where(PrintJob.order_id == order_id))
            ).scalars()
        )
        assert len(job_rows) == 1
        assert job_rows[0].status == "pending"

        records = list(
            (
                await verify_session.execute(
                    select(PaymentRecord).where(PaymentRecord.txn_id == "txn-print-race")
                )
            ).scalars()
        )
        assert len(records) == 1

    assert enqueue_spy
    assert len(set(enqueue_spy)) == 1


@pytest.mark.asyncio
async def test_payment_service_logs_replayed_notification(
    db_session,
    monkeypatch,
    enqueue_spy,
    caplog,
) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with session_factory() as setup_session:
        order = Order(
            order_id=450,
            order_number="202510170450-NA0001",
            total_price=Decimal("18.00"),
            status="pending_payment",
            order_type="pickup",
        )
        setup_session.add(order)
        setup_session.add(
            OrderItem(
                item_id=4501,
                order_id=order.order_id,
                product_id=None,
                product_name="重放检测饮品",
                quantity=1,
                unit_price=Decimal("18.00"),
            )
        )
        await setup_session.flush()
        order_number = order.order_number
        await setup_session.commit()

    info_calls: list[tuple[str, dict]] = []

    original_info = app.services.payments.logger.info  # type: ignore[attr-defined]

    def capture_info(event: str, **kwargs):
        info_calls.append((event, kwargs))
        return original_info(event, **kwargs)

    monkeypatch.setattr("app.services.payments.logger.info", capture_info)

    payload = WechatPaymentNotifySchema(
        event_id="evt_replayed",
        order_number=order_number,
        transaction_id="txn_replayed",
        amount=18.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, get_settings())
        await service.handle_wechat_notification(
            payload, raw_body=raw_body, signature=_sign(raw_body)
        )
        info_calls.clear()
        await service.handle_wechat_notification(
            payload, raw_body=raw_body, signature=_sign(raw_body)
        )

    assert any(
        event == "payment.notification_replayed"
        and call_kwargs.get("order_number") == order_number
        and call_kwargs.get("txn_id") == "txn_replayed"
        for event, call_kwargs in info_calls
    )


@pytest.mark.asyncio
async def test_payment_commit_but_enqueue_failed(db_session, monkeypatch) -> None:
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.workers.print_jobs.async_session_factory", session_factory)

    settings = get_settings()

    async with session_factory() as setup_session:
        order = Order(
            order_id=910,
            order_number="202510170910-NA0001",
            total_price=Decimal("18.00"),
            status="pending_payment",
            order_type="pickup",
        )
        setup_session.add(order)
        setup_session.add(
            OrderItem(
                item_id=9101,
                order_id=order.order_id,
                product_id=None,
                product_name="测试饮品",
                quantity=1,
                unit_price=Decimal("18.00"),
            )
        )
        await setup_session.flush()
        order_id = order.order_id
        order_number = order.order_number
        await setup_session.commit()

    def explode_enqueue(_job_id: int) -> None:
        raise RuntimeError("enqueue crashed")

    monkeypatch.setattr("app.services.payments.enqueue_print_job", explode_enqueue)

    payload = WechatPaymentNotifySchema(
        event_id="evt_crash",
        order_number=order_number,
        transaction_id="txn_crash",
        amount=18.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    async with session_factory() as session:
        service = PaymentService(session, settings)
        response = await service.handle_wechat_notification(
            payload,
            raw_body=raw_body,
            signature=_sign(raw_body),
        )
        assert response["status"] == "SUCCESS"

    async with session_factory() as verify_session:
        job = await verify_session.scalar(select(PrintJob).where(PrintJob.order_id == order_id))
        assert job is not None
        assert job.status == "pending"
        assert job.next_try_at is not None
        job_id = job.job_id

    recovered_ids = await recover_print_jobs(
        limit=10,
        now=datetime.now(tz=UTC),
        settings=settings,
    )
    assert job_id in recovered_ids


@pytest.mark.asyncio
async def test_payment_service_pickup_code_respects_settings(db_session) -> None:
    order = Order(
        order_id=920,
        order_number="PICKUP-CUSTOM-1",
        total_price=Decimal("28.00"),
        status="pending_payment",
        order_type="pickup",
    )
    db_session.add(order)
    db_session.add(
        OrderItem(
            item_id=9201,
            order_id=order.order_id,
            product_id=None,
            product_name="定制取餐码饮品",
            quantity=1,
            unit_price=Decimal("28.00"),
        )
    )
    db_session.add_all(
        [
            ShopSetting(key="pickup_code_prefix", value="NA-"),
            ShopSetting(key="pickup_code_digits", value="4"),
        ]
    )
    await db_session.flush()

    payload = WechatPaymentNotifySchema(
        event_id="evt_pickup_custom",
        order_number=order.order_number,
        transaction_id="txn_pickup_custom",
        amount=28.0,
        currency="CNY",
        channel="wechat_jsapi",
        status="SUCCESS",
        paid_at=datetime.now(tz=UTC),
    )
    raw_body = payload.model_dump_json().encode("utf-8")

    service = PaymentService(db_session, get_settings())
    await service.handle_wechat_notification(payload, raw_body=raw_body, signature=_sign(raw_body))

    refreshed = await db_session.get(Order, order.order_id)
    assert refreshed is not None
    assert refreshed.pickup_code
    assert refreshed.pickup_code.startswith("NA-")
    assert len(refreshed.pickup_code) == 3 + 4
