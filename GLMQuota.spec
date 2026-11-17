# Build from this directory: python -m PyInstaller --noconfirm --clean GLMQuota.spec
import sys
import ssl
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
sys.setrecursionlimit(6000)
base = Path(SPECPATH)
datas, binaries, hiddenimports = collect_all('win32more')
datas.append((str(base / 'mobile' / 'src' / 'provider-catalog.json'), 'mobile/src'))
# This Python distribution loads an additional OpenSSL trust-policy PEM from
# beside ssl.py. Preserve that policy file when freezing the standard library.
ssl_policy = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
if ssl_policy.is_file():
    datas.append((str(ssl_policy), '.'))
# Only the x64 bootstrap DLL is needed for this x64 application.
datas = [(s,d) for s,d in datas if not any(x in s.replace('\\','/').lower() for x in ('/dll/arm64/','/dll/x86/'))]
binaries = [(s,d) for s,d in binaries if not any(x in s.replace('\\','/').lower() for x in ('/dll/arm64/','/dll/x86/'))]
a = Analysis([str(base / 'app.py')], pathex=[str(base)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['tkinter','unittest','pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='SubscriptionQuota-v1.5', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=str(base / 'app.ico') if (base / 'app.ico').exists() else None,
    version=str(base / 'version.txt'), uac_admin=False)
