import {
  Account,
  AccountCard,
  GlmProfile,
  Json,
  PanelUser,
  SubProfile,
  glmWindows,
  isRecord,
  normalizeURL,
  snapshotWindows,
  subWindows,
  validateKey,
  formatTime,
} from './models';
export interface RequestSpec {
  url: string;
  method: 'GET' | 'POST';
  headers: Record<string, string>;
  body?: string;
}
export interface HttpResponse {
  status: number;
  body: string;
}
export type Transport = (request: RequestSpec) => Promise<HttpResponse>;
export class APIError extends Error {
  constructor(
    message: string,
    readonly status = 0,
    readonly reason = '',
  ) {
    super(message);
  }
}
export class NeedsOTP extends Error {}
const errors: Record<string, string> = {
  INVALID_CREDENTIALS: '邮箱或密码不正确。',
  INVALID_PASSWORD: '邮箱或密码不正确。',
  ADMIN_REQUIRED: '需要 sub2api 管理员权限。',
  ADMIN_COMPLIANCE_ACK_REQUIRED: '请先在 sub2api 后台完成部署确认。',
  OPENAI_QUOTA_AUTH_FAILED: '上游 GPT 授权失效，请在 sub2api 后台重新授权。',
  OPENAI_QUOTA_UPSTREAM_ERROR: 'sub2api 查询上游额度失败，请检查账号授权。',
  OPENAI_QUOTA_REQUEST_FAILED: 'sub2api 无法连接上游，请检查服务端代理。',
  CAPTCHA_REQUIRED: '站点需要人机验证，请在设置中填写有效凭据。',
  CAPTCHA_INVALID: '站点人机验证未通过。',
};
export async function queryGLM(p: GlmProfile, transport: Transport): Promise<AccountCard[]> {
  const url =
    p.site === 'global'
      ? 'https://api.z.ai/api/monitor/usage/quota/limit'
      : 'https://open.bigmodel.cn/api/monitor/usage/quota/limit';
  const result = await transport({
    url,
    method: 'GET',
    headers: { Authorization: validateKey(p.key), Accept: 'application/json' },
  });
  if (result.status >= 300)
    throw new APIError(
      result.status === 401
        ? 'GLM Key 无效或已失效。'
        : 'GLM 请求失败（HTTP ' + result.status + '）。',
      result.status,
    );
  let payload: unknown;
  try {
    payload = JSON.parse(result.body);
  } catch {
    throw new Error('GLM 没有返回有效 JSON。');
  }
  return glmWindows(payload).map((w, i) => ({
    id: 'glm-' + i,
    title: w.title,
    subtitle: p.site === 'global' ? 'Z.ai' : '智谱 BigModel',
    windows: [w],
  }));
}
export class SubClient {
  readonly url: string;
  profile: SubProfile;
  pending = '';
  constructor(
    profile: SubProfile,
    private readonly transport: Transport,
  ) {
    this.url = normalizeURL(profile.url);
    this.profile = { ...profile, url: this.url };
  }
  private async once(route: string, body?: Json, auth = true): Promise<unknown> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (auth && this.profile.access_token)
      headers.Authorization = 'Bearer ' + validateKey(this.profile.access_token);
    if (body) headers['Content-Type'] = 'application/json';
    const r = await this.transport({
      url: this.url + '/api/v1' + route,
      method: body ? 'POST' : 'GET',
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.body.length > 8 * 1024 * 1024) throw new Error('后台响应过大。');
    let p: unknown;
    try {
      p = JSON.parse(r.body);
    } catch {
      throw new APIError('后台没有返回有效 JSON，请检查站点地址。', r.status);
    }
    if (!isRecord(p)) throw new Error('后台返回格式异常。');
    if (r.status >= 300 || String(p.code) !== '0') {
      const reason = String(p.reason ?? p.code ?? r.status);
      throw new APIError(
        errors[reason] ??
          {
            401: '后台登录已过期或邮箱密码错误。',
            403: '后台拒绝请求，请检查管理员权限。',
            404: '当前版本没有此接口或账号不存在。',
            429: '请求过于频繁，请稍后再试。',
          }[r.status] ??
          '后台请求失败，请检查账号和站点配置。',
        r.status,
        reason,
      );
    }
    return p.data;
  }
  private accept(data: unknown, requireUser = true): void {
    if (!isRecord(data) || typeof data.access_token !== 'string')
      throw new Error('登录响应缺少访问令牌。');
    this.profile.access_token = validateKey(data.access_token);
    if (typeof data.refresh_token === 'string')
      this.profile.refresh_token = validateKey(data.refresh_token);
    if (requireUser) {
      if (!isRecord(data.user) || data.user.role !== 'admin') {
        delete this.profile.access_token;
        delete this.profile.refresh_token;
        throw new Error('读取 GPT 账号额度需要 sub2api 管理员。');
      }
      this.profile.user = {
        id: typeof data.user.id === 'number' ? data.user.id : undefined,
        email: typeof data.user.email === 'string' ? data.user.email : undefined,
        role: 'admin',
      } satisfies PanelUser;
    }
    this.pending = '';
  }
  async login(code = '', captcha = '', force = false): Promise<void> {
    if (this.pending) {
      if (!/^\d{6}$/.test(code)) throw new NeedsOTP('请输入 6 位登录验证码。');
      this.accept(
        await this.once('/auth/login/2fa', { temp_token: this.pending, totp_code: code }, false),
      );
      return;
    }
    if (!force && this.profile.access_token && this.profile.user?.role === 'admin') return;
    if (!this.profile.email || !this.profile.password)
      throw new Error('保存的会话失效，请由连接所有者更新登录信息。');
    const body: Json = { email: this.profile.email.trim(), password: this.profile.password };
    if (captcha) body.turnstile_token = captcha;
    const data = await this.once('/auth/login', body, false);
    if (isRecord(data) && data.requires_2fa) {
      if (typeof data.temp_token !== 'string') throw new Error('缺少临时验证凭据。');
      this.pending = data.temp_token;
      delete this.profile.access_token;
      delete this.profile.refresh_token;
      if (code) {
        await this.login(code, captcha);
        return;
      }
      throw new NeedsOTP('该账号需要 2FA，请填写验证码后再次查询。');
    }
    this.accept(data);
  }
  async request(route: string): Promise<unknown> {
    try {
      return await this.once(route);
    } catch (e) {
      if (
        !(e instanceof APIError) ||
        e.status !== 401 ||
        !this.profile.refresh_token ||
        e.reason.startsWith('OPENAI_')
      )
        throw e;
      const data = await this.once(
        '/auth/refresh',
        { refresh_token: this.profile.refresh_token },
        false,
      );
      this.accept(data, false);
      return this.once(route);
    }
  }
  async accounts(): Promise<Account[]> {
    const rows: Account[] = [];
    const seen = new Set<number>();
    let processed = 0;
    for (let page = 1; page <= 100; page++) {
      const d = await this.request(
        '/admin/accounts?page=' + page + '&page_size=100&platform=openai&type=oauth',
      );
      if (!isRecord(d) || !Array.isArray(d.items)) throw new Error('账号列表格式异常。');
      processed += d.items.length;
      for (const row of d.items)
        if (
          isRecord(row) &&
          typeof row.id === 'number' &&
          row.id > 0 &&
          !seen.has(row.id) &&
          (row.platform ?? 'openai') === 'openai' &&
          (row.type ?? 'oauth') === 'oauth'
        ) {
          seen.add(row.id);
          rows.push({
            id: row.id,
            name: String(row.name ?? ''),
            status: typeof row.status === 'string' ? row.status : undefined,
          });
        }
      if (
        !d.items.length ||
        (typeof d.total === 'number' ? processed >= d.total : d.items.length < 100)
      )
        break;
    }
    return rows;
  }
  async card(account: Account, cached = false): Promise<AccountCard> {
    const title = this.profile.sealed
      ? 'GPT 账号 #' + account.id
      : account.name || 'GPT 账号 #' + account.id;
    if (!cached) {
      try {
        const data = await this.request('/admin/openai/accounts/' + account.id + '/quota');
        if (!isRecord(data)) throw new Error('额度响应格式异常。');
        return {
          id: String(account.id),
          title,
          subtitle: [String(data.plan_type ?? ''), '实时额度', formatTime(data.fetched_at)]
            .filter(Boolean)
            .join(' · '),
          windows: subWindows(data),
        };
      } catch (e) {
        if (!(e instanceof APIError) || ![404, 405, 501].includes(e.status)) throw e;
      }
    }
    const accountData = await this.request('/admin/accounts/' + account.id);
    if (!isRecord(accountData) || !isRecord(accountData.extra))
      throw new Error('后台没有可用额度快照。');
    const windows = snapshotWindows(accountData.extra);
    if (!windows.length) throw new Error('后台还没有该账号的额度快照。');
    return {
      id: String(account.id),
      title,
      subtitle: ['后台快照', formatTime(accountData.extra.codex_usage_updated_at)]
        .filter(Boolean)
        .join(' · '),
      windows,
      cached: true,
    };
  }
}
export async function queryAll(
  client: SubClient,
  onCard: (card: AccountCard) => void,
): Promise<AccountCard[]> {
  let accounts: Account[];
  try {
    accounts = await client.accounts();
  } catch (e) {
    if (!(e instanceof APIError) || e.status !== 401) throw e;
    await client.login('', '', true);
    accounts = await client.accounts();
  }
  const out: AccountCard[] = [];
  for (const a of accounts) {
    let card: AccountCard;
    try {
      card = await client.card(a, client.profile.cached === true);
    } catch (e) {
      card = {
        id: String(a.id),
        title: client.profile.sealed ? 'GPT 账号 #' + a.id : a.name || 'GPT 账号 #' + a.id,
        subtitle: '读取失败',
        windows: [],
        error: e instanceof Error ? e.message : '读取失败，请检查后台。',
      };
    }
    out.push(card);
    onCard(card);
  }
  return out;
}
