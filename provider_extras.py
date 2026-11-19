"""Optional read-only entitlements. Never keep raw responses or redemption handles."""
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
import quota
import service_providers as providers

ACTIONS = {
    'glm': [('reset', '重置卡'), ('boost', '加油包')],
    'claude': [('reset', '重置次数'), ('spend', '额外消费')],
    'mimo_balance': [('daily', '近7天用量'), ('bill', '近7天账单')],
    'ark_agent': [('subscription', '订阅到期')],
}

def date_value(raw):
    if isinstance(raw, bool) or raw in (None, ''): return None
    n = providers.amount(raw, negative=True)
    try:
        if n is not None: return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, timezone.utc)
        value = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError): return None

def time_text(raw):
    value = date_value(raw)
    return value.astimezone().strftime('%Y-%m-%d %H:%M %Z') if value else ''

def result(title, value, lines=(), expanded=()):
    return {'title': title, 'used': None, 'remaining': None, 'value': str(value),
            'details': '\n'.join([str(value), *lines]), 'expanded_details': list(expanded)}

def request_spec(name, action, profile, *, now=None):
    if action not in dict(ACTIONS.get(name, [])): raise quota.QueryError('此服务不支持该查询。')
    headers = {'Accept': 'application/json'}
    if name == 'ark_agent':
        body = json.dumps({'ResourceNames': ['RealAgentPlanPersonal']}, separators=(',', ':'))
        p = providers.validate_profile(name,profile)
        headers.update(providers.sign_volc(p['secret'],p['secret2'],p.get('session_token',''),action='ListSubscribeTrade',body=body))
        return {'url':'https://ark.cn-beijing.volcengineapi.com/?Action=ListSubscribeTrade&Version=2024-01-01','method':'POST','headers':headers,'body':body}
    if name == 'glm':
        if profile.get('site') != 'cn': raise quota.QueryError('当前只核实了国内 GLM 控制台的权益查询接口。')
        token = profile.get('console_token', '')
        if not token: raise quota.QueryError('查询重置卡和加油包需要 GLM 网页控制台 Authorization，请先添加控制台凭据。')
        headers['Authorization'] = providers.header_secret(token)
        route = '/api/biz/customer-package-reset/list?targetType=PERSONAL' if action == 'reset' else '/api/biz/boosterPack/usage/remaining'
        url = 'https://www.bigmodel.cn' + route
    elif name == 'claude':
        headers.update(Authorization='Bearer ' + quota.validate_key(profile.get('secret', '')),
                       **{'anthropic-beta': 'oauth-2025-04-20', 'User-Agent': 'claude-cli/2.1.0 (external, cli)'})
        url = 'https://api.anthropic.com/api/oauth/usage' + ('?cedar_ember=1' if action == 'reset' else '')
    else:
        now = now or datetime.now(timezone(timedelta(hours=8)))
        end = now.astimezone(timezone(timedelta(hours=8))).date()
        query = urllib.parse.urlencode({'start_date': str(end - timedelta(days=6)), 'end_date': str(end)})
        headers['Authorization'] = 'Bearer ' + quota.validate_key(profile.get('secret', ''))
        url = 'https://api.xiaomimimo.com/v1/platform/' + ('usage' if action == 'daily' else 'billing') + '/daily?' + query
    return {'url': url, 'method': 'GET', 'headers': headers}

def parse(name, action, payload, *, now=None):
    if not isinstance(payload, dict): raise quota.QueryError('附加信息响应格式异常。')
    now = now or datetime.now(timezone.utc)
    if name == 'ark_agent':
        data = payload.get('Result')
        if (isinstance(payload.get('ResponseMetadata'),dict) and payload['ResponseMetadata'].get('Error')) or not isinstance(data,dict) or not isinstance(data.get('InfoList'),list):
            raise quota.QueryError('方舟未返回订阅明细，请检查 ListSubscribeTrade 查询权限。')
        rows=[]
        for i,item in enumerate(data['InfoList'],1):
            if not isinstance(item,dict):raise quota.QueryError('方舟订阅格式异常。')
            end=date_value(item.get('EndTime'))
            if end and end.timestamp()<=0:end=None
            rows.append(result('方舟 · 个人订阅 #'+str(i),'已到期' if end and end<=now else ('订阅到期：'+time_text(end.isoformat()) if end else '接口未返回有效到期时间')))
        return rows or [result('方舟 · 个人订阅','接口未返回订阅记录')]
    if name == 'glm':
        if payload.get('success') is not True or payload.get('code') != 200 or not isinstance(payload.get('data'), dict):
            raise quota.QueryError('GLM 控制台会话失效或无查询权限，请更新控制台凭据。')
        data = payload['data']
        if action == 'reset':
            rows = []
            for key, title in [('fiveHourResets', 'GLM · 5 小时重置卡'), ('weekResets', 'GLM · 周重置卡')]:
                grants = data.get(key)
                if not isinstance(grants, list): continue
                if len(grants)>1000 or any(not isinstance(g,dict) or type(g.get('available')) is not bool for g in grants):raise quota.QueryError('GLM 重置卡明细无效。')
                valid = [g for g in grants if isinstance(g, dict) and g.get('available') is True]
                times = sorted(t for g in valid if (t := date_value(g.get('expireTime'))) is not None)
                detail = ['最近到期：' + time_text(times[0].isoformat())] if times else []
                expanded = ['#' + str(i) + ' · ' + ('到期：' + time_text(g.get('expireTime')) if time_text(g.get('expireTime')) else '接口未返回有效到期时间') for i, g in enumerate(valid, 1)]
                rows.append(result(title, str(len(valid)) + ' 次可用', detail, expanded))
            if rows: return rows
        else:
            total, left = providers.amount(data.get('totalMagnitude')), providers.amount(data.get('totalBalance'))
            if total is not None or left is not None:
                lines = []
                if total is not None: lines.append('总额度：' + quota.pretty_number(total))
                if left is not None: lines.append('剩余额度：' + quota.pretty_number(left))
                if time_text(data.get('nearestExpireTime')): lines.append('最近到期：' + time_text(data['nearestExpireTime']))
                return [result('GLM · 加油包', '剩余 ' + quota.pretty_number(left) if left is not None else '接口未返回剩余额度', lines)]
    elif name == 'claude' and action == 'reset':
        data = payload.get('cedar_ember')
        if not isinstance(data, dict) or not isinstance(data.get('eligible'), bool):
            raise quota.QueryError('当前 Claude 账号未返回重置权益，无法确认次数。')
        if not data['eligible']: return [result('Claude · 重置次数', '账号暂无重置资格')]
        grants = data.get('grants')
        if not isinstance(grants, list) or len(grants) > 200: raise quota.QueryError('Claude 重置权益明细无效。')
        dates = []; count = 0
        for grant in grants:
            if not isinstance(grant, dict): raise quota.QueryError('Claude 重置权益明细无效。')
            left = grant.get('resets_left'); total = grant.get('resets_total')
            if type(left) is not int or left < 0 or not isinstance(grant.get('paused'), bool) or (total is not None and (type(total) is not int or total < left)):
                raise quota.QueryError('Claude 重置权益数量无效。')
            start, end = date_value(grant.get('starts_at')), date_value(grant.get('ends_at'))
            for key, date in [('starts_at', start), ('ends_at', end)]:
                if grant.get(key) not in (None, '') and date is None: raise quota.QueryError('Claude 重置权益时间无效。')
            if grant['paused'] or (start and start > now) or (end and end <= now): continue
            count += left
            if count > 1000: raise quota.QueryError('Claude 重置权益数量超限。')
            dates.extend([end] * left)
        dates.sort(key=lambda d: d or datetime.max.replace(tzinfo=timezone.utc))
        lines = ['最近到期：' + time_text(dates[0].isoformat())] if dates and dates[0] else []
        lines.append('持有次数不代表当前可立即兑换。')
        expanded = ['#' + str(i) + ' · ' + ('到期：' + time_text(d.isoformat()) if d else '接口未设置到期时间') for i, d in enumerate(dates, 1)]
        return [result('Claude · 重置次数', str(count) + ' 次可用', lines, expanded)]
    elif name == 'claude':
        data = payload.get('extra_usage')
        if not isinstance(data, dict) or not isinstance(data.get('is_enabled'), bool): raise quota.QueryError('Claude 未返回额外消费信息。')
        lines = []
        for key, label in [('monthly_limit', '月消费上限'), ('used_credits', '已消费额度'), ('utilization', '使用比例')]:
            value = providers.amount(data.get(key))
            if value is not None: lines.append(label + '：' + quota.pretty_number(value) + ('%' if key == 'utilization' else '（接口计费单位）'))
        lines.append('消费上限不是钱包余额；金额单位未确认时保留接口计费单位。')
        return [result('Claude · 额外消费', '已开启' if data['is_enabled'] else '未开启', lines)]
    elif name == 'mimo_balance':
        items = payload.get('data')
        if payload.get('error') or not isinstance(items, list): raise quota.QueryError('MiMo 未返回有效用量或账单明细。')
        expanded = []
        fields = [('consumed_amount', '消费金额'), ('request_count', '请求次数')] if action == 'daily' else [('original_amount', '原价'), ('discount_amount', '折扣减免'), ('gift_amount', '赠金抵扣'), ('final_paid_amount', '实付')]
        for item in items:
            if not isinstance(item, dict): raise quota.QueryError('MiMo 明细格式无效。')
            parts = [str(item.get('date', '日期未返回'))[:32]]
            if action == 'daily' and isinstance(item.get('name'), str): parts.append(item['name'][:160])
            currency = str(item.get('currency', ''))[:12]
            has_value=False
            for key, label in fields:
                value = providers.amount(item.get(key), negative=True)
                if value is not None:
                    has_value=True
                    parts.append(label + ' ' + (format(value, '.6f') if key == 'consumed_amount' else quota.pretty_number(value)) + ((' ' + currency) if key != 'request_count' else ''))
            if not has_value: raise quota.QueryError('MiMo 明细缺少消费数值。')
            expanded.append(' · '.join(parts))
        return [result('MiMo · ' + ('近7天日用量' if action == 'daily' else '近7天日账单'), str(len(items)) + ' 条记录', ['日期范围为北京时间今天及前6天。'], expanded)]
    raise quota.QueryError('接口没有返回可展示的附加信息；未推算数据。')

def fetch(name, action, profile, *, opener=None):
    spec = request_spec(name, action, profile)
    client = opener or urllib.request.build_opener(quota.NoRedirect())
    try:
        request = urllib.request.Request(spec['url'], headers=spec['headers'], method=spec['method'],data=spec['body'].encode() if spec.get('body') is not None else None)
        with client.open(request, timeout=25) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000: raise quota.QueryError('附加信息响应过大。')
            payload = json.loads(body.decode('utf-8-sig'))
        return parse(name, action, payload)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403): raise quota.QueryError('附加查询凭据失效、无权限或该权益未向当前账号开放。') from None
        if exc.code in (400, 404, 405): raise quota.QueryError('该账号或服务版本不支持此附加查询。') from None
        raise quota.QueryError('附加查询失败（HTTP ' + str(exc.code) + '）。') from None
    except (TimeoutError, socket.timeout, urllib.error.URLError): raise quota.QueryError('附加查询连接失败或超时。') from None
    except (ValueError, UnicodeError): raise quota.QueryError('附加查询未返回有效 JSON。') from None
