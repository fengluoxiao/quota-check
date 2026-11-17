"""Read-only quota/balance integrations. Provider authentication targets are pinned.
Vendor docs and console source references are recorded in PROVIDERS.md.
"""
from __future__ import annotations
import hashlib,hmac,json,re,socket,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
import quota
CATALOG=json.loads((Path(__file__).parent/'mobile/src/provider-catalog.json').read_text(encoding='utf-8'))
BY_ID={p['id']:p for p in CATALOG}
BY_SOURCE={p['source']:p for p in CATALOG}
MAX_BYTES=2_000_000

def header_secret(value,required=True):
    if not isinstance(value,str) or len(value)>32768:raise quota.QueryError('凭据格式或长度无效。')
    value=value.strip()
    if required and not value:raise quota.QueryError('请先填写对应的访问凭据。')
    if any(ord(c)<32 or ord(c)>126 for c in value):raise quota.QueryError('凭据含有换行、控制字符或非英文字符。')
    return value

def validate_profile(name,record):
    spec=BY_ID.get(name)
    if not spec or not isinstance(record,dict):raise quota.QueryError('不支持的服务连接。')
    allowed={f['key'] for f in spec['fields']}|{'sealed'}
    if set(record)-allowed:raise quota.QueryError('服务连接包含不支持的字段。')
    if 'sealed' in record and not isinstance(record['sealed'],bool):raise quota.QueryError('连接保护标记无效。')
    out={'sealed':record.get('sealed') is True}
    for f in spec['fields']:
        value=header_secret(record.get(f['key'],''),f['required'])
        if value and spec['auth'] not in ('cookie','volc'):value=quota.validate_key(value)
        if value or f['required']:out[f['key']]=value
    return out

def sign_volc(ak,sk,session_token='',*,timestamp=None):
    ak=header_secret(ak);sk=header_secret(sk);session_token=header_secret(session_token,False)
    stamp=timestamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z',stamp):raise quota.QueryError('签名时间格式无效。')
    host='ark.cn-beijing.volcengineapi.com';body='{}'
    headers={'Content-Type':'application/json','Host':host,'X-Date':stamp,'X-Content-Sha256':hashlib.sha256(body.encode()).hexdigest()}
    if session_token:headers['X-Security-Token']=session_token
    lower={k.lower():v for k,v in headers.items()};names=';'.join(sorted(lower))
    canonical='\n'.join(['POST','/','Action=GetAFPUsage&Version=2024-01-01',''.join(k+':'+lower[k]+'\n' for k in sorted(lower)),names,headers['X-Content-Sha256']])
    scope=stamp[:8]+'/cn-beijing/ark/request'
    message='\n'.join(['HMAC-SHA256',stamp,scope,hashlib.sha256(canonical.encode()).hexdigest()])
    key=sk.encode()
    for part in (stamp[:8],'cn-beijing','ark','request'):key=hmac.new(key,part.encode(),hashlib.sha256).digest()
    signature=hmac.new(key,message.encode(),hashlib.sha256).hexdigest()
    headers['Authorization']='HMAC-SHA256 Credential='+ak+'/'+scope+', SignedHeaders='+names+', Signature='+signature
    return headers

def request_spec(name,record,*,page=0,timestamp=None):
    p=validate_profile(name,record);spec=BY_ID[name]
    headers={'Accept':'application/json'};method='GET';body=None
    urls={'claude':'https://api.anthropic.com/api/oauth/usage','deepseek':'https://api.deepseek.com/user/balance','mimo':'https://token-plan-cn.xiaomimimo.com/v1/platform/token_plan','mimo_balance':'https://api.xiaomimimo.com/v1/platform/balance'}
    if name in urls:
        url=urls[name];headers['Authorization']='Bearer '+p['secret']
        if name=='claude':headers['anthropic-beta']='oauth-2025-04-20'
    elif spec['auth']=='ali':
        api='zeldaHttp.apikeyMgr./tokenplan/personal/api/v2/usage' if name=='aliyun_token' else 'zeldaEasy.broadscope-bailian.codingPlan.queryCodingPlanInstanceInfoV2'
        data={} if name=='aliyun_token' else {'queryCodingPlanInstanceInfoRequest':{'commodityCode':'sfm_codingplan_public_cn','onlyLatestOne':True}}
        data['cornerstoneParam']={'protocol':'V2','console':'ONE_CONSOLE','productCode':'p_efm','switchUserType':3,'consoleSite':'BAILIAN_ALIYUN'}
        params={'Api':api,'V':'1.0','Data':data}
        url='https://bailian-cs.console.aliyun.com/cli/api.json?'+urllib.parse.urlencode({'action':'BroadScopeAspnGateway','product':'sfm_bailian','api':api})
        method='POST';body=urllib.parse.urlencode({'params':json.dumps(params,separators=(',',':')),'region':'cn-beijing'})
        headers.update({'Authorization':'Bearer '+p['secret'],'Content-Type':'application/x-www-form-urlencoded'})
    elif name=='ark_agent':
        url='https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01';method='POST';body='{}'
        headers.update(sign_volc(p['secret'],p['secret2'],p.get('session_token',''),timestamp=timestamp))
    else:
        if not 0<=page<100:raise quota.QueryError('分页超限。')
        route='token-plan/seats?page='+str(page)+'&size=100' if name=='astron' else 'coding-plan/list?page='+str(page+1)+'&size=100'
        url='https://maas.xfyun.cn/api/v1/gpt-finetune/'+route
        headers.update({'Cookie':p['secret'],'Referer':'https://maas.xfyun.cn/'+('tokenPlan' if name=='astron' else 'packageSubscription')})
        if p.get('secret2'):headers['Authorization']=p['secret2']
    return {'url':url,'method':method,'headers':headers,'body':body}

def amount(value,*,negative=False):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)) or (isinstance(value,str) and not value.strip()):return None
    try:n=quota.number(value)
    except OverflowError:return None
    return n if n is not None and (negative or n>=0) else None

def count_window(title,used=None,total=None,left=None,reset=None,unit=''):
    u,t,r=map(amount,(used,total,left))
    if u is None and t is not None and r is not None and r<=t:u=t-r
    if r is None and u is not None and t is not None:r=max(0,t-u)
    if u is None and t is None and r is None:return None
    percent=min(100,100*u/t) if t and u is not None else None
    parts=[]
    for label,value in [('已用',u),('总计',t),('剩余',r)]:
        if value is not None:parts.append(label+' '+quota.pretty_number(value)+((' '+unit) if unit else ''))
    return window(title,percent,reset,' · '.join(parts))

def window(title,percent,reset=None,detail=''):
    percent=amount(percent)
    if percent is not None and percent>100:percent=None
    if percent is None and not detail and (reset is None or reset==''):return None
    reset_num=quota.number(reset) if isinstance(reset,(str,int,float)) and not isinstance(reset,bool) else None
    if isinstance(reset,bool) or (reset_num is not None and reset_num<=0):reset=None
    if percent is None and not detail and (reset is None or reset==''):return None
    if reset is not None and reset!='':detail+=('\n' if detail else '')+'重置时间：'+quota.format_reset(reset)
    return {'title':str(title)[:200],'used':percent,'remaining':100-percent if percent is not None else None,'details':detail or '接口未提供具体次数。'}

def unwrap_ali(payload):
    data=payload
    for _ in range(8):
        if not isinstance(data,dict):raise quota.QueryError('阿里控制台响应格式异常。')
        if data.get('success') is False or data.get('successResponse') is False or data.get('failed') is True or (data.get('errorCode') not in (None,'',0,'0',200,'200') and data.get('success') is not True and data.get('successResponse') is not True) or (isinstance(data.get('ret'),list) and any(not isinstance(v,str) or not v.startswith('SUCCESS::') for v in data['ret'])):raise quota.QueryError('阿里控制台认证失效或查询被拒绝，请更新控制台访问令牌。')
        if 'DataV2' in data:data=data['DataV2']
        elif isinstance(data.get('data'),dict):data=data['data']
        else:return data
    raise quota.QueryError('阿里控制台响应嵌套异常。')

def parse_usage(name,payload,*,sealed=False):
    if name not in BY_ID or not isinstance(payload,dict):raise quota.QueryError('额度响应格式异常。')
    if payload.get('success') is False or payload.get('succeed') is False or payload.get('failed') is True or payload.get('error') or (isinstance(payload.get('ResponseMetadata'),dict) and payload['ResponseMetadata'].get('Error')):
        raise quota.QueryError('服务拒绝查询，请检查凭据、登录状态或查询权限。')
    rows=[]
    if name=='claude':
        labels={'five_hour':'5 小时','seven_day':'7 天','seven_day_opus':'7 天 · Opus','seven_day_sonnet':'7 天 · Sonnet','seven_day_oauth_apps':'7 天 · OAuth Apps','iguana_necktie':'其他周期'}
        for key,label in labels.items():
            data=payload.get(key)
            if isinstance(data,dict):rows.append(window('Claude Code · '+label,data.get('utilization'),data.get('resets_at')))
    elif name in ('deepseek','mimo_balance'):
        balances=payload.get('balance_infos')
        if not isinstance(balances,list):raise quota.QueryError('接口未返回余额明细。')
        for i,data in enumerate(balances):
            if not isinstance(data,dict):raise quota.QueryError('余额明细格式异常。')
            currency=data.get('currency','')
            if currency not in ('CNY','USD','EUR','HKD'):currency=str(currency)[:12]
            fields=[('总余额','total_balance'),('现金余额','topped_up_balance'),('赠金余额','granted_balance')] if name=='deepseek' else [('账面余额（含冻结）','total_available'),('现金余额','cash_balance'),('赠金余额','gift_balance'),('冻结金额','frozen_balance'),('可用授信','credit_available')]
            parts=[]
            for label,key in fields:
                number=amount(data.get(key),negative=True)
                if number is not None:parts.append(label+' '+format(number,',.2f')+' '+currency)
            if parts:rows.append({'title':BY_ID[name]['label']+' · '+currency,'used':None,'remaining':None,'details':'\n'.join(parts)})
    elif name=='mimo':
        data=payload.get('quota');period=payload.get('period')
        if not isinstance(data,dict):raise quota.QueryError('MiMo 未返回套餐积分，请检查是否为 Token Plan Key。')
        rows.append(count_window('MiMo · 套餐积分',data.get('used_credits'),data.get('total_credits'),data.get('remaining_credits'),None,'积分'))
        if rows[-1] and isinstance(period,dict) and period.get('end_at'):rows[-1]['details']+='\n周期结束（UTC）：'+str(period['end_at'])[:100]
    elif name=='ark_agent':
        data=payload.get('Result')
        if not isinstance(data,dict):raise quota.QueryError('当前身份没有可用的个人版 Agent Plan 数据。')
        for key,label in [('AFPFiveHour','5 小时'),('AFPDaily','近一天'),('AFPWeekly','近一周'),('AFPMonthly','近一月')]:
            w=data.get(key)
            if isinstance(w,dict):rows.append(count_window('方舟 Agent Plan · '+label,w.get('Used'),w.get('Quota'),reset=w.get('ResetTime'),unit='AFP'))
    elif name=='aliyun_token':
        data=unwrap_ali(payload);windows={}
        for key,value in data.items():
            match=re.fullmatch(r'per(\d+)(Hour|Day|Week|Month)(Percentage|ResetTime)',key)
            if match:windows.setdefault((int(match[1]),match[2]),{})[match[3]]=value
        units={'Hour':'小时','Day':'天','Week':'周','Month':'月'}
        for (count,unit),data in sorted(windows.items(),key=lambda x:x[0][0]*{'Hour':1,'Day':24,'Week':168,'Month':720}[x[0][1]]):
            ratio=amount(data.get('Percentage'));rows.append(window('阿里 Token Plan · '+str(count)+' '+units[unit],ratio*100 if ratio is not None and ratio<=1 else None,data.get('ResetTime')))
    elif name=='aliyun_coding':
        data=unwrap_ali(payload);instances=data.get('codingPlanInstanceInfos')
        if not isinstance(instances,list):raise quota.QueryError('阿里未返回 Coding Plan 套餐列表。')
        for i,item in enumerate(instances):
            if not isinstance(item,dict) or item.get('status')!='VALID':continue
            data=item.get('codingPlanQuotaInfo')
            if not isinstance(data,dict):continue
            for key,label in [('per5Hour','5 小时'),('perWeek','每周'),('perBillMonth','账单月')]:rows.append(count_window('阿里 Coding Plan · '+label,data.get(key+'UsedQuota'),data.get(key+'TotalQuota'),reset=data.get(key+'QuotaNextRefreshTime')))
    elif name in ('spark','astron'):
        if payload.get('code')!=0:raise quota.QueryError('讯飞会话已失效或请求被拒绝，请更新登录 Cookie。')
        data=payload.get('data');items=data.get('seats' if name=='astron' else 'rows') if isinstance(data,dict) else None
        if not isinstance(items,list):raise quota.QueryError('讯飞未返回套餐列表。')
        for index,item in enumerate(items):
            if not isinstance(item,dict):raise quota.QueryError('讯飞套餐格式异常。')
            ident=str(item.get('id',index+1))[:50]
            if name=='astron':
                title='Astron · 席位 #'+ident if sealed else str(item.get('name') or item.get('seatTypeName') or ('席位 #'+ident))[:120]
                usage=item.get('usage')
                if not isinstance(usage,dict):
                    rows.append({'title':title,'used':None,'remaining':None,'details':'该席位尚无积分用量数据。'});continue
                rows.append(count_window(title,usage.get('usedPoints'),usage.get('totalAuthorizedPoints'),unit='积分'))
            else:
                usage=item.get('codingPlanUsageDTO')
                if not isinstance(usage,dict):continue
                title='星火套餐 #'+ident if sealed else '星火 · '+str(item.get('name') or ('套餐 #'+ident))[:120]
                for prefix,label in [('rp5h','5 小时'),('rpw','每周'),('package','套餐总量')]:
                    row=count_window(title+' · '+label,usage.get(prefix+'Usage'),usage.get(prefix+'Limit'),usage.get('packageLeft') if prefix=='package' else None)
                    if row and item.get('expiresAt'):row['details']+='\n套餐到期：'+str(item['expiresAt'])[:100]
                    rows.append(row)
    rows=[r for r in rows if r is not None]
    if not rows:raise quota.QueryError('接口未返回可展示的额度或余额，请检查套餐状态；未生成模拟数据。')
    return rows

def fetch_usage(name,record,*,opener=None):
    profile=validate_profile(name,record);client=opener or urllib.request.build_opener(quota.NoRedirect());result=[];seen=set()
    try:
        for page in range(100):
            spec=request_spec(name,profile,page=page)
            request=urllib.request.Request(spec['url'],headers=spec['headers'],method=spec['method'],data=spec['body'].encode() if spec['body'] is not None else None)
            with client.open(request,timeout=25) as response:
                body=response.read(MAX_BYTES+1)
                if len(body)>MAX_BYTES:raise quota.QueryError('接口响应过大。')
                payload=json.loads(body.decode('utf-8-sig'))
            # Never expose original console JSON: it may include API keys or identity fields.
            if name not in ('spark','astron'):return {'cards':parse_usage(name,payload,sealed=profile['sealed'])}
            data=payload.get('data') if isinstance(payload,dict) else None
            if page and payload.get('code')==0 and isinstance(data,dict) and data.get('seats' if name=='astron' else 'rows')==[]:return {'cards':result}
            rows=parse_usage(name,payload,sealed=profile['sealed']);result.extend(rows)
            data=payload['data'];items=data['seats' if name=='astron' else 'rows'];fingerprint=tuple(str(i.get('id',index)) for index,i in enumerate(items))
            if fingerprint in seen:raise quota.QueryError('后台未正确响应分页，已停止以避免重复。')
            seen.add(fingerprint)
            total=amount(data.get('total',data.get('totalCount')))
            if len(items)<100 or (total is not None and (page+1)*100>=total):return {'cards':result}
        raise quota.QueryError('后台数据超过分页上限，未返回截断后的结果。')
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):raise quota.QueryError('认证失效或没有查询权限，请检查该服务要求的凭据类型。') from None
        if exc.code==429:raise quota.QueryError('查询过于频繁，请稍后重试。') from None
        raise quota.QueryError('额度查询失败（HTTP '+str(exc.code)+'）。') from None
    except (TimeoutError,socket.timeout):raise quota.QueryError('查询超时，请稍后重试。') from None
    except urllib.error.URLError:raise quota.QueryError('无法连接查询服务，请检查网络或系统代理。') from None
    except (ValueError,UnicodeError):raise quota.QueryError('服务未返回有效 JSON。') from None
