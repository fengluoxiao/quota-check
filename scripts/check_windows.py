"""Verify the packaged WinUI app with external development fixtures, never user data."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
exe=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
version=json.loads((root/'mobile/package.json').read_text(encoding='utf-8'))['version']
def launch(args):
    p=subprocess.run([str(exe),*map(str,args)],cwd=root,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if p.returncode:raise RuntimeError('Packaged native check failed')
runtime=out/'runtime-check.json';launch(['--check-runtime',runtime])
report=json.loads(runtime.read_text(encoding='utf-8'));assert report.get('ok') and report.get('frozen')
cases=json.loads((root/'tests/fixtures/providers-usage.json').read_text(encoding='utf-8'));reports=[]
fixture_storage=tempfile.TemporaryDirectory(prefix='quota-native-ui-')
fixture_dir=Path(fixture_storage.name)
for case in cases:
    source=fixture_dir/(case['id']+'.json');target=out/('ui-'+case['id']+'.json')
    extras=json.loads((root/'tests/fixtures/extras-usage.json').read_text(encoding='utf-8'))
    extra_cases=[item for item in extras if item['provider']==case['id']]
    source.write_text(json.dumps({'_provider':case['id'],'quota':case['payload'],'_provider_extras':extra_cases,'_vault_check':True,'file_password':'ci-native-file-test-password','expected_cards':len(case['expect'])}),encoding='utf-8')
    launch(['--check-ui',source,target])
    result=json.loads(target.read_text(encoding='utf-8'))
    assert all(result.get(k) for k in ('ok','frozen','service_controls','file_handlers_verified','credential_fields_empty','import_read_only','reexport_blocked','raw_hidden')),case['id']
    if extra_cases:assert result.get('extra_buttons'),case['id']
    reports.append({'provider':case['id'],'ok':True})
    print('Packaged native UI and encrypted file checks passed:',case['id'],flush=True)
guide=out/'README-Windows.txt'
guide.write_text('Quota Check '+version+'\n\n运行 '+exe.name+'，在查询服务中选择目标服务，按界面填写对应凭据。查询成功后本机加密保存。\n\nClaude Code 需要 OAuth 访问令牌；阿里需要百炼 CLI 控制台 Access Token；方舟 Agent Plan 使用有查询权限的 AK/SK（STS 必须附带 Session Token）；讯飞需要登录 MaaS 官网后的 Cookie。DeepSeek / MiMo API 余额不作为订阅百分比。完整说明见仓库 PROVIDERS.md。\n\n支持 .sqv 加密文件导入导出。导入后隐藏凭据并禁止再次导出，但本地文件和 UI 不能抵抗控制设备的人。\n\n自动检查使用外部开发样例，不是产品额度数据。未持有用户各厂商真实凭据，需填写自己的凭据查询实际账号。\n',encoding='utf-8')
meta={'ok':True,'version':version,'commit':os.environ.get('GITHUB_SHA') or subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'runtime':report,'providers':reports,'exe':exe.name,'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
(out/'windows-verification.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
if exe.parent!=out:
    import shutil
    shutil.copy2(exe,out/exe.name)
names=[exe.name,'README-Windows.txt','windows-verification.json']
(out/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256((out/n).read_bytes()).hexdigest()+'  '+n+'\n' for n in names),encoding='ascii')
