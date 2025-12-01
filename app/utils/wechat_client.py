"""微信小程序API客户端"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
import structlog

from app.core.settings import get_settings

logger = structlog.get_logger()


class WeChatAPIError(Exception):
    """微信API调用异常"""

    def __init__(self, errcode: int, errmsg: str) -> None:
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"微信API错误 [{errcode}]: {errmsg}")


class WeChatClient:
    """微信小程序API客户端,负责code2session和手机号获取"""

    BASE_URL = "https://api.weixin.qq.com"

    def __init__(self) -> None:
        settings = get_settings()
        self.appid = settings.wechat_appid
        self.secret = settings.wechat_secret
        self.timeout = settings.wechat_api_timeout

    async def jscode2session(self, code: str) -> dict[str, Any]:
        """
        通过code换取session信息
        返回: {"openid": str, "session_key": str, "unionid": str | None}
        """
        url = f"{self.BASE_URL}/sns/jscode2session"
        params = {
            "appid": self.appid,
            "secret": self.secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as exc:
                logger.warning("wechat.jscode2session.timeout", code_prefix=code[:8])
                raise WeChatAPIError(-1, "微信服务超时") from exc
            except httpx.HTTPError as exc:
                logger.warning("wechat.jscode2session.http_error", error=str(exc))
                raise WeChatAPIError(-2, "微信服务不可用") from exc

        if "errcode" in data and data["errcode"] != 0:
            errcode = data["errcode"]
            errmsg = data.get("errmsg", "未知错误")
            logger.warning(
                "wechat.jscode2session.error",
                errcode=errcode,
                errmsg=errmsg,
            )
            raise WeChatAPIError(errcode, errmsg)

        # 不记录敏感信息session_key
        logger.info(
            "wechat.jscode2session.success",
            openid=data.get("openid"),
            has_unionid=bool(data.get("unionid")),
        )

        return {
            "openid": data["openid"],
            "session_key": data["session_key"],
            "unionid": data.get("unionid"),
        }

    async def get_phone_number(self, code: str) -> dict[str, Any]:
        """
        通过code换取手机号
        返回: {"phone_number": str, "pure_phone_number": str, "country_code": str}
        """
        # 需要access_token,这里简化为直接调用API
        # 生产环境应缓存access_token
        access_token = await self._get_access_token()
        
        url = f"{self.BASE_URL}/wxa/business/getuserphonenumber"
        params = {"access_token": access_token}
        payload = {"code": code}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, params=params, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.TimeoutException as exc:
                logger.warning("wechat.get_phone_number.timeout")
                raise WeChatAPIError(-1, "微信服务超时") from exc
            except httpx.HTTPError as exc:
                logger.warning("wechat.get_phone_number.http_error", error=str(exc))
                raise WeChatAPIError(-2, "微信服务不可用") from exc

        if data.get("errcode", 0) != 0:
            errcode = data["errcode"]
            errmsg = data.get("errmsg", "未知错误")
            logger.warning(
                "wechat.get_phone_number.error",
                errcode=errcode,
                errmsg=errmsg,
            )
            raise WeChatAPIError(errcode, errmsg)

        phone_info = data.get("phone_info", {})
        # 日志脱敏
        logger.info(
            "wechat.get_phone_number.success",
            phone_masked=self._mask_phone(phone_info.get("purePhoneNumber", "")),
        )

        return {
            "phone_number": phone_info.get("phoneNumber", ""),
            "pure_phone_number": phone_info.get("purePhoneNumber", ""),
            "country_code": phone_info.get("countryCode", "86"),
        }

    async def _get_access_token(self) -> str:
        """获取access_token(应实现缓存,此处简化)"""
        url = f"{self.BASE_URL}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.secret,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        if "errcode" in data and data["errcode"] != 0:
            raise WeChatAPIError(data["errcode"], data.get("errmsg", "获取access_token失败"))

        return data["access_token"]

    @staticmethod
    def _mask_phone(phone: str) -> str:
        """手机号脱敏"""
        if len(phone) < 7:
            return "***"
        return f"{phone[:3]}****{phone[-4:]}"


def get_wechat_client() -> WeChatClient:
    """获取微信客户端单例"""
    return WeChatClient()
