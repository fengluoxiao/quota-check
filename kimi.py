"""Kimi Code subscription usage, following MoonshotAI/kimi-cli's /usage implementation.
Only GET /usages is sent; this never calls a model or the Moonshot prepaid balance API.
"""
from __future__ import annotations
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime
import quota

ENDPOINT = "https://api.kimi.com/coding/v1/usages"
MAX_BYTES = 2_000_000

def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:n = quota.number(value)
    except OverflowError:return None
    return n if n is not None and n >= 0 else None

def _label(item, detail, index):
    for field in ("name", "title", "scope"):
        value = item.get(field) or detail.get(field)
        if isinstance(value, str) and value.strip():
            return value[:160]
    window = item.get("window")
    window = window if isinstance(window, dict) else {}
    duration = _amount(window.get("duration", item.get("duration", detail.get("duration"))))
    unit = window.get("timeUnit", item.get("timeUnit", detail.get("timeUnit", "")))
    if duration is not None and duration > 0 and isinstance(unit, str):
        units = {"TIME_UNIT_MINUTE": "分钟", "TIME_UNIT_HOUR": "小时", "TIME_UNIT_DAY": "天", "TIME_UNIT_WEEK": "周", "TIME_UNIT_MONTH": "月", "TIME_UNIT_SECOND": "秒"}
        if unit == "TIME_UNIT_MINUTE" and duration % 60 == 0:
            return quota.pretty_number(duration / 60) + " 小时额度"
        if unit in units:
            return quota.pretty_number(duration) + " " + units[unit] + "额度"
    return "周期额度 #" + str(index + 1)

def _reset(detail):
    for field in ("reset_at", "resetAt", "reset_time", "resetTime"):
        value = detail.get(field)
        if value is not None and value != "":
            if isinstance(value, str):
                try:
                    return "重置时间：" + datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M %Z")
                except ValueError:
                    pass
            return "重置时间：" + quota.format_reset(value)
    for field in ("reset_in", "resetIn", "ttl"):
        seconds = _amount(detail.get(field))
        if seconds is not None:
            return "接口返回：" + quota.pretty_number(seconds) + " 秒后重置"
    return ""

def quota_cards(payload):
    if not isinstance(payload, dict):
        raise quota.QueryError("Kimi 接口返回格式异常。")
    rows = []
    if isinstance(payload.get("usage"), dict):
        rows.append((payload["usage"], "周额度"))
    limits = payload.get("limits", [])
    if not isinstance(limits, list):
        raise quota.QueryError("Kimi 周期额度格式异常。")
    for index, item in enumerate(limits):
        if not isinstance(item, dict):
            raise quota.QueryError("Kimi 周期额度格式异常。")
        detail = item.get("detail", item)
        if not isinstance(detail, dict):
            raise quota.QueryError("Kimi 周期额度格式异常。")
        rows.append((detail, _label(item, detail, index)))
    cards = []
    for detail, default_title in rows:
        total = _amount(detail.get("limit"))
        used = _amount(detail.get("used"))
        remaining = _amount(detail.get("remaining"))
        if used is None and total is not None and remaining is not None and remaining <= total:
            used = total - remaining
        if remaining is None and total is not None and used is not None:
            remaining = max(0, total - used)
        if total is None and used is None and remaining is None:
            continue
        percent = min(100, 100 * used / total) if total and used is not None else None
        parts = []
        if used is not None: parts.append("已用 " + quota.pretty_number(used))
        if total is not None: parts.append("总计 " + quota.pretty_number(total))
        if remaining is not None: parts.append("剩余 " + quota.pretty_number(remaining))
        details = " · ".join(parts)
        reset = _reset(detail)
        if reset: details += "\n" + reset
        label = detail.get("name") or detail.get("title") or default_title
        title = str(label)[:160]
        cards.append({"title": "Kimi · " + title, "used": percent,
                      "remaining": 100 - percent if percent is not None else None,
                      "details": details or "接口未提供具体额度。"})
    if not cards:
        raise quota.QueryError("Kimi 未返回可用的套餐额度。请确认使用 Kimi Coding Plan Key，而不是开放平台余额 Key。")
    return cards

def fetch_quota(key, *, opener=None):
    key = quota.validate_key(key)
    request = urllib.request.Request(ENDPOINT, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
        "User-Agent": "QuotaCheck/1.4.0",
    }, method="GET")
    client = opener or urllib.request.build_opener(quota.NoRedirect())
    try:
        with client.open(request, timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise quota.QueryError("Kimi 接口响应过大，请稍后重试。")
            payload = json.loads(body.decode("utf-8-sig"))
            quota_cards(payload)
            return payload
    except urllib.error.HTTPError as exc:
        messages = {401: "Kimi Key 无效或已失效，请使用 Coding Plan Key。", 403: "Kimi 查询权限不足，请检查 Coding Plan 套餐状态。", 404: "Kimi 用量接口不可用，请确认套餐类型。", 429: "Kimi 查询过于频繁，请稍后重试。"}
        raise quota.QueryError(messages.get(exc.code, "Kimi 服务暂时不可用（HTTP %s）。" % exc.code)) from None
    except (TimeoutError, socket.timeout):
        raise quota.QueryError("Kimi 请求超时，请检查网络后重试。") from None
    except urllib.error.URLError:
        raise quota.QueryError("无法连接 Kimi，请检查网络或系统代理。") from None
    except (ValueError, UnicodeError):
        raise quota.QueryError("Kimi 接口未返回有效 JSON。") from None
