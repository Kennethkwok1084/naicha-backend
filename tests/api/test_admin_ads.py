from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import TokenScope, create_access_token
from app.db.session import get_async_session
from app.main import app
from app.models.accounts import Admin
from app.models.advertisement import AdSlot
from app.services.advertisement import AdvertisementService


def _admin_token(admin_id: int) -> str:
    return create_access_token(subject=str(admin_id), scope=TokenScope.ADMIN)


@pytest.fixture(autouse=True)
def _clear_ad_cache() -> None:
    AdvertisementService._invalidate_cache()
    yield
    AdvertisementService._invalidate_cache()


@pytest.mark.asyncio
async def test_admin_advertisement_flow(db_session) -> None:
    admin = Admin(admin_id=9001, username="ads-admin", password_hash="x", role="admin")
    db_session.add(admin)
    await db_session.flush()
    token = _admin_token(admin.admin_id)

    app.dependency_overrides[get_async_session] = lambda: db_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 初始广告位列表为空
            list_resp = await client.get(
                "/api/v1/admin/ads/slots",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert list_resp.status_code == 200
            assert list_resp.json() == []

            # 创建广告位
            create_slot_resp = await client.post(
                "/api/v1/admin/ads/slots",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "code": "HOME_BANNER",
                    "name": "首页轮播",
                    "spec": {"max_count": 5},
                },
            )
            assert create_slot_resp.status_code == 201, create_slot_resp.text
            slot_payload = create_slot_resp.json()
            assert slot_payload["code"] == "HOME_BANNER"

            # 创建两条素材
            creative_a = await client.post(
                "/api/v1/admin/ads/creatives",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": "秋季上新",
                    "image_url": "https://cdn.example.com/autumn.png",
                    "jump_type": "miniapp_page",
                    "jump_payload": {"path": "/pages/menu/index"},
                    "priority": 10,
                    "platforms": ["miniapp"],
                },
            )
            assert creative_a.status_code == 201
            creative_a_body = creative_a.json()

            creative_b = await client.post(
                "/api/v1/admin/ads/creatives",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": "冬季特饮",
                    "image_url": "https://cdn.example.com/winter.png",
                    "jump_type": "miniapp_page",
                    "priority": 5,
                    "platforms": ["miniapp"],
                },
            )
            assert creative_b.status_code == 201
            creative_b_body = creative_b.json()

            # 更新素材标题
            update_resp = await client.put(
                f"/api/v1/admin/ads/creatives/{creative_a_body['creative_id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": "秋季热饮"},
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["title"] == "秋季热饮"

            # 投放两条素材
            placement_a = await client.post(
                "/api/v1/admin/ads/placements",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "slot_code": "HOME_BANNER",
                    "creative_id": creative_a_body["creative_id"],
                },
            )
            assert placement_a.status_code == 201
            placement_a_body = placement_a.json()

            placement_b = await client.post(
                "/api/v1/admin/ads/placements",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "slot_code": "HOME_BANNER",
                    "creative_id": creative_b_body["creative_id"],
                },
            )
            assert placement_b.status_code == 201
            # placement_b_body = placement_b.json()  # unused

            # 查看投放
            placements_resp = await client.get(
                "/api/v1/admin/ads/placements",
                headers={"Authorization": f"Bearer {token}"},
                params={"slot_code": "HOME_BANNER"},
            )
            assert placements_resp.status_code == 200
            placements_payload = placements_resp.json()
            assert len(placements_payload) == 2

            # 调整排序
            reorder = await client.put(
                "/api/v1/admin/ads/placements/order",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "slot_code": "HOME_BANNER",
                    "creative_ids": [
                        creative_b_body["creative_id"],
                        creative_a_body["creative_id"],
                    ],
                },
            )
            assert reorder.status_code == 204

            reordered_list = await client.get(
                "/api/v1/admin/ads/placements",
                headers={"Authorization": f"Bearer {token}"},
                params={"slot_code": "HOME_BANNER"},
            )
            assert reordered_list.status_code == 200
            payload_after = reordered_list.json()
            assert payload_after[0]["creative"]["creative_id"] == creative_b_body["creative_id"]

            # 删除投放与素材
            delete_a = await client.delete(
                f"/api/v1/admin/ads/placements/{placement_a_body['placement_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert delete_a.status_code == 204

            delete_creative = await client.delete(
                f"/api/v1/admin/ads/creatives/{creative_a_body['creative_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert delete_creative.status_code == 204

            # 更新广告位信息
            update_slot = await client.put(
                "/api/v1/admin/ads/slots/HOME_BANNER",
                headers={"Authorization": f"Bearer {token}"},
                json={"description": "首页顶部轮播", "spec": {"max_count": 6}},
            )
            assert update_slot.status_code == 200
            slot_after = update_slot.json()
            assert slot_after["description"] == "首页顶部轮播"
            assert slot_after["spec"]["max_count"] == 6
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.mark.asyncio
async def test_advertisement_management_requires_manager_role(db_session) -> None:
    slot = AdSlot(slot_id=9101, code="HOME_CARD", name="首页卡片", spec={})
    db_session.add(slot)
    clerk = Admin(admin_id=9102, username="ads-clerk", password_hash="x", role="clerk")
    db_session.add(clerk)
    await db_session.flush()

    token = _admin_token(clerk.admin_id)
    app.dependency_overrides[get_async_session] = lambda: db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/ads/slots",
                headers={"Authorization": f"Bearer {token}"},
                json={"code": "NEW_SLOT", "name": "新品位", "spec": {}},
            )
    finally:
        app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 403
    detail = response.json()
    assert detail["error"]["message"] == "Insufficient role for advertisement management."
