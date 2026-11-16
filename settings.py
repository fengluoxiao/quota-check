"""Opt-in API key storage protected with Windows user-scoped DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

class Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

def crypt(data, decrypt=False):
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    lib = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = lib.CryptUnprotectData if decrypt else lib.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(target.pbData, target.cbData)
    finally: kernel.LocalFree(target.pbData)

def config_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "GLMQuota" / "settings.json"

def load():
    try:
        obj = json.loads(config_path().read_text(encoding="utf-8"))
        site = obj.get("site", "cn")
        key = crypt(base64.b64decode(obj["key"]), decrypt=True).decode("utf-8") if obj.get("key") else ""
        return {"site": site if site in ("cn", "global") else "cn", "key": key}
    except (OSError, ValueError, KeyError, TypeError):
        return {"site": "cn", "key": ""}

def save(site, key=""):
    obj = {"site": site}
    if key: obj["key"] = base64.b64encode(crypt(key.encode("utf-8"))).decode("ascii")
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(".tmp")
    temp.write_text(json.dumps(obj), encoding="utf-8")
    temp.replace(p)
