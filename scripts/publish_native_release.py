"""Publish verified artifacts from the current commit; never replace another commit's release."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
assets=Path(sys.argv[1]).resolve()
version=json.loads((root/'mobile/package.json').read_text(encoding='utf-8'))['version']
sha=os.environ['GITHUB_SHA'];repo=os.environ['GITHUB_REPOSITORY']
assert os.environ['GITHUB_REF']=='refs/heads/main'
windows=json.loads((assets/'windows/windows-verification.json').read_text(encoding='utf-8'))
health=json.loads((assets/'ios/native-health.json').read_text(encoding='utf-8'))
assert windows['ok'] and windows['commit']==sha and windows['version']==version
assert len(windows['providers'])==9 and all(p['ok'] for p in windows['providers'])
assert all(health.get(k) is True for k in ('ok','crypto','storage','signing','importPersistence'))
assert health.get('keychain') is True or health.get('keychainFallback') is True
assert health.get('providerUI')==9
assert health.get('bundleIdentifier')=='com.fengluoxiao.quotacheck' and health.get('appIcon') is True
for folder in ('windows','ios'):
    for line in (assets/folder/'SHA256SUMS.txt').read_text().splitlines():
        expected,name=line.split(maxsplit=1);name=name.strip().lstrip('*')
        assert Path(name).name==name
        assert hashlib.sha256((assets/folder/name).read_bytes()).hexdigest()==expected
ios_names=['QuotaCheck-ios-unsigned.ipa','QuotaCheck-ios-simulator-arm64.app.zip','ios-simulator.png','native-health.json','SHA256SUMS.txt']
for name in ios_names:assert (assets/'ios'/name).is_file()
body='''新增 GLM 加油包、Claude 重置次数与额外消费、MiMo 近七天日用量与日账单、方舟个人订阅到期查询。Windows WinUI 3 和原生 SwiftUI iOS 同步支持。

- iOS 恢复原 Bundle ID com.fengluoxiao.quotacheck、原应用图标与“额度查询”名称；加入旧 Expo 本机加密配置的已知 Keychain 别名迁移。覆盖安装仍需相同签名身份。

- 按用户要求移除 GLM 重置卡查询，保留套餐 Key 的普通额度查询。
- 卡片上的附加按钮按需读取，不兑换重置卡、不购买或续费、不调用模型；明细支持展开/收起。
- GLM 国内站点需要额外的网页控制台 Authorization，和套餐 Key 分开加密保存。导入连接继续隐藏凭据，禁止再次导出。
- Claude 重置查询为账号条件开放的 OAuth 权益；没有返回字段时明确提示，不显示虚构零值。额外消费保留接口计费单位，不当作钱包余额。
- MiMo 日用量/账单使用普通 API Key；Token Plan 专属 Key 不通用。方舟订阅读取需要 ListSubscribeTrade 权限。
- MiMo 套餐增加档位、自动续费及 Claw 状态（接口返回时），余额增加授信额度。
- 加密协议、附加查询解析及原生启动验证通过；没有使用用户真实供应商凭据，测试样例不作为产品额度。
'''
proof='\n构建：https://github.com/'+repo+'/actions/runs/'+os.environ['GITHUB_RUN_ID']+'\n提交：'+sha
for suffix,folder,names,preview in [('', 'windows',[windows['exe'],'README-Windows.txt','windows-verification.json','SHA256SUMS.txt'],False),('-ios-native','ios',ios_names,True)]:
    tag='v'+version+suffix
    existing=subprocess.run(['gh','release','view',tag,'--repo',repo,'--json','targetCommitish'],capture_output=True,text=True)
    if existing.returncode==0:
        ref=json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/git/ref/tags/{tag}'],text=True))
        assert ref['object']['sha']==sha,'Existing release targets another commit'
        raise RuntimeError('Release already exists; verify assets explicitly before modifying it')
    note=body+proof
    if preview:note+='\n\nIPA 未签名，安装真机前需 Apple 签名。模拟器使用受保护的本地测试密钥存储，不代表真机 Keychain 已验证。最低 iOS 17。'
    path=assets/(folder+'-notes.md');path.write_text(note,encoding='utf-8')
    command=['gh','release','create',tag,'--repo',repo,'--target',sha,'--title','v'+version+(' iOS Native Preview' if preview else ' · 多服务附加权益查询'),'--notes-file',str(path)]
    command+=['--prerelease','--latest=false'] if preview else ['--latest']
    command+=[str(assets/folder/name) for name in names]
    subprocess.run(command,check=True)
