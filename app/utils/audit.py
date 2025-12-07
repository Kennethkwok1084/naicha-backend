"""审计日志统一处理工具"""

from __future__ import annotations

import functools
from datetime import UTC, datetime
from typing import Any, Callable

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from structlog import get_logger

from app.models.accounts import Admin
from app.models.orders import AuditLog

logger = get_logger(__name__)


async def record_audit_log(
    session: AsyncSession,
    admin: Admin,
    action: str,
    target_table: str,
    target_id: str | None,
    before_json: dict | None,
    after_json: dict | None,
    request: Request,
    reason: str | None = None,
) -> None:
    """记录审计日志

    Args:
        session: 数据库会话
        admin: 当前管理员
        action: 操作动作（如 "order.refund", "member.points.adjust"）
        target_table: 目标表名
        target_id: 目标记录 ID
        before_json: 操作前状态
        after_json: 操作后状态
        request: FastAPI 请求对象
        reason: 操作原因（高风险操作必填）
    """
    audit_log = AuditLog(
        actor_type="admin",
        actor_admin_id=admin.admin_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        before_json=before_json,
        after_json=after_json,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    # 如果有 reason，添加到 after_json
    if reason and after_json is not None:
        after_json["_reason"] = reason
    elif reason and after_json is None:
        audit_log.after_json = {"_reason": reason}

    session.add(audit_log)
    logger.info(
        "audit.logged",
        admin_id=admin.admin_id,
        action=action,
        target=f"{target_table}:{target_id}",
        reason=reason,
    )


def require_reason(param_name: str = "reason") -> Callable:
    """装饰器：强制要求 reason 参数

    用于高风险操作（退款、资产调整、取消订单等），确保必须填写原因。

    Args:
        param_name: reason 参数在请求体中的字段名，默认为 "reason"

    Example:
        @router.post("/orders/{order_id}/refund")
        @require_reason()
        async def refund_order(order_id: int, payload: RefundSchema):
            # payload 必须包含 reason 字段，且不能为空
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 尝试从 kwargs 中查找包含 reason 的 payload 对象
            for arg_value in kwargs.values():
                if hasattr(arg_value, param_name):
                    reason_value = getattr(arg_value, param_name, None)
                    if not reason_value or (
                        isinstance(reason_value, str) and not reason_value.strip()
                    ):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Field '{param_name}' is required and cannot be empty for this operation.",
                        )
                    break
            else:
                # 如果没有找到任何包含 reason 的对象，记录警告
                logger.warning(
                    "audit.reason_check_skipped",
                    func=func.__name__,
                    note=f"No payload object with '{param_name}' field found",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def audit_action(
    action: str,
    target_table: str,
    risk_level: str = "normal",  # normal, high, critical
    require_reason_field: bool = False,
) -> Callable:
    """装饰器：自动记录审计日志

    Args:
        action: 操作动作标识
        target_table: 目标表名
        risk_level: 风险等级（normal/high/critical）
        require_reason_field: 是否强制要求 reason 字段

    Example:
        @router.put("/orders/{order_id}/status")
        @audit_action(action="order.status.update", target_table="orders", risk_level="high")
        async def update_order_status(
            order_id: int,
            payload: UpdateStatusSchema,
            admin: Admin = Depends(get_current_admin),
            session: AsyncSession = Depends(get_async_session),
            request: Request = ...,
        ):
            # 函数执行后自动记录审计日志
            # 需要在返回值或 kwargs 中提供 target_id, before_state, after_state
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 如果是高风险操作且要求 reason，则先检查
            if require_reason_field and risk_level in ("high", "critical"):
                for arg_value in kwargs.values():
                    if hasattr(arg_value, "reason"):
                        reason_value = getattr(arg_value, "reason", None)
                        if not reason_value or (
                            isinstance(reason_value, str) and not reason_value.strip()
                        ):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Field 'reason' is required for this high-risk operation.",
                            )
                        break

            # 执行原函数
            result = await func(*args, **kwargs)

            # 尝试从 kwargs 中提取必要的审计信息
            admin: Admin | None = kwargs.get("admin")
            session: AsyncSession | None = kwargs.get("session")
            request: Request | None = kwargs.get("request")

            if admin and session and request:
                # 尝试从结果或 kwargs 中提取审计相关信息
                target_id = (
                    kwargs.get("order_id") or kwargs.get("product_id") or kwargs.get("member_id")
                )
                if target_id:
                    target_id = str(target_id)

                # 记录日志（简化版，实际使用时可能需要更复杂的状态提取逻辑）
                await record_audit_log(
                    session=session,
                    admin=admin,
                    action=action,
                    target_table=target_table,
                    target_id=target_id,
                    before_json=None,  # 需要在具体业务中手动传入
                    after_json={"result": "operation_completed"},
                    request=request,
                    reason=None,  # 从 payload 中提取
                )

            return result

        return wrapper

    return decorator
