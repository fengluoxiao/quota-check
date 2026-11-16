"""Native Windows file pickers owned by the application window."""
import ctypes
from ctypes import wintypes
from vault import VaultError

class OpenFileName(ctypes.Structure):
    _fields_=[("lStructSize",wintypes.DWORD),("hwndOwner",wintypes.HWND),("hInstance",wintypes.HINSTANCE),
    ("lpstrFilter",wintypes.LPCWSTR),("lpstrCustomFilter",wintypes.LPWSTR),("nMaxCustFilter",wintypes.DWORD),
    ("nFilterIndex",wintypes.DWORD),("lpstrFile",wintypes.LPWSTR),("nMaxFile",wintypes.DWORD),
    ("lpstrFileTitle",wintypes.LPWSTR),("nMaxFileTitle",wintypes.DWORD),("lpstrInitialDir",wintypes.LPCWSTR),
    ("lpstrTitle",wintypes.LPCWSTR),("Flags",wintypes.DWORD),("nFileOffset",wintypes.WORD),
    ("nFileExtension",wintypes.WORD),("lpstrDefExt",wintypes.LPCWSTR),("lCustData",ctypes.c_ssize_t),
    ("lpfnHook",ctypes.c_void_p),("lpTemplateName",wintypes.LPCWSTR),("pvReserved",ctypes.c_void_p),
    ("dwReserved",wintypes.DWORD),("FlagsEx",wintypes.DWORD)]

def pick(window,*,save=False):
    from win32more.Microsoft.UI.Interop import GetWindowFromWindowId
    handle=GetWindowFromWindowId(window.AppWindow.Id)
    buffer=ctypes.create_unicode_buffer(32768)
    if save:buffer.value="订阅额度连接.sqv"
    info=OpenFileName();info.lStructSize=ctypes.sizeof(info)
    info.hwndOwner=handle.value if hasattr(handle,"value") else handle
    info.lpstrFilter="订阅额度加密连接 (*.sqv)\0*.sqv\0所有文件 (*.*)\0*.*\0\0"
    info.nFilterIndex=1;info.lpstrFile=ctypes.cast(buffer,wintypes.LPWSTR);info.nMaxFile=len(buffer)
    info.lpstrDefExt="sqv";info.lpstrTitle="保存加密连接文件" if save else "导入加密连接文件"
    info.Flags=0x80000|0x800|0x8|(0x2 if save else 0x1000)
    lib=ctypes.WinDLL("comdlg32",use_last_error=True)
    fn=lib.GetSaveFileNameW if save else lib.GetOpenFileNameW
    fn.argtypes=[ctypes.POINTER(OpenFileName)];fn.restype=wintypes.BOOL
    lib.CommDlgExtendedError.restype=wintypes.DWORD
    if fn(ctypes.byref(info)):return buffer.value
    if lib.CommDlgExtendedError():raise VaultError("无法打开文件选择窗口。")
    return None
