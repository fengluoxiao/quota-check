import { AccountCard, isRecord, formatTime } from './models';
import { Transport, RequestSpec, APIError } from './api';
import { ServiceId, ServiceProfile, serviceForId, validateService } from './serviceCatalog';
export interface HashFunctions {
  sha256: (value: string) => string;
  hmacSHA256: (keyHex: string, message: string) => string;
}
export interface ProviderWindow {
  title: string;
  used: number | null;
  remaining: number | null;
  details: string;
}
function num(value: unknown, negative = false): number | null {
  if (
    (typeof value !== 'string' && typeof value !== 'number') ||
    (typeof value === 'string' && !value.trim())
  )
    return null;
  const n = Number(value);
  return Number.isFinite(n) && (negative || n >= 0) ? n : null;
}
function fmt(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
}
function win(title: string, p: unknown, reset?: unknown, detail = ''): ProviderWindow | null {
  let percent = num(p);
  if (percent !== null && percent > 100) percent = null;
  if (percent === null && !detail && (reset === undefined || reset === null || reset === ''))
    return null;
  const resetNumber = typeof reset === 'boolean' ? null : num(reset, true);
  const resetText =
    typeof reset !== 'boolean' && (resetNumber === null || resetNumber > 0)
      ? formatTime(reset)
      : '';
  if (percent === null && !detail && !resetText) return null;
  if (resetText) detail += (detail ? '\n' : '') + '重置时间：' + resetText;
  return {
    title: title.slice(0, 200),
    used: percent,
    remaining: percent === null ? null : 100 - percent,
    details: detail || '接口未提供具体次数。',
  };
}
function count(
  title: string,
  used?: unknown,
  total?: unknown,
  left?: unknown,
  reset?: unknown,
  unit = '',
): ProviderWindow | null {
  let u = num(used),
    r = num(left);
  const t = num(total);
  if (u === null && t !== null && r !== null && r <= t) u = t - r;
  if (r === null && u !== null && t !== null) r = Math.max(0, t - u);
  if (u === null && t === null && r === null) return null;
  const detail: string[] = [];
  for (const [label, v] of [
    ['已用', u],
    ['总计', t],
    ['剩余', r],
  ] as const)
    if (v !== null) detail.push(label + ' ' + fmt(v) + (unit ? ' ' + unit : ''));
  return win(
    title,
    t !== null && t > 0 && u !== null ? Math.min(100, (100 * u) / t) : null,
    reset,
    detail.join(' · '),
  );
}
function unwrapAli(payload: unknown): Record<string, unknown> {
  let d = payload;
  for (let i = 0; i < 8; i++) {
    if (!isRecord(d)) throw new Error('阿里控制台响应格式异常。');
    if (
      d.success === false ||
      d.successResponse === false ||
      d.failed === true ||
      (Array.isArray(d.ret) &&
        d.ret.some((v) => typeof v !== 'string' || !v.startsWith('SUCCESS::'))) ||
      (d.errorCode !== undefined &&
        d.errorCode !== null &&
        !['', 0, '0', 200, '200'].includes(d.errorCode as string | number) &&
        d.success !== true &&
        d.successResponse !== true)
    )
      throw new Error('阿里控制台认证失效或查询被拒绝，请更新访问令牌。');
    if (d.DataV2 !== undefined) d = d.DataV2;
    else if (isRecord(d.data)) d = d.data;
    else return d;
  }
  throw new Error('阿里控制台响应嵌套异常。');
}
export function parseProvider(id: ServiceId, payload: unknown, sealed = false): ProviderWindow[] {
  if (!isRecord(payload)) throw new Error('额度响应格式异常。');
  if (
    payload.success === false ||
    payload.succeed === false ||
    payload.failed === true ||
    payload.error ||
    (isRecord(payload.ResponseMetadata) && payload.ResponseMetadata.Error)
  )
    throw new Error('服务拒绝查询，请检查凭据、登录状态或查询权限。');
  const rows: (ProviderWindow | null)[] = [];
  if (id === 'claude') {
    const labels: Record<string, string> = {
      five_hour: '5 小时',
      seven_day: '7 天',
      seven_day_opus: '7 天 · Opus',
      seven_day_sonnet: '7 天 · Sonnet',
      seven_day_oauth_apps: '7 天 · OAuth Apps',
      iguana_necktie: '其他周期',
    };
    for (const [key, label] of Object.entries(labels)) {
      const d = payload[key];
      if (isRecord(d)) rows.push(win('Claude Code · ' + label, d.utilization, d.resets_at));
    }
  } else if (id === 'deepseek' || id === 'mimo_balance') {
    if (!Array.isArray(payload.balance_infos)) throw new Error('接口未返回余额明细。');
    for (const d of payload.balance_infos) {
      if (!isRecord(d)) throw new Error('余额明细格式异常。');
      const currency = String(d.currency ?? '').slice(0, 12);
      const fields =
        id === 'deepseek'
          ? [
              ['总余额', 'total_balance'],
              ['现金余额', 'topped_up_balance'],
              ['赠金余额', 'granted_balance'],
            ]
          : [
              ['账面余额（含冻结）', 'total_available'],
              ['现金余额', 'cash_balance'],
              ['赠金余额', 'gift_balance'],
              ['冻结金额', 'frozen_balance'],
              ['可用授信', 'credit_available'],
            ];
      const lines: string[] = [];
      for (const [label, key] of fields) {
        const n = num(d[key!], true);
        if (n !== null)
          lines.push(
            label +
              ' ' +
              n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) +
              ' ' +
              currency,
          );
      }
      if (lines.length)
        rows.push({
          title: serviceForId(id)!.label + ' · ' + currency,
          used: null,
          remaining: null,
          details: lines.join('\n'),
        });
    }
  } else if (id === 'mimo') {
    if (!isRecord(payload.quota))
      throw new Error('MiMo 未返回套餐积分，请检查是否为 Token Plan Key。');
    const d = payload.quota;
    const row = count(
      'MiMo · 套餐积分',
      d.used_credits,
      d.total_credits,
      d.remaining_credits,
      undefined,
      '积分',
    );
    if (row && isRecord(payload.period) && payload.period.end_at)
      row.details += '\n周期结束（UTC）：' + String(payload.period.end_at).slice(0, 100);
    rows.push(row);
  } else if (id === 'ark_agent') {
    if (!isRecord(payload.Result)) throw new Error('当前身份没有可用的个人版 Agent Plan 数据。');
    for (const [key, label] of [
      ['AFPFiveHour', '5 小时'],
      ['AFPDaily', '近一天'],
      ['AFPWeekly', '近一周'],
      ['AFPMonthly', '近一月'],
    ]) {
      const d = payload.Result[key!];
      if (isRecord(d))
        rows.push(
          count('方舟 Agent Plan · ' + label, d.Used, d.Quota, undefined, d.ResetTime, 'AFP'),
        );
    }
  } else if (id === 'aliyun_token') {
    const d = unwrapAli(payload);
    const groups = new Map<
      string,
      { n: number; u: string; percentage?: unknown; reset?: unknown }
    >();
    for (const [key, value] of Object.entries(d)) {
      const match = /^per(\d+)(Hour|Day|Week|Month)(Percentage|ResetTime)$/.exec(key);
      if (!match) continue;
      const group = match[1] + match[2]!;
      const data = groups.get(group) ?? { n: Number(match[1]), u: match[2]! };
      if (match[3] === 'Percentage') data.percentage = value;
      else data.reset = value;
      groups.set(group, data);
    }
    const units: Record<string, string> = { Hour: '小时', Day: '天', Week: '周', Month: '月' };
    const hours: Record<string, number> = { Hour: 1, Day: 24, Week: 168, Month: 720 };
    for (const d of [...groups.values()].sort((a, b) => a.n * hours[a.u]! - b.n * hours[b.u]!)) {
      const ratio = num(d.percentage);
      rows.push(
        win(
          '阿里 Token Plan · ' + d.n + ' ' + units[d.u],
          ratio !== null && ratio <= 1 ? 100 * ratio : null,
          d.reset,
        ),
      );
    }
  } else if (id === 'aliyun_coding') {
    const d = unwrapAli(payload);
    if (!Array.isArray(d.codingPlanInstanceInfos))
      throw new Error('阿里未返回 Coding Plan 套餐列表。');
    for (const item of d.codingPlanInstanceInfos) {
      if (!isRecord(item) || item.status !== 'VALID' || !isRecord(item.codingPlanQuotaInfo))
        continue;
      const q = item.codingPlanQuotaInfo;
      for (const [key, label] of [
        ['per5Hour', '5 小时'],
        ['perWeek', '每周'],
        ['perBillMonth', '账单月'],
      ])
        rows.push(
          count(
            '阿里 Coding Plan · ' + label,
            q[key + 'UsedQuota'],
            q[key + 'TotalQuota'],
            undefined,
            q[key + 'QuotaNextRefreshTime'],
          ),
        );
    }
  } else {
    if (payload.code !== 0) throw new Error('讯飞会话已失效或请求被拒绝，请更新登录 Cookie。');
    const items = isRecord(payload.data)
      ? payload.data[id === 'astron' ? 'seats' : 'rows']
      : undefined;
    if (!Array.isArray(items)) throw new Error('讯飞未返回套餐列表。');
    for (const [i, item] of items.entries()) {
      if (!isRecord(item)) throw new Error('讯飞套餐格式异常。');
      const ident = String(item.id ?? i + 1).slice(0, 50);
      if (id === 'astron') {
        const title = sealed
          ? 'Astron · 席位 #' + ident
          : String(item.name || item.seatTypeName || '席位 #' + ident).slice(0, 120);
        const q = item.usage;
        if (!isRecord(q)) {
          rows.push({ title, used: null, remaining: null, details: '该席位尚无积分用量数据。' });
          continue;
        }
        rows.push(
          count(title, q.usedPoints, q.totalAuthorizedPoints, undefined, undefined, '积分'),
        );
      } else {
        if (!isRecord(item.codingPlanUsageDTO)) continue;
        const q = item.codingPlanUsageDTO;
        const title = sealed
          ? '星火套餐 #' + ident
          : '星火 · ' + String(item.name || '套餐 #' + ident).slice(0, 120);
        for (const [prefix, label] of [
          ['rp5h', '5 小时'],
          ['rpw', '每周'],
          ['package', '套餐总量'],
        ]) {
          const row = count(
            title + ' · ' + label,
            q[prefix + 'Usage'],
            q[prefix + 'Limit'],
            prefix === 'package' ? q.packageLeft : undefined,
          );
          if (row && item.expiresAt)
            row.details += '\n套餐到期：' + String(item.expiresAt).slice(0, 100);
          rows.push(row);
        }
      }
    }
  }
  const result = rows.filter((r): r is ProviderWindow => r !== null);
  if (!result.length)
    throw new Error('接口未返回可展示的额度或余额，请检查套餐状态；未生成模拟数据。');
  return result;
}
export function signVolc(
  profile: ServiceProfile,
  hash: HashFunctions,
  stamp: string,
): Record<string, string> {
  if (!/^\d{8}T\d{6}Z$/.test(stamp)) throw new Error('签名时间格式无效。');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Host: 'ark.cn-beijing.volcengineapi.com',
    'X-Date': stamp,
    'X-Content-Sha256': hash.sha256('{}'),
  };
  if (profile.session_token) headers['X-Security-Token'] = profile.session_token;
  const lower: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) lower[k.toLowerCase()] = v;
  const keys = Object.keys(lower).sort(),
    names = keys.join(';');
  const canonical = [
    'POST',
    '/',
    'Action=GetAFPUsage&Version=2024-01-01',
    keys.map((k) => k + ':' + lower[k] + '\n').join(''),
    names,
    headers['X-Content-Sha256'],
  ].join('\n');
  const scope = stamp.slice(0, 8) + '/cn-beijing/ark/request';
  const message = ['HMAC-SHA256', stamp, scope, hash.sha256(canonical)].join('\n');
  let key = Array.from(profile.secret2!, (c) => c.charCodeAt(0).toString(16).padStart(2, '0')).join(
    '',
  );
  for (const part of [stamp.slice(0, 8), 'cn-beijing', 'ark', 'request'])
    key = hash.hmacSHA256(key, part);
  headers.Authorization =
    'HMAC-SHA256 Credential=' +
    profile.secret +
    '/' +
    scope +
    ', SignedHeaders=' +
    names +
    ', Signature=' +
    hash.hmacSHA256(key, message);
  return headers;
}
export function serviceRequest(
  id: ServiceId,
  record: ServiceProfile,
  page = 0,
  hash?: HashFunctions,
  timestamp?: string,
): RequestSpec {
  const p = validateService(id, record),
    spec = serviceForId(id)!;
  const headers: Record<string, string> = { Accept: 'application/json' };
  const urls: Partial<Record<ServiceId, string>> = {
    claude: 'https://api.anthropic.com/api/oauth/usage',
    deepseek: 'https://api.deepseek.com/user/balance',
    mimo: 'https://token-plan-cn.xiaomimimo.com/v1/platform/token_plan',
    mimo_balance: 'https://api.xiaomimimo.com/v1/platform/balance',
  };
  if (urls[id]) {
    headers.Authorization = 'Bearer ' + p.secret;
    if (id === 'claude') headers['anthropic-beta'] = 'oauth-2025-04-20';
    return { url: urls[id]!, method: 'GET', headers };
  }
  if (spec.auth === 'ali') {
    const api =
      id === 'aliyun_token'
        ? 'zeldaHttp.apikeyMgr./tokenplan/personal/api/v2/usage'
        : 'zeldaEasy.broadscope-bailian.codingPlan.queryCodingPlanInstanceInfoV2';
    const data: Record<string, unknown> =
      id === 'aliyun_token'
        ? {}
        : {
            queryCodingPlanInstanceInfoRequest: {
              commodityCode: 'sfm_codingplan_public_cn',
              onlyLatestOne: true,
            },
          };
    data.cornerstoneParam = {
      protocol: 'V2',
      console: 'ONE_CONSOLE',
      productCode: 'p_efm',
      switchUserType: 3,
      consoleSite: 'BAILIAN_ALIYUN',
    };
    headers.Authorization = 'Bearer ' + p.secret;
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    const query = new URLSearchParams({
      action: 'BroadScopeAspnGateway',
      product: 'sfm_bailian',
      api,
    });
    const body = new URLSearchParams({
      params: JSON.stringify({ Api: api, V: '1.0', Data: data }),
      region: 'cn-beijing',
    }).toString();
    return {
      url: 'https://bailian-cs.console.aliyun.com/cli/api.json?' + query,
      method: 'POST',
      headers,
      body,
    };
  }
  if (id === 'ark_agent') {
    if (!hash) throw new Error('原生签名模块不可用。');
    const stamp =
      timestamp ??
      new Date()
        .toISOString()
        .replace(/[-:]/g, '')
        .replace(/\.\d{3}Z$/, 'Z');
    return {
      url: 'https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01',
      method: 'POST',
      headers: { ...headers, ...signVolc(p, hash, stamp) },
      body: '{}',
    };
  }
  if (!Number.isInteger(page) || page < 0 || page >= 100) throw new Error('分页超限。');
  const route =
    id === 'astron'
      ? 'token-plan/seats?page=' + page + '&size=100'
      : 'coding-plan/list?page=' + (page + 1) + '&size=100';
  headers.Cookie = p.secret;
  headers.Referer =
    'https://maas.xfyun.cn/' + (id === 'astron' ? 'tokenPlan' : 'packageSubscription');
  if (p.secret2) headers.Authorization = p.secret2;
  return { url: 'https://maas.xfyun.cn/api/v1/gpt-finetune/' + route, method: 'GET', headers };
}
export async function queryService(
  id: ServiceId,
  profile: ServiceProfile,
  transport: Transport,
  hash?: HashFunctions,
): Promise<AccountCard[]> {
  const cards: AccountCard[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < 100; page++) {
    const response = await transport(serviceRequest(id, profile, page, hash));
    if (response.status < 200 || response.status >= 300)
      throw new APIError(
        [401, 403].includes(response.status)
          ? '认证失效或没有查询权限，请检查该服务要求的凭据类型。'
          : response.status === 429
            ? '查询过于频繁，请稍后重试。'
            : '额度查询失败（HTTP ' + response.status + '）。',
        response.status,
      );
    if (response.body.length > 2_000_000) throw new Error('接口响应过大。');
    let payload: unknown;
    try {
      payload = JSON.parse(response.body);
    } catch {
      throw new Error('服务未返回有效 JSON。');
    }
    if (
      page &&
      isRecord(payload) &&
      payload.code === 0 &&
      isRecord(payload.data) &&
      Array.isArray(payload.data[id === 'astron' ? 'seats' : 'rows']) &&
      (payload.data[id === 'astron' ? 'seats' : 'rows'] as unknown[]).length === 0
    )
      return cards;
    const windows = parseProvider(id, payload, profile.sealed);
    windows.forEach((w, i) =>
      cards.push({
        id: id + '-' + page + '-' + i,
        title: w.title,
        subtitle: serviceForId(id)!.kind === 'balance' ? '账户余额' : serviceForId(id)!.label,
        kind: serviceForId(id)!.kind,
        windows: [
          {
            title: serviceForId(id)!.kind === 'balance' ? '余额明细' : '额度',
            used: w.used,
            remaining: w.remaining,
            detail: w.details,
            reset: '',
          },
        ],
      }),
    );
    if (id !== 'spark' && id !== 'astron') return cards;
    const data = (payload as { data: Record<string, unknown> }).data;
    const items = data[id === 'astron' ? 'seats' : 'rows'] as Record<string, unknown>[];
    const mark = JSON.stringify(items.map((i, index) => i.id ?? index));
    if (seen.has(mark)) throw new Error('后台未正确响应分页，已停止以避免重复。');
    seen.add(mark);
    const total = num(data.total ?? data.totalCount);
    if (items.length < 100 || (total !== null && (page + 1) * 100 >= total)) return cards;
  }
  throw new Error('后台数据超过分页上限，未返回截断后的结果。');
}
