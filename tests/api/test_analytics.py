"""用户行为分析埋点API测试"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAnalyticsEventsAPI:
    """测试 POST /api/v1/analytics/events 接口"""

    async def test_batch_report_events_success_with_user(
        self, async_client: AsyncClient, test_user_token: str
    ):
        """测试已登录用户批量上报埋点事件（正常流程）"""
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "add_to_cart",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": {
                        "productId": 123,
                        "productName": "珍珠奶茶",
                        "quantity": 2,
                        "price": 15.0,
                    },
                },
                {
                    "id": str(uuid.uuid4()),
                    "type": "page",
                    "name": "page_view",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": {
                        "path": "/pages/menu/index",
                        "referrer": "/pages/index/index",
                        "duration": 3500,
                    },
                },
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"Authorization": f"Bearer {test_user_token}"},
        )

        assert response.status_code == 204
        assert response.content == b""

    async def test_batch_report_events_success_with_session_id(self, async_client: AsyncClient):
        """测试匿名用户携带X-Session-Id批量上报埋点事件"""
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "product_click",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": {"productId": 456},
                }
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "anon_session_12345"},
        )

        assert response.status_code == 204

    async def test_batch_report_events_missing_session_id(self, async_client: AsyncClient):
        """测试匿名用户缺少X-Session-Id返回400"""
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "test_event",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                }
            ]
        }

        response = await async_client.post("/api/v1/analytics/events", json=events_data)

        assert response.status_code == 400
        assert "X-Session-Id" in response.json()["detail"]

    async def test_batch_report_events_payload_too_large(self, async_client: AsyncClient):
        """测试payload超过8KB返回422"""
        large_payload = {"data": "x" * 10000}  # 超过8KB
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "test_event",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": large_payload,
                }
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422
        assert "payload" in response.text.lower()

    async def test_batch_report_events_too_many_fields(self, async_client: AsyncClient):
        """测试payload字段数超过30个返回422"""
        many_fields_payload = {f"field_{i}": i for i in range(35)}  # 超过30个字段
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "test_event",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": many_fields_payload,
                }
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422
        assert "30" in response.text

    async def test_batch_report_events_deep_nested(self, async_client: AsyncClient):
        """测试payload嵌套超过4层返回422"""
        deep_nested = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}  # 超过4层
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "test_event",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                    "payload": deep_nested,
                }
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422
        assert "4" in response.text or "层" in response.text

    async def test_batch_report_events_duplicate_ids(self, async_client: AsyncClient):
        """测试批次内存在重复事件ID返回422"""
        duplicate_id = str(uuid.uuid4())
        events_data = {
            "events": [
                {
                    "id": duplicate_id,
                    "type": "event",
                    "name": "event1",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                },
                {
                    "id": duplicate_id,  # 重复ID
                    "type": "event",
                    "name": "event2",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                },
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422
        assert "重复" in response.text or "duplicate" in response.text.lower()

    async def test_batch_report_events_max_batch_size(self, async_client: AsyncClient):
        """测试批次最多10条事件"""
        # 正常情况：恰好10条
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": f"event_{i}",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                }
                for i in range(10)
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 204

        # 超过限制：11条
        events_data_over = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": f"event_{i}",
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                }
                for i in range(11)
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data_over,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422

    async def test_batch_report_events_invalid_event_name(self, async_client: AsyncClient):
        """测试非法事件名返回422"""
        events_data = {
            "events": [
                {
                    "id": str(uuid.uuid4()),
                    "type": "event",
                    "name": "invalid name!@#",  # 包含特殊字符
                    "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                }
            ]
        }

        response = await async_client.post(
            "/api/v1/analytics/events",
            json=events_data,
            headers={"X-Session-Id": "test_session"},
        )

        assert response.status_code == 422

    async def test_analytics_health_check(self, async_client: AsyncClient):
        """测试埋点系统健康检查端点"""
        response = await async_client.get("/api/v1/analytics/health")

        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        if response.status_code == 200:
            assert data["status"] == "healthy"
            assert "queue_size" in data

    async def test_batch_report_events_respects_configured_queue(
        self, async_client: AsyncClient, monkeypatch
    ):
        """测试埋点任务投递使用配置的队列名而非硬编码"""
        from unittest.mock import MagicMock, patch

        from app.core.settings import get_settings

        # 模拟自定义队列名
        custom_queue_name = "custom_analytics_queue"
        settings = get_settings()
        monkeypatch.setattr(settings, "analytics_queue_name", custom_queue_name)

        # Mock Celery task 的 apply_async 方法
        with patch(
            "app.api.routes.analytics.batch_ingest_analytics_events.apply_async"
        ) as mock_apply_async:
            mock_apply_async.return_value = MagicMock()

            events_data = {
                "events": [
                    {
                        "id": str(uuid.uuid4()),
                        "type": "event",
                        "name": "test_queue_config",
                        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
                        "payload": {"test": "data"},
                    }
                ]
            }

            response = await async_client.post(
                "/api/v1/analytics/events",
                json=events_data,
                headers={"X-Session-Id": "test_session"},
            )

            assert response.status_code == 204

            # 验证 apply_async 被调用，且 queue 参数使用了配置的队列名
            mock_apply_async.assert_called_once()
            call_kwargs = mock_apply_async.call_args.kwargs
            assert call_kwargs["queue"] == custom_queue_name, (
                f"期望队列名为 {custom_queue_name}, " f"实际为 {call_kwargs.get('queue')}"
            )

    async def test_analytics_health_uses_configured_queue_name(
        self, async_client: AsyncClient, monkeypatch
    ):
        """测试健康检查使用配置的队列键进行Redis查询"""
        from unittest.mock import MagicMock, patch

        from app.core.settings import get_settings

        # 模拟自定义队列名
        custom_queue_name = "prod_analytics"
        settings = get_settings()
        monkeypatch.setattr(settings, "analytics_queue_name", custom_queue_name)

        # Mock Redis 客户端
        mock_redis_client = MagicMock()
        mock_redis_client.llen.return_value = 100  # 模拟队列长度

        with patch("redis.from_url", return_value=mock_redis_client):
            response = await async_client.get("/api/v1/analytics/health")

            # 验证 llen 被调用，且使用了配置的队列名
            mock_redis_client.llen.assert_called_once_with(custom_queue_name)
            mock_redis_client.close.assert_called_once()

            # 验证响应正常
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["queue_size"] == 100
