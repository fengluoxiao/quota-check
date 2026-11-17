"""Publish only artifacts verified by this exact CI run; never reads provider credentials."""
import hashlib,json,os,sys,time,urllib.request,urllib.error,urllib.parse
from pathlib import Path
root=Path(__file__).resolve().parents[1];assets=Path(sys.argv[1]).resolve();sha=os.environ['GITHUB_SHA']
assert os.environ['GITHUB_REF']=='refs/heads/main'
repo=os.environ['GITHUB_REPOSITORY'];api='https://api.github.com/repos/'+repo
version=json.loads((root/'mobile/package.json').read_text())['version']
windows=json.loads((assets/'windows/windows-verification.json').read_text(encoding='utf-8'))
health=json.loads((assets/'ios/native-health.json').read_text())
assert windows['ok'] and windows['commit']==sha and windows['version']==version
assert all(health.get(k) is True for k in ('ok','keychain','crypto','storage','signing'))
assert len(windows['providers'])==9 and all(x['ok'] for x in windows['providers'])
assert health.get('providerUI')==9
def verify(folder):
    for line in (folder/'SHA256SUMS.txt').read_text().splitlines():
        expected,name=line.split(maxsplit=1);name=name.strip().lstrip('*');assert Path(name).name==name
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==expected
verify(assets/'windows');verify(assets/'ios')
headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'quota-check-release','X-GitHub-Api-Version':'2022-11-28'}
def call(url,method='GET',data=None,ctype='application/json'):
    h=dict(headers)
    if data is not None:h['Content-Type']=ctype
    raw=json.dumps(data,ensure_ascii=False).encode() if isinstance(data,dict) else data
    with urllib.request.urlopen(urllib.request.Request(url,data=raw,headers=h,method=method),timeout=240) as response:
        body=response.read();return json.loads(body) if body else None
common='''新增 Claude Code、阿里 Token Plan / Coding Plan、方舟 Agent Plan 个人版、MiMo Token Plan / API 余额、讯飞星火 Coding Plan、Astron Token Plan、DeepSeek API 余额，保留 GLM、Kimi 和 sub2api 全部账号查询。

- Windows WinUI 3 与 Expo / React Native iOS 同步支持；无 WebView。
- 不调用模型，不模拟额度；余额与订阅窗口分开，未知用量不补成 100% 剩余。
- 每家独立加密保存凭据，支持跨端 .sqv；导入后隐藏凭据、禁止再次导出。Astron 逐席位读取并过滤响应中的 Key / Secret。
- 认证方式不同：Claude 使用 OAuth；阿里使用国内百炼 CLI 控制台 Access Token；方舟使用有 GetAFPUsage 权限的 AK/SK，STS 需保留 Session Token；讯飞使用 MaaS 官网登录 Cookie。控制台 / OAuth 会话可能过期，模型 API Key 不能替代这些凭据。详见仓库 PROVIDERS.md。
- Windows 协议测试与打包后所有服务的原生界面、文件流程检查通过；macOS 27 / iOS 27 编译和模拟器启动、Keychain、CryptoKit 签名、加密文件互通检查通过。
- 未持有用户各厂商真实凭据，未声称已验证某个实际账号的额度；开发样例不作为产品数据。'''
proof='\n\n构建：https://github.com/'+repo+'/actions/runs/'+os.environ['GITHUB_RUN_ID']+'\n提交：'+sha
plans=[{'tag':'v'+version,'name':'v'+version+' — 多服务订阅额度与余额','preview':False,'folder':'windows','files':[windows['exe'],'SHA256SUMS.txt','README-Windows.txt','windows-verification.json'],'body':common+'\n\nWindows x64：下载 EXE 后选择服务，按提示填写对应凭据。'+proof},
{'tag':'v'+version+'-ios-preview','name':'v'+version+' iOS Preview — 多服务额度','preview':True,'folder':'ios','files':[p.name for p in (assets/'ios').glob('*.ipa')]+['QuotaCheck-ios-simulator-arm64.app.zip','ios-simulator.png','native-health.json','SHA256SUMS.txt'],'body':common+'\n\niPhone/iPad IPA 需要 Apple 签名后才能安装。默认构建为未签名包；模拟器包用于 Apple Silicon Mac / iOS 27。最低部署目标 iOS 17。Android 仅有源代码，尚未打包验证。New API 渠道管理仍在 Windows。'+proof}]
records=[]
for plan in plans:
    releases=call(api+'/releases?per_page=50');release=next((r for r in releases if r['tag_name']==plan['tag']),None)
    if release is None:release=call(api+'/releases','POST',{'tag_name':plan['tag'],'target_commitish':sha,'name':plan['name'],'body':plan['body'],'draft':True,'prerelease':plan['preview'],'make_latest':'false'})
    else:
        assert release['prerelease']==plan['preview']
        if not release['draft']:
            ref=call(api+'/git/ref/tags/'+plan['tag']);assert ref['object']['sha']==sha,'Existing release targets another commit'
    for name in plan['files']:
        blob=(assets/plan['folder']/name).read_bytes();digest='sha256:'+hashlib.sha256(blob).hexdigest()
        for attempt in range(3):
            existing=next((a for a in call(release['assets_url']) if a['name']==name),None)
            if existing and existing['state']!='uploaded' and existing['size']==0:
                call(api+'/releases/assets/'+str(existing['id']),'DELETE');existing=None
            if existing:
                assert existing['state']=='uploaded' and existing['size']==len(blob) and (not existing.get('digest') or existing['digest']==digest),'Existing release asset differs'
                asset=existing;break
            try:
                asset=call(release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':name}),'POST',blob,'application/octet-stream')
                assert asset['name']==name and asset['state']=='uploaded' and asset['size']==len(blob)
                if asset.get('digest'):assert asset['digest']==digest
                break
            except (urllib.error.URLError,TimeoutError):
                if attempt==2:raise
                time.sleep(5)
        print('Verified release asset:',plan['tag'],name,len(blob),flush=True)
    result=call(api+'/releases/'+str(release['id']),'PATCH',{'body':plan['body'],'draft':False,'prerelease':plan['preview'],'make_latest':'false' if plan['preview'] else 'true'})
    records.append({'tag':plan['tag'],'release':result['html_url'],'commit':sha})
assert call(api+'/releases/latest')['tag_name']=='v'+version
(assets/'publication.json').write_text(json.dumps({'releases':records},indent=2),encoding='utf-8')
print('Published verified Windows stable and iOS preview releases.',flush=True)
