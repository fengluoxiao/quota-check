"""Versioned binary credential container: AES-256-GCM, DPAPI or Argon2id wrapping.
No hard-coded encryption key. No pickle or executable deserialization.
"""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
import settings
import service_providers
import quota

MAGIC=b"SQVAULT\0"
VERSION=1
LOCAL=0
PORTABLE=1
HEADER=struct.Struct(">8sBBI16s12sI")
MAX_SIZE=2*1024*1024
class VaultError(Exception):pass

def fresh():return {"version":1,"source":0,"profiles":{}}

def validate(data):
    if not isinstance(data,dict) or data.get("version")!=1 or not isinstance(data.get("profiles"),dict):
        raise VaultError("加密连接文件的数据格式无效。")
    result=fresh();result["source"]=data.get("source") if type(data.get("source")) is int and data.get("source") in range(12) else 0
    for name,record in data["profiles"].items():
        if name in service_providers.BY_ID:
            if not isinstance(record,dict) or ("sealed" in record and not isinstance(record["sealed"],bool)):raise VaultError("服务连接格式无效。")
            try:result["profiles"][name]=service_providers.validate_profile(name,record)
            except quota.QueryError:raise VaultError("服务连接凭据无效。") from None
            continue
        if name not in ("glm","sub2api","newapi","kimi") or not isinstance(record,dict):raise VaultError("连接文件包含不支持的连接类型。")
        allowed={"kimi":{"key","sealed"},"glm":{"site","key","sealed"},
                 "sub2api":{"url","email","password","access_token","refresh_token","user","sealed","cached"},
                 "newapi":{"url","username","password","sealed"}}[name]
        if set(record)-allowed:raise VaultError("连接文件包含不支持的字段。")
        item={}
        for k,v in record.items():
            if k in ("sealed","cached"):
                if not isinstance(v,bool):raise VaultError("连接字段格式无效。")
            elif k=="user":
                if not isinstance(v,dict) or set(v)-{"id","email","username","role"}:raise VaultError("登录会话格式无效。")
                if any(not isinstance(x,(str,int,type(None))) for x in v.values()):raise VaultError("登录会话格式无效。")
            elif not isinstance(v,str) or len(v)>32768:raise VaultError("连接字段格式无效或长度超限。")
            item[k]=copy.deepcopy(v)
        item["sealed"]=bool(item.get("sealed"))
        if name=="kimi":
            try:item["key"]=quota.validate_key(item.get("key",""))
            except quota.QueryError:raise VaultError("Kimi 连接信息不完整或 Key 无效。") from None
        if name=="glm" and (item.get("site") not in ("cn","global") or not item.get("key")):
            raise VaultError("GLM 连接信息不完整。")
        if name=="sub2api" and (not item.get("url") or not item.get("email") or not (item.get("password") or item.get("refresh_token"))):
            raise VaultError("sub2api 连接信息不完整。")
        if name=="newapi" and not all(item.get(k) for k in ("url","username","password")):
            raise VaultError("New API 连接信息不完整。")
        if name in ("sub2api","newapi"):
            from urllib.parse import urlsplit
            try:
                u=urlsplit(item["url"])
                if u.scheme not in ("http","https") or not u.hostname or u.username or u.password or u.query or u.fragment or any(c.isspace() for c in item["url"]):raise ValueError()
                _=u.port
            except ValueError:raise VaultError("连接文件中的服务器地址无效。") from None
        result["profiles"][name]=item
    return result

def _derive(password,salt):
    if not isinstance(password,str) or len(password)<12 or len(password)>1024:
        raise VaultError("跨电脑文件密码至少需要 12 个字符。")
    return Argon2id(salt=salt,length=32,iterations=3,lanes=4,memory_cost=65536).derive(password.encode("utf-8"))

def encode(data,*,password=None):
    data=validate(data)
    plain=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    if len(plain)>MAX_SIZE//2:raise VaultError("连接配置过大。")
    mode=LOCAL if password is None else PORTABLE
    salt=os.urandom(16);nonce=os.urandom(12)
    if mode==LOCAL:
        key=os.urandom(32);wrapped=settings.crypt(key)
    else:
        key=_derive(password,salt);wrapped=b""
    header=HEADER.pack(MAGIC,VERSION,mode,len(wrapped),salt,nonce,len(plain)+16)
    return header+wrapped+AESGCM(key).encrypt(nonce,plain,header+wrapped)

def inspect(blob):
    if not isinstance(blob,bytes) or len(blob)<HEADER.size+16 or len(blob)>MAX_SIZE:raise VaultError("文件大小无效或不是订阅额度连接文件。")
    magic,version,mode,wrapped_len,salt,nonce,size=HEADER.unpack_from(blob)
    if magic!=MAGIC or version!=VERSION or mode not in (LOCAL,PORTABLE):raise VaultError("文件格式或版本不受支持。")
    if wrapped_len>16384 or size<16 or HEADER.size+wrapped_len+size!=len(blob):raise VaultError("文件已损坏或长度无效。")
    if (mode==LOCAL and not wrapped_len) or (mode==PORTABLE and wrapped_len):raise VaultError("文件的加密参数无效。")
    return mode

def decode(blob,*,password=None):
    mode=inspect(blob)
    _,_,_,wrapped_len,salt,nonce,_=HEADER.unpack_from(blob)
    aad=blob[:HEADER.size+wrapped_len];cipher=blob[len(aad):]
    try:
        key=settings.crypt(blob[HEADER.size:len(aad)],decrypt=True) if mode==LOCAL else _derive(password,salt)
        plain=AESGCM(key).decrypt(nonce,cipher,aad)
        data=json.loads(plain.decode("utf-8"))
        return validate(data)
    except VaultError:raise
    except (InvalidTag,OSError,ValueError,TypeError,UnicodeError,OverflowError):
        message="此本机文件不属于当前 Windows 用户，或文件已损坏。" if mode==LOCAL else "文件密码不正确，或文件已损坏。"
        raise VaultError(message) from None

def exportable(data):
    result=validate(data)
    result["profiles"]={k:v for k,v in result["profiles"].items() if not v.get("sealed")}
    if not result["profiles"]:raise VaultError("没有可导出的自有连接。导入的连接只能查询，不能再次导出。")
    active={0:"glm",1:"sub2api",2:"kimi",**{s:p["id"] for s,p in service_providers.BY_SOURCE.items()}}
    if active[result["source"]] not in result["profiles"]:
        result["source"]=next((source for source,name in active.items() if name in result["profiles"]),0)
    return result

def imported(data):
    result=validate(data)
    if not result["profiles"]:raise VaultError("连接文件中没有可导入的连接。")
    for record in result["profiles"].values():record["sealed"]=True
    return result

def local_path():return settings.config_path().with_name("connections.sqv")

def atomic_write(path,blob):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix=path.name+".",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(blob);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def load_local():
    p=local_path()
    if p.exists():return decode(p.read_bytes())
    data=fresh()
    old=settings.load()
    if old.get("key"):data["profiles"]["glm"]={"site":old["site"],"key":old["key"],"sealed":False}
    return data

def save_local(data):atomic_write(local_path(),encode(data))
