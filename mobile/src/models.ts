export type Provider = 0 | 1;
export interface GlmProfile {
  site: 'cn' | 'global';
  key: string;
  sealed: boolean;
}
export interface PanelUser {
  id?: number;
  email?: string;
  username?: string;
  role?: string;
}
export interface SubProfile {
  url: string;
  email: string;
  password?: string;
  access_token?: string;
  refresh_token?: string;
  user?: PanelUser;
  cached?: boolean;
  sealed: boolean;
}
export interface NewProfile {
  url: string;
  username: string;
  password: string;
  sealed: boolean;
}
export interface VaultData {
  version: 1;
  source: Provider;
  profiles: { glm?: GlmProfile; sub2api?: SubProfile; newapi?: NewProfile };
}
export interface Account {
  id: number;
  name: string;
  platform?: string;
  type?: string;
  status?: string;
}
export interface UsageWindow {
  title: string;
  used: number | null;
  remaining: number | null;
  reset: string;
  detail: string;
}
export interface AccountCard {
  id: string;
  title: string;
  subtitle: string;
  windows: UsageWindow[];
  error?: string;
  cached?: boolean;
}
export type Json = Record<string, unknown>;
export const freshVault = (): VaultData => ({ version: 1, source: 0, profiles: {} });
export const isRecord = (v: unknown): v is Json =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
export function numeric(v: unknown): number | null {
  if (typeof v === 'boolean' || v === null || v === '' || v === undefined) return null;
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}
export function normalizeURL(value: string): string {
  const s = value.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(s) || /[\s\u0000-\u001f]/.test(s))
    throw new Error('请输入完整的 HTTPS 或 HTTP 站点地址。');
  let u: URL;
  try {
    u = new URL(s);
  } catch {
    throw new Error('站点地址无效。');
  }
  if (!u.hostname || u.username || u.password || u.search || u.hash)
    throw new Error('站点地址不能包含账号、密码或查询参数。');
  return s.replace(/\/api(?:\/v1)?$/, '');
}
export function validateKey(input: string): string {
  const value = input.trim().replace(/^Bearer\s+/i, '');
  if (!value || /[^\x21-\x7e]/.test(value)) throw new Error('请输入有效的 Key，不能含空格或换行。');
  return value;
}
function checkedString(v: unknown, field: string): string {
  if (typeof v !== 'string' || v.length > 32768) throw new Error('连接字段格式无效：' + field);
  return v;
}
export function validateVault(value: unknown): VaultData {
  if (!isRecord(value) || value.version !== 1 || !isRecord(value.profiles))
    throw new Error('连接文件格式不受支持。');
  const out = freshVault();
  out.source = value.source === 1 ? 1 : 0;
  for (const [name, raw] of Object.entries(value.profiles)) {
    if (!isRecord(raw)) throw new Error('连接信息格式无效。');
    const allowed: Record<string, string[]> = {
      glm: ['site', 'key', 'sealed'],
      sub2api: [
        'url',
        'email',
        'password',
        'access_token',
        'refresh_token',
        'user',
        'sealed',
        'cached',
      ],
      newapi: ['url', 'username', 'password', 'sealed'],
    };
    if (!allowed[name] || Object.keys(raw).some((k) => !allowed[name]!.includes(k)))
      throw new Error('连接文件包含不支持的字段。');
    if (raw.sealed !== undefined && typeof raw.sealed !== 'boolean')
      throw new Error('连接保护标记无效。');
    if (name === 'glm') {
      if (raw.site !== 'cn' && raw.site !== 'global') throw new Error('GLM 站点无效。');
      out.profiles.glm = {
        site: raw.site,
        key: validateKey(checkedString(raw.key, 'key')),
        sealed: raw.sealed === true,
      };
    } else if (name === 'sub2api') {
      const p: SubProfile = {
        url: normalizeURL(checkedString(raw.url, 'url')),
        email: checkedString(raw.email, 'email'),
        sealed: raw.sealed === true,
      };
      for (const k of ['password', 'access_token', 'refresh_token'] as const)
        if (raw[k] !== undefined) p[k] = checkedString(raw[k], k);
      if (!p.email || !(p.password || p.refresh_token)) throw new Error('sub2api 连接信息不完整。');
      if (raw.cached !== undefined && typeof raw.cached !== 'boolean')
        throw new Error('读取方式无效。');
      p.cached = raw.cached === true;
      if (raw.user !== undefined) {
        if (
          !isRecord(raw.user) ||
          Object.keys(raw.user).some((k) => !['id', 'email', 'username', 'role'].includes(k))
        )
          throw new Error('登录会话格式无效。');
        p.user = {};
        if (raw.user.id !== undefined && raw.user.id !== null) {
          if (typeof raw.user.id !== 'number') throw new Error('登录用户 ID 无效。');
          p.user.id = raw.user.id;
        }
        for (const k of ['email', 'username', 'role'] as const)
          if (raw.user[k] !== undefined && raw.user[k] !== null)
            p.user[k] = checkedString(raw.user[k], k);
      }
      out.profiles.sub2api = p;
    } else if (name === 'newapi') {
      out.profiles.newapi = {
        url: normalizeURL(checkedString(raw.url, 'url')),
        username: checkedString(raw.username, 'username'),
        password: checkedString(raw.password, 'password'),
        sealed: raw.sealed === true,
      };
    }
  }
  return out;
}
export function lockImported(value: unknown): VaultData {
  const v = validateVault(value);
  if (!Object.keys(v.profiles).length) throw new Error('文件中没有连接。');
  for (const p of Object.values(v.profiles)) p.sealed = true;
  return v;
}
export function exportOwned(value: VaultData): VaultData {
  const v = validateVault(value);
  for (const k of ['glm', 'sub2api', 'newapi'] as const)
    if (v.profiles[k]?.sealed) delete v.profiles[k];
  if (!Object.keys(v.profiles).length) throw new Error('导入连接只能查询，不能再次导出。');
  if (v.source === 1 && !v.profiles.sub2api) v.source = 0;
  return v;
}
export function formatTime(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  const n = numeric(value);
  const date = n === null ? new Date(String(value)) : new Date(n > 1e11 ? n : n * 1000);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}
function window(title: string, usedRaw: unknown, resetRaw?: unknown, detail = ''): UsageWindow {
  const n = numeric(usedRaw);
  const used = n !== null && n >= 0 ? n : null;
  return {
    title,
    used,
    remaining: used === null ? null : Math.max(0, 100 - used),
    reset: formatTime(resetRaw),
    detail,
  };
}
export function glmWindows(payload: unknown): UsageWindow[] {
  if (!isRecord(payload)) throw new Error('GLM 返回格式异常。');
  if (
    payload.success === false ||
    (payload.code !== undefined && ![0, 200, '0', '200'].includes(payload.code as number))
  )
    throw new Error('GLM 拒绝查询，请检查 Key 和套餐状态。');
  const d = isRecord(payload.data) ? payload.data : payload;
  if (!Array.isArray(d.limits)) throw new Error('没有返回套餐额度，请确认使用 Coding Plan Key。');
  return d.limits.filter(isRecord).map((item) => {
    const type = String(item.type ?? '额度');
    const unit = numeric(item.unit);
    const count = numeric(item.number);
    let label =
      type === 'TIME_LIMIT'
        ? '工具额度'
        : ['TOKENS_LIMIT', 'CREDIT_LIMIT'].includes(type)
          ? '模型额度'
          : type;
    if (unit === 6) label += ' · 每周';
    else if (unit === 3 && count) label += ' · ' + count + ' 小时';
    else if (unit === 5) label += ' · 每月';
    const used = numeric(item.currentValue),
      total = numeric(item.usage);
    const detail =
      used !== null && total !== null && used >= 0 && used <= total
        ? '已用 ' +
          used.toLocaleString() +
          ' / 总计 ' +
          total.toLocaleString() +
          ' · 剩余 ' +
          (total - used).toLocaleString()
        : '';
    const p = numeric(item.percentage);
    return window(
      label,
      p !== null && p <= 100 ? p : null,
      item.nextResetTime ?? item.resetTime ?? item.resetAt ?? item.renewTime,
      detail,
    );
  });
}
export function snapshotWindows(extra: Json): UsageWindow[] {
  const out: UsageWindow[] = [];
  for (const [part, label] of [
    ['5h', '5 小时'],
    ['7d', '7 天'],
  ] as const)
    if (extra['codex_' + part + '_used_percent'] !== undefined)
      out.push(
        window(
          'GPT / Codex · ' + label,
          extra['codex_' + part + '_used_percent'],
          extra['codex_' + part + '_reset_at'],
        ),
      );
  if (!out.length)
    for (const part of ['primary', 'secondary'])
      if (extra['codex_' + part + '_used_percent'] !== undefined) {
        const minutes = numeric(extra['codex_' + part + '_window_minutes']);
        const label =
          minutes === 10080
            ? '7 天'
            : minutes === 300
              ? '5 小时'
              : minutes
                ? minutes + ' 分钟'
                : part === 'primary'
                  ? '主窗口'
                  : '次窗口';
        out.push(
          window(
            'GPT / Codex · ' + label,
            extra['codex_' + part + '_used_percent'],
            extra['codex_' + part + '_reset_at'],
          ),
        );
      }
  return out;
}
export function subWindows(data: Json): UsageWindow[] {
  const out: UsageWindow[] = [];
  const rate = (r: unknown, name: string) => {
    if (!isRecord(r)) return;
    for (const k of ['primary_window', 'secondary_window']) {
      const item = r[k];
      if (!isRecord(item)) continue;
      const seconds = numeric(item.limit_window_seconds ?? item.rate_limit_window_seconds);
      const label =
        seconds === 18000
          ? '5 小时'
          : seconds === 604800
            ? '7 天'
            : seconds
              ? seconds / 3600 + ' 小时'
              : k === 'primary_window'
                ? '主窗口'
                : '次窗口';
      let reset = item.reset_at;
      const fetched = numeric(data.fetched_at),
        after = numeric(item.reset_after_seconds);
      if (!reset && fetched !== null && after !== null) reset = fetched + after;
      out.push(window(name + ' · ' + label, item.used_percent, reset));
    }
  };
  rate(data.rate_limit, 'GPT / Codex');
  if (Array.isArray(data.additional_rate_limits))
    for (const item of data.additional_rate_limits)
      if (isRecord(item))
        rate(item.rate_limit, String(item.limit_name ?? item.metered_feature ?? '附加额度'));
  rate(data.code_review_rate_limit, '代码审查');
  if (!out.length)
    for (const [key, label] of [
      ['five_hour', '5 小时'],
      ['seven_day', '7 天'],
      ['thirty_day', '30 天'],
    ] as const) {
      const item = data[key];
      if (isRecord(item))
        out.push(window('GPT / Codex · ' + label, item.utilization, item.resets_at));
    }
  return out;
}
