"""Read GPT/Codex subscription usage through a user's sub2api administrator login."""
from __future__ import annotations
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from quota import QueryError, NoRedirect, validate_key, number, pretty_number, format_reset

class Sub2APIError(QueryError):
    def __init__(self, message, *, status=0, reason=""):
        super().__init__(message)
        self.status, self.reason = status, str(reason)

class LoginCodeRequired(Sub2APIError): pass

def normalize_url(value):
    value=value.strip().rstrip("/")
    try:
        parsed=urllib.parse.urlsplit(value)
        if parsed.scheme not in ("http","https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        _=parsed.port
        if any(c.isspace() or ord(c)<32 for c in value): raise ValueError()
    except ValueError:
        raise Sub2APIError("请填写有效的 sub2api 站点地址，如 https://sub.example.com。") from None
    for suffix in ("/api/v1", "/api"):
        if value.endswith(suffix): value=value[:-len(suffix)];break
    return value

def local_time(value):
    if value is None or value=="": return ""
    n=number(value)
    if n is not None: return format_reset(n)
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    except (ValueError,TypeError,OverflowError,OSError): return str(value)[:100]

def _nearest_expiration(grants):
    values=[]
    for grant in grants if isinstance(grants,list) else []:
        raw=grant.get("expires_at") if isinstance(grant,dict) else None
        if raw is None or raw=="": continue
        seconds=number(raw)
        if seconds is not None:
            if seconds>1e11: seconds/=1000
            try: value=datetime.fromtimestamp(seconds,timezone.utc)
            except (ValueError,OverflowError,OSError): continue
        else:
            try:
                value=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
                if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
            except (ValueError,TypeError,OverflowError,OSError): continue
        values.append(value)
    if not values: return ""
    now=datetime.now(timezone.utc)
    nearest=min(values,key=lambda item:((item<now),abs(item-now)))
    return "最近到期："+local_time(nearest.timestamp())

def window_name(seconds, fallback="窗口"):
    seconds=number(seconds)
    if seconds is None or seconds<=0: return fallback
    if seconds==18000:return "5 小时"
    if seconds==604800:return "7 天"
    if seconds%86400==0:return pretty_number(seconds/86400)+" 天"
    if seconds%3600==0:return pretty_number(seconds/3600)+" 小时"
    return pretty_number(seconds/60)+" 分钟"

def _card(title, used, reset=None, after=None, details=None, fetched=None):
    used=number(used)
    if used is not None and used<0: used=None
    lines=list(details or [])
    if reset:
        lines.append("重置时间："+local_time(reset))
    elif number(after) is not None and number(after)>=0:
        # Only turn a relative duration into a time when the API supplied its sample time.
        sample=number(fetched)
        if sample is not None:
            lines.append("重置时间："+local_time(sample+number(after)))
        else:
            lines.append("距重置约 "+pretty_number(number(after)/60)+" 分钟（接口返回）")
    return {"title":title,"used":used,"remaining":max(0,100-used) if used is not None else None,
            "details":"\n".join(lines) or "接口未提供具体次数或重置时间。"}

def usage_cards(payload):
    """Accept the official read-only OpenAI quota response and cached account snapshots."""
    if not isinstance(payload,dict):raise Sub2APIError("sub2api 额度响应格式异常。")
    if payload.get("source")=="snapshot":
        return snapshot_cards(payload.get("extra",{}))
    data=payload.get("usage",payload)
    if not isinstance(data,dict):raise Sub2APIError("sub2api 额度响应格式异常。")
    fetched=data.get("fetched_at")
    cards=[]
    def add_rate_limit(rate,label):
        if not isinstance(rate,dict):return
        for key,fallback in (("primary_window","主窗口"),("secondary_window","次窗口")):
            item=rate.get(key)
            if isinstance(item,dict):
                duration=item.get("limit_window_seconds",item.get("rate_limit_window_seconds"))
                name=window_name(duration,fallback)
                cards.append(_card(label+" · "+name,item.get("used_percent"),item.get("reset_at"),item.get("reset_after_seconds"),fetched=fetched))
    add_rate_limit(data.get("rate_limit"),"GPT / Codex")
    additional=data.get("additional_rate_limits")
    if isinstance(additional,list):
        for item in additional:
            if isinstance(item,dict):
                label=str(item.get("limit_name") or item.get("metered_feature") or "附加额度")
                add_rate_limit(item.get("rate_limit"),label)
    for key,label in (("code_review_rate_limit","代码审查"),("codex_rate_limit","Codex")):
        add_rate_limit(data.get(key),label)
    # Some versions return the normalized generic usage structure instead.
    if not cards:
        for key,label in (("five_hour","GPT / Codex · 5 小时"),("seven_day","GPT / Codex · 7 天"),("thirty_day","GPT / Codex · 30 天")):
            item=data.get(key)
            if not isinstance(item,dict):continue
            detail=[]
            used,total=number(item.get("used_requests")),number(item.get("limit_requests"))
            if used is not None and total is not None and total>0 and used>=0:
                detail.append("请求次数：已用 "+pretty_number(used)+" / 总计 "+pretty_number(total))
            cards.append(_card(label,item.get("utilization"),item.get("resets_at"),item.get("remaining_seconds"),detail,fetched))
    return cards

SNAPSHOT_KEYS={"codex_usage_updated_at"}
for _part in ("5h","7d","primary","secondary"):
    for _suffix in ("used_percent","reset_after_seconds","reset_at","window_minutes"):
        SNAPSHOT_KEYS.add("codex_"+_part+"_"+_suffix)

def snapshot_cards(extra):
    if not isinstance(extra,dict):return []
    cards=[]
    # Canonical names take precedence. Do not assume the primary window is 5h.
    for part,label in (("5h","5 小时"),("7d","7 天")):
        key="codex_"+part+"_used_percent"
        if key in extra:
            cards.append(_card("GPT / Codex · "+label,extra[key],extra.get("codex_"+part+"_reset_at"),
                extra.get("codex_"+part+"_reset_after_seconds"),["数据来源：sub2api 后台快照"],extra.get("codex_usage_updated_at")))
    if not cards:
        for part,fallback in (("primary","主窗口"),("secondary","次窗口")):
            key="codex_"+part+"_used_percent"
            if key in extra:
                minutes=number(extra.get("codex_"+part+"_window_minutes"))
                label=window_name(minutes*60 if minutes is not None else None,fallback)
                cards.append(_card("GPT / Codex · "+label,extra[key],extra.get("codex_"+part+"_reset_at"),
                    extra.get("codex_"+part+"_reset_after_seconds"),["数据来源：sub2api 后台快照"],extra.get("codex_usage_updated_at")))
    return cards

def _live_usage(payload):
    if not isinstance(payload, dict): raise Sub2APIError("sub2api 额度响应格式异常。")
    data=payload.get("usage",payload)
    if not isinstance(data,dict): raise Sub2APIError("sub2api 额度响应格式异常。")
    return data

def reset_credit_card(payload):
    data=_live_usage(payload);credits=data.get("rate_limit_reset_credits")
    if not isinstance(credits,dict): raise Sub2APIError("当前 sub2api / 上游响应没有返回重置卡次数。")
    count=number(credits.get("available_count"))
    if count is None or count<0: raise Sub2APIError("重置卡次数格式无效，未推算可用数量。")
    lines=["可用重置卡次数："+pretty_number(count)]
    grants=credits.get("credits")
    expanded=[]
    if isinstance(grants,list):
        nearest=_nearest_expiration(grants)
        if nearest: lines.append(nearest)
        for index,grant in enumerate(grants,1):
            expires=local_time(grant.get("expires_at")) if isinstance(grant,dict) else ""
            expanded.append(f"#{index} · "+("到期："+expires if expires else "接口未返回到期时间"))
    else:
        lines.append("接口未返回到期明细，无法核对每张卡。")
    if isinstance(grants,list) and count!=len(grants):
        lines.append("接口计数与明细条数不同；仅展示返回明细，不推算差额。")
    if isinstance(grants,list) and len(grants)>5:
        lines.append("明细较多，展开查看。")
    return {"title":"重置卡次数","used":None,"remaining":None,"details":"\n".join(lines),"expanded_details":expanded}

def codex_credit_card(payload):
    data=_live_usage(payload);credits=data.get("credits")
    if not isinstance(credits,dict): raise Sub2APIError("当前 sub2api / 上游响应没有返回点数余额。")
    unlimited=credits.get("unlimited")
    balance=credits.get("balance")
    if unlimited is True:
        lines=["点数余额：接口标记为不限量"]
    elif balance is not None and balance!="":
        value=number(balance)
        if value is None or value<0 or len(str(balance))>64: raise Sub2APIError("点数余额格式无效，未推算可用余额。")
        lines=["点数余额："+str(balance)]
    elif credits.get("has_credits") is False:
        lines=["点数余额：接口返回没有可展示余额"]
    else:
        raise Sub2APIError("接口未返回具体点数余额，未推算可用余额。")
    return {"title":"Codex 点数","used":None,"remaining":None,"details":"\n".join(lines)}

MESSAGES={
 "INVALID_CREDENTIALS":"sub2api 邮箱或密码不正确。",
 "INVALID_PASSWORD":"sub2api 邮箱或密码不正确。",
 "USER_DISABLED":"此 sub2api 用户已停用。",
 "ADMIN_REQUIRED":"读取 OpenAI 账号额度需要 sub2api 管理员权限。",
 "ADMIN_COMPLIANCE_ACK_REQUIRED":"请先在 sub2api 后台完成部署确认，再返回此工具查询。",
 "OPENAI_QUOTA_AUTH_FAILED":"sub2api 中的 GPT 账号授权已失效，请在该后台重新授权。",
 "OPENAI_QUOTA_UPSTREAM_ERROR":"sub2api 查询上游额度失败，请到后台检查该 GPT 账号的授权与连接。",
 "OPENAI_QUOTA_REQUEST_FAILED":"sub2api 无法连接上游额度接口，请检查服务端代理及账号状态。",
 "CAPTCHA_REQUIRED":"站点要求人机验证，请在高级选项填写有效验证码凭据。",
 "CAPTCHA_INVALID":"站点人机验证未通过，请更新高级选项中的验证码凭据。",
 "TURNSTILE_FAILED":"站点人机验证未通过，请更新高级选项中的验证码凭据。",
}

class Sub2APIClient:
    def __init__(self,url,*,opener=None):
        self.url=normalize_url(url)
        self.opener=opener or urllib.request.build_opener(NoRedirect())
        self.access_token="";self.refresh_token="";self.user={};self.pending=None
        self.login_email=""

    def _request_once(self,route,body=None,*,auth=True):
        if not route.startswith("/") or route.startswith("//"):raise Sub2APIError("无效的 sub2api 接口路径。")
        headers={"Accept":"application/json","Accept-Language":"zh-CN","User-Agent":"SubscriptionQuota/1.1"}
        if auth and self.access_token:headers["Authorization"]="Bearer "+self.access_token
        raw=None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
        if raw is not None:headers["Content-Type"]="application/json"
        request=urllib.request.Request(self.url+"/api/v1"+route,data=raw,headers=headers,method="GET" if body is None else "POST")
        status=200
        try:
            try:response=self.opener.open(request,timeout=30)
            except urllib.error.HTTPError as exc:response,status=exc,exc.code
            with response:
                raw=response.read(8_000_001)
                if len(raw)>8_000_000:raise Sub2APIError("sub2api 响应过大，已停止读取。")
                try:payload=json.loads(raw.decode("utf-8-sig"))
                except (ValueError,UnicodeError):
                    raise Sub2APIError("sub2api 没有返回有效 JSON，请检查站点地址与反向代理。",status=status) from None
        except (TimeoutError,urllib.error.URLError):
            raise Sub2APIError("连接 sub2api 失败或超时，请检查地址、网络和代理。") from None
        if not isinstance(payload,dict):raise Sub2APIError("sub2api 响应格式异常。")
        if status>=400 or str(payload.get("code"))!="0":
            reason=str(payload.get("reason") or payload.get("code") or status)
            message=MESSAGES.get(reason)
            if not message:
                message={401:"sub2api 登录失效或邮箱密码错误，请重新登录。",403:"sub2api 拒绝了请求，请确认账号具有管理员权限。",404:"当前 sub2api 版本未提供此接口或账号不存在。",405:"当前 sub2api 版本不支持此接口。",429:"sub2api 操作过于频繁，请稍后重试。"}.get(status,"sub2api 请求失败，请检查账号状态和服务端配置。")
            raise Sub2APIError(message,status=status,reason=reason)
        return payload.get("data")

    def request(self,route,body=None):
        try:return self._request_once(route,body)
        except Sub2APIError as exc:
            if exc.status!=401 or not self.refresh_token:raise
            # Refresh only the panel login session; never extract/refresh the upstream GPT credential.
            data=self._request_once("/auth/refresh",{"refresh_token":self.refresh_token},auth=False)
            self._tokens(data,require_user=False)
            return self._request_once(route,body)

    def _tokens(self,data,*,require_user=True):
        if not isinstance(data,dict) or not isinstance(data.get("access_token"),str):
            raise Sub2APIError("sub2api 登录响应缺少访问令牌。")
        self.access_token=validate_key(data["access_token"])
        if data.get("refresh_token"):self.refresh_token=validate_key(data["refresh_token"])
        if require_user:
            user=data.get("user")
            if not isinstance(user,dict):raise Sub2APIError("sub2api 登录响应缺少用户信息。")
            self.user={k:user.get(k) for k in ("id","email","username","role")}
            if self.user.get("role")!="admin":
                self.access_token="";self.refresh_token=""
                raise Sub2APIError("当前 sub2api 用户不是管理员，无法读取上游 GPT 账号额度。")
        self.pending=None
        return self.user

    def login(self,email,password,*,turnstile=""):
        email=email.strip()
        if not email or not password:raise Sub2APIError("请填写 sub2api 管理员邮箱和密码。")
        self.access_token="";self.refresh_token="";self.user={};self.pending=None
        self.login_email=email
        body={"email":email,"password":password}
        if turnstile.strip():body["turnstile_token"]=turnstile.strip()
        data=self._request_once("/auth/login",body,auth=False)
        if isinstance(data,dict) and data.get("requires_2fa"):
            if not isinstance(data.get("temp_token"),str):raise Sub2APIError("sub2api 登录响应缺少临时验证凭据。")
            self.pending=data["temp_token"]
            raise LoginCodeRequired("此 sub2api 账号启用了 2FA，请填写登录验证码后继续。")
        return self._tokens(data)

    def complete_login(self,code):
        if not self.pending:raise Sub2APIError("请先提交 sub2api 邮箱和密码。")
        code=code.strip()
        if len(code)!=6 or not code.isascii() or not code.isdigit():raise LoginCodeRequired("请输入 6 位登录验证码。")
        data=self._request_once("/auth/login/2fa",{"temp_token":self.pending,"totp_code":code},auth=False)
        return self._tokens(data)

    def list_accounts(self):
        if self.user.get("role")!="admin":raise Sub2APIError("请先使用 sub2api 管理员账号登录。")
        rows=[];seen=set();processed=0
        for page in range(1,101):
            params=urllib.parse.urlencode({"page":page,"page_size":100,"platform":"openai","type":"oauth"})
            data=self.request("/admin/accounts?"+params)
            if not isinstance(data,dict) or not isinstance(data.get("items"),list):raise Sub2APIError("sub2api 账号列表格式异常。")
            added=0
            processed+=len(data["items"])
            for row in data["items"]:
                if not isinstance(row,dict) or row.get("platform","openai")!="openai" or row.get("type","oauth")!="oauth":continue
                account_id=row.get("id")
                if not isinstance(account_id,int) or isinstance(account_id,bool) or account_id<=0 or account_id in seen:continue
                seen.add(account_id);added+=1
                rows.append({k:row.get(k) for k in ("id","name","platform","type","status")})
            total=number(data.get("total"))
            if (total is not None and processed>=total) or not data["items"] or (total is None and len(data["items"])<100):break
        return sorted(rows,key=lambda row:(row.get("status")!="active",str(row.get("name") or ""),row["id"]))

    def fetch_usage(self,account,*,cached=False):
        account_id=account.get("id") if isinstance(account,dict) else None
        if not isinstance(account_id,int) or isinstance(account_id,bool) or account_id<=0:raise Sub2APIError("请选择有效的 GPT 账号。")
        fallback=False
        if not cached:
            try:
                data=self.request(f"/admin/openai/accounts/{account_id}/quota")
                if not isinstance(data,dict):raise Sub2APIError("sub2api 额度响应格式异常。")
                return {"source":"live","account":account,"usage":data,"updated_at":data.get("fetched_at",data.get("updated_at"))}
            except Sub2APIError as exc:
                if exc.status not in (404,405,501):raise
                fallback=True
        data=self.request(f"/admin/accounts/{account_id}")
        if not isinstance(data,dict):raise Sub2APIError("sub2api 账号快照格式异常。")
        extra=data.get("extra")
        extra={k:v for k,v in extra.items() if k in SNAPSHOT_KEYS} if isinstance(extra,dict) else {}
        if not snapshot_cards(extra):
            raise Sub2APIError("后台还没有这个 GPT 账号的额度快照。请更新 sub2api 以支持实时查询，或等待后台采集到实际用量。")
        return {"source":"snapshot","account":account,"extra":extra,"updated_at":extra.get("codex_usage_updated_at"),"fallback":fallback}

    def query_usage(self,account):
        account_id=account.get("id") if isinstance(account,dict) else None
        if not isinstance(account_id,int) or isinstance(account_id,bool) or account_id<=0:raise Sub2APIError("请选择有效的 GPT 账号。")
        data=self.request(f"/admin/openai/accounts/{account_id}/quota")
        if not isinstance(data,dict):raise Sub2APIError("sub2api 额度响应格式异常。")
        return data

    def query_reset_credits(self,account):
        return reset_credit_card(self.query_usage(account))

    def query_credits(self,account):
        return codex_credit_card(self.query_usage(account))

    def refresh_usage(self,account):
        account_id=account.get("id") if isinstance(account,dict) else None
        if not isinstance(account_id,int) or isinstance(account_id,bool) or account_id<=0:raise Sub2APIError("请选择有效的 GPT 账号。")
        data=self.request(f"/admin/openai/accounts/{account_id}/quota/refresh",{})
        if not isinstance(data,dict):raise Sub2APIError("sub2api 刷新额度响应格式异常。")
        return {"source":"live","account":account,"usage":data,"updated_at":data.get("fetched_at",data.get("updated_at")),"refreshed":True}
