"""Coding Plan API client. Standard library only; no model requests are sent."""
from __future__ import annotations
import json
import math
import socket
import urllib.error
import urllib.request
from datetime import datetime

ENDPOINTS = {
    "cn": "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
    "global": "https://api.z.ai/api/monitor/usage/quota/limit",
}

class QueryError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise QueryError("接口发生重定向，已停止请求。请确认所选站点。")

def validate_key(key):
    key = key.strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise QueryError("请先输入 Coding Plan 的 API Key。")
    if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in key):
        raise QueryError("API Key 含有空格、换行或非英文字符，请重新粘贴。")
    return key

def parse_response(payload):
    if not isinstance(payload, dict):
        raise QueryError("接口返回格式异常：预期 JSON 对象。")
    code = payload.get("code")
    if payload.get("success") is False or (code is not None and str(code) not in ("0", "200")):
        raise QueryError("查询被拒绝（代码 %s），请检查 Key、站点和套餐状态。" % code)
    data = payload.get("data", payload)
    if not isinstance(data, dict) or not isinstance(data.get("limits"), list):
        raise QueryError("接口没有返回额度列表，请确认 Key 属于有效的个人 Coding Plan 套餐。")
    if any(not isinstance(item, dict) for item in data["limits"]):
        raise QueryError("接口额度列表格式异常。")
    return payload

def fetch_quota(key, site="cn", *, opener=None):
    key = validate_key(key)
    if site not in ENDPOINTS:
        raise QueryError("不支持的站点。")
    request = urllib.request.Request(ENDPOINTS[site], headers={
        "Authorization": key, "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9", "User-Agent": "GLMQuota/1.0",
    }, method="GET")
    client = opener or urllib.request.build_opener(NoRedirect())
    try:
        with client.open(request, timeout=20) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise QueryError("接口响应过大，请稍后重试。")
            return parse_response(json.loads(body.decode("utf-8-sig")))
    except urllib.error.HTTPError as exc:
        messages = {401: "Key 无效或已失效，请检查后重试。", 403: "没有查询权限，请检查所选站点和套餐状态。",
                    429: "查询过于频繁，请稍后重试。"}
        raise QueryError(messages.get(exc.code, "服务暂时不可用（HTTP %s），请稍后重试。" % exc.code)) from None
    except (TimeoutError, socket.timeout):
        raise QueryError("请求超时，请检查网络后重试。") from None
    except urllib.error.URLError:
        raise QueryError("网络连接失败，请检查网络、系统代理和所选站点。") from None
    except (ValueError, UnicodeError):
        raise QueryError("接口没有返回有效的 JSON，请稍后重试。") from None

def number(value):
    if isinstance(value, bool): return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError): return None

def pretty_number(value):
    v = number(value)
    return f"{v:,.0f}" if v is not None and v.is_integer() else (f"{v:,.2f}" if v is not None else "—")

def format_reset(value):
    if value is None or value == "": return ""
    v = number(value)
    if v is not None:
        try:
            if v > 1e11: v /= 1000
            if v < 946684800: return str(value)
            return datetime.fromtimestamp(v).astimezone().strftime("%Y-%m-%d %H:%M %Z")
        except (ValueError, OverflowError, OSError): pass
    return str(value)[:160]

def quota_cards(payload):
    data = payload.get("data", payload)
    cards = []
    for item in data["limits"]:
        kind = str(item.get("type", "未知额度"))
        title = {"TOKENS_LIMIT": "模型额度", "CREDIT_LIMIT": "模型额度", "TIME_LIMIT": "MCP 工具额度"}.get(kind, kind)
        unit = number(item.get("unit"))
        period = {1: "天", 3: "小时", 5: "月", 6: "周"}.get(unit)
        if unit == 6:
            title += " · 每周"
        elif period:
            count = number(item.get("number"))
            if count is not None and count > 0:
                title += f" · {pretty_number(count)} {period}"
            else:
                title += {3: " · 5 小时", 5: " · 每月", 1: " · 每日"}.get(unit, "")
        p = number(item.get("percentage"))
        valid_percent = p is not None and 0 <= p <= 100
        details = []
        if item.get("currentValue") is not None and item.get("usage") is not None:
            used, total = number(item["currentValue"]), number(item["usage"])
            if used is not None and total is not None and 0 <= used <= total:
                details.append(f"已用 {pretty_number(used)} / 总计 {pretty_number(total)} · 剩余 {pretty_number(total-used)}")
        for field in ("nextResetTime", "resetTime", "resetAt", "renewTime"):
            if item.get(field):
                details.append("重置时间：" + format_reset(item[field]))
                break
        usage_details = item.get("usageDetails")
        for d in usage_details if isinstance(usage_details, list) else []:
            if isinstance(d, dict):
                name = d.get("modelCode") or d.get("name") or d.get("type") or "工具"
                value = d.get("usage", d.get("currentValue"))
                if value is not None: details.append(f"{name}：{pretty_number(value)}")
        cards.append({"title": title, "used": p if valid_percent else None,
                      "remaining": 100-p if valid_percent else None,
                      "details": "\n".join(details) or "接口未提供具体次数或重置时间。"})
    return cards

def redact_payload(value, key=""):
    # The UI never exports headers, and masks credential-shaped fields if the API adds them.
    if isinstance(value, dict):
        return {k: ("[已隐藏]" if any(s in str(k).lower().replace("_", "") for s in ("apikey", "authorization", "authtoken", "accesstoken", "refreshtoken", "idtoken", "sessiontoken", "credential", "cookie", "secret", "password")) else redact_payload(v, key)) for k,v in value.items()}
    if isinstance(value, list): return [redact_payload(v, key) for v in value]
    if isinstance(value, str) and key: return value.replace(key, "[已隐藏]")
    return value
