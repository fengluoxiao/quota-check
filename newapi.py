"""New API username/password login and channel-key retrieval.
Supports cookie sessions and newer bearer login bundles. Secrets stay in memory.
"""
from __future__ import annotations
import base64
import http.cookiejar
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from quota import QueryError, NoRedirect, validate_key

class NewAPIError(QueryError):
    def __init__(self, message, code=""):
        super().__init__(message)
        self.code = str(code)

class LoginCodeRequired(NewAPIError): pass

def normalize_url(value):
    value = value.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        _ = parsed.port
        if any(c.isspace() or ord(c)<32 for c in value): raise ValueError()
    except ValueError:
        raise NewAPIError("请填写有效的 New API 地址，如 https://newapi.example.com。") from None
    if value.endswith("/api"): value = value[:-4]
    return value

def encrypt_password(password, key_data):
    # Matches New API's published RSA-OAEP SHA-256 password envelope.
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    kid = key_data.get("kid")
    try:
        key = serialization.load_pem_public_key(key_data["public_key"].encode("ascii"))
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048: raise ValueError()
        raw = password.encode("utf-8")
        def pad(label=None): return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=label)
        b64 = lambda b: base64.b64encode(b).decode("ascii")
        if len(raw) <= key.key_size // 8 - 66:
            encrypted = b64(key.encrypt(raw, pad()))
        else:
            secret, nonce = os.urandom(32), os.urandom(12)
            wrapped = key.encrypt(secret, pad(b"password-v2"))
            ciphertext = AESGCM(secret).encrypt(nonce, raw, ("password-v2:"+str(kid)).encode())
            encrypted = ".".join(("v2", b64(wrapped), b64(nonce), b64(ciphertext)))
        if not isinstance(kid, str) or not kid: raise ValueError()
        return {"password_encrypted": encrypted, "encryption_key_id": kid}
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise NewAPIError("New API 的密码加密公钥格式无效，已停止登录。") from None

ERRORS = {
    "SECURITY_PROOF_REQUIRED": "读取渠道 Key 需要安全验证，请输入新的 2FA 验证码后重试。",
    "VERIFICATION_REQUIRED": "读取渠道 Key 需要安全验证，请输入 2FA 验证码后重试。",
    "SECURITY_VERIFICATION_FAILED": "安全验证失败，请检查验证码；登录用过的验证码可能不能再次使用。",
    "SECURITY_VERIFICATION_LOCKED": "安全验证已被暂时锁定，请在 New API 后台确认后重试。",
    "SECURITY_METHOD_UNAVAILABLE": "服务器不允许此验证方式；可改用手动粘贴 GLM Key。",
    "SECURITY_PROOF_EXPIRED": "安全验证已过期，请输入新的验证码后重试。",
    "SECURITY_PROOF_CONSUMED": "安全验证凭据已使用，请输入新的验证码后重试。",
    "SECURITY_ACTION_FORBIDDEN": "账号没有执行此操作的权限。读取渠道 Key 需要超级管理员。",
    "AUTH_INSUFFICIENT_PRIVILEGE": "账号权限不足。读取渠道原始 Key 需要超级管理员。",
    "AUTH_TOKEN_EXPIRED": "登录已过期，请重新登录。",
}

class NewAPIClient:
    def __init__(self, url, *, opener=None):
        self.url = normalize_url(url)
        self.cookies = http.cookiejar.CookieJar()
        self.opener = opener or urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.cookies))
        self.access_token = ""
        self.user = {}
        self.pending = None

    def request(self, route, body=None, *, headers=None):
        if not route.startswith("/api/") or route.startswith("//"): raise NewAPIError("无效的管理接口路径。")
        h = {"Accept": "application/json", "Accept-Language": "zh-CN", "User-Agent": "GLMQuota/1.0"}
        if self.access_token: h["Authorization"] = "Bearer " + self.access_token
        if self.user.get("id"): h["New-Api-User"] = str(self.user["id"])
        if headers: h.update(headers)
        raw = None if body is None else json.dumps(body,ensure_ascii=False).encode("utf-8")
        if raw is not None: h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.url+route, data=raw, headers=h, method="GET" if body is None else "POST")
        status = 200
        try:
            try:
                response = self.opener.open(req,timeout=20)
            except urllib.error.HTTPError as exc:
                response, status = exc, exc.code
            with response:
                raw_response = response.read(4_000_001)
                if len(raw_response)>4_000_000: raise NewAPIError("New API 响应过大，已停止读取。")
                try: payload = json.loads(raw_response.decode("utf-8-sig"))
                except (ValueError,UnicodeError):
                    raise NewAPIError("New API 没有返回有效 JSON（HTTP %s），请检查地址和反向代理。" % status,str(status)) from None
        except (TimeoutError, urllib.error.URLError):
            raise NewAPIError("连接 New API 失败或超时，请检查地址、网络和代理。") from None
        if not isinstance(payload,dict): raise NewAPIError("New API 返回格式异常。")
        if status>=400 or payload.get("success") is not True:
            code = str(payload.get("code",status))
            message = ERRORS.get(code)
            if not message:
                message = {401:"New API 登录失效或账号密码不正确，请重新登录。",403:"New API 拒绝了请求，请检查超级管理员权限和安全验证。",404:"New API 没有提供此接口，请确认部署版本。",429:"操作过于频繁，请稍后重试。"}.get(status,"New API 请求失败，请检查账号密码、权限和服务端设置。")
            # Do not display arbitrary server messages, which could echo a secret.
            raise NewAPIError(message,code)
        return payload

    def _accept_login(self, payload):
        data = payload.get("data")
        if not isinstance(data,dict): raise NewAPIError("登录响应没有用户信息。")
        if data.get("require_verification") or data.get("require_2fa"):
            self.pending = data
            raise LoginCodeRequired("此账号需要登录验证。请填写登录用 2FA 验证码，再点击继续登录。")
        token = data.get("access_token")
        if token: self.access_token = validate_key(token)
        self.user = data.get("user",data)
        if not isinstance(self.user,dict) or not self.user.get("id"):
            raise NewAPIError("登录响应缺少用户 ID。")
        self.pending = None
        return self.user

    def login(self, username, password, *, turnstile=""):
        if not username.strip() or not password: raise NewAPIError("请填写 New API 账号和密码。")
        self.access_token, self.user, self.pending = "", {}, None
        status = self.request("/api/status").get("data",{})
        if not isinstance(status,dict): raise NewAPIError("无法读取 New API 的登录配置。")
        if status.get("password_login") is False: raise NewAPIError("这个 New API 站点已关闭账号密码登录。")
        if status.get("turnstile_check") and not turnstile.strip():
            raise NewAPIError("站点启用了 Turnstile 人机验证。请在高级选项填写有效的 Turnstile Token，或从后台手动复制 GLM Key。")
        fields = {"password":password}
        if status.get("password_login_encryption_enabled"):
            key_data=self.request("/api/user/login/encryption-key").get("data",{})
            fields=encrypt_password(password,key_data)
        route = "/api/user/login"
        if turnstile.strip(): route += "?"+urllib.parse.urlencode({"turnstile":turnstile.strip()})
        return self._accept_login(self.request(route,{"username":username.strip(),**fields}))

    def complete_login(self, code):
        if self.pending is None: raise NewAPIError("请先提交账号密码。")
        code=code.strip()
        if not code: raise LoginCodeRequired("请填写登录用 2FA 验证码。")
        flow=self.pending.get("flow_token")
        if flow:
            methods=self.pending.get("methods",[])
            if methods and not any(m.get("method")=="2fa" and m.get("available",True) for m in methods if isinstance(m,dict)):
                raise NewAPIError("此账号的登录验证仅支持 Passkey，当前工具支持 2FA；请在后台取 Key 后手动粘贴。")
            payload=self.request("/api/user/login/verify",{"flow_token":flow,"method":"2fa","code":code})
        else:
            payload=self.request("/api/user/login/2fa",{"code":code})
        return self._accept_login(payload)

    def list_channels(self):
        self.require_root()
        rows,seen=[],set()
        for page in range(1,101):
            data=self.request(f"/api/channel/?p={page}&page_size=100").get("data")
            if isinstance(data,dict): items=data.get("items",[]); total=data.get("total")
            elif isinstance(data,list): items=data; total=None
            else: raise NewAPIError("渠道列表响应格式异常。")
            if not isinstance(items,list): raise NewAPIError("渠道列表响应格式异常。")
            added=0
            for row in items:
                if isinstance(row,dict) and row.get("id") is not None and row["id"] not in seen:
                    # Never keep the 'key' field from a list response.
                    seen.add(row["id"]); rows.append({k:row.get(k) for k in ("id","name","models","base_url","type")}); added+=1
            if not added or (isinstance(total,int) and len(rows)>=total) or (total is None and len(items)<100): break
        def likely_glm(row):
            text=" ".join(str(row.get(k,"")) for k in ("name","models","base_url")).lower()
            return any(s in text for s in ("glm","智谱","bigmodel.cn","api.z.ai"))
        return sorted(rows,key=lambda row:(not likely_glm(row),str(row.get("name","")),row["id"]))

    def require_root(self):
        try: role=int(self.user.get("role",0))
        except (TypeError,ValueError): role=0
        if role<100: raise NewAPIError("当前账号不是超级管理员（root），无法读取渠道原始 Key。请使用 root 账号或手动粘贴 GLM Key。")

    def channel_keys(self, channel_id, code=""):
        self.require_root()
        if isinstance(channel_id,bool) or not str(channel_id).isdigit() or int(channel_id)<=0: raise NewAPIError("请选择有效的渠道。")
        channel_id=int(channel_id)
        headers={}
        if code.strip():
            verification=self.request("/api/verify",{"method":"2fa","scope":"channel.key.read","context":{"channel_id":channel_id},"code":code.strip()})
            data=verification.get("data")
            # New versions return a single-use proof. Old versions update the cookie session.
            if isinstance(data,dict) and data.get("proof_token"):
                headers["X-Security-Proof"]=validate_key(data["proof_token"])
        data=self.request(f"/api/channel/{channel_id}/key",{},headers=headers).get("data")
        raw=data.get("key") if isinstance(data,dict) else None
        if not isinstance(raw,str) or not raw.strip(): raise NewAPIError("渠道没有返回可用 Key。")
        keys=[]
        for line in raw.splitlines():
            line=line.strip()
            if not line: continue
            if line.startswith(("{","[")) or "*" in line or "…" in line:
                raise NewAPIError("此渠道返回的是脱敏值或插件凭据，不是可直接使用的 GLM Key。请手动获取原始 Key。")
            key=validate_key(line)
            if key not in keys: keys.append(key)
        if not keys: raise NewAPIError("渠道没有返回可用 Key。")
        return keys
