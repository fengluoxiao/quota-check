import test from 'node:test';
import assert from 'node:assert/strict';
import {
  APIError,
  NeedsOTP,
  SubClient,
  queryAll,
  queryGLM,
  Transport,
  RequestSpec,
} from '../src/api';
import { subWindows } from '../src/models';
const profile = () => ({
  url: 'https://sub.example.test',
  email: 'admin@example.test',
  password: 'test-password',
  sealed: false,
});
const auth = {
  access_token: 'test-access',
  refresh_token: 'test-refresh',
  user: { id: 1, email: 'admin@example.test', role: 'admin' },
};
function backend(mode = 'live') {
  const calls: RequestSpec[] = [];
  const transport: Transport = async (r) => {
    calls.push(r);
    const u = new URL(r.url);
    const route = u.pathname;
    const data = r.body ? JSON.parse(r.body) : {};
    const ok = (data: unknown) => ({ status: 200, body: JSON.stringify({ code: 0, data }) });
    const fail = (status: number, reason = '') => ({
      status,
      body: JSON.stringify({ code: status, reason, message: 'do not display test-password' }),
    });
    if (route === '/api/v1/auth/login') {
      if (mode === 'bad-login') return fail(401, 'INVALID_CREDENTIALS');
      if (mode === 'otp') return ok({ requires_2fa: true, temp_token: 'test-temp' });
      return ok({ ...auth, user: { ...auth.user, role: mode === 'nonadmin' ? 'user' : 'admin' } });
    }
    if (route === '/api/v1/auth/login/2fa')
      return data.totp_code === '123456' ? ok(auth) : fail(401);
    if (route === '/api/v1/auth/refresh')
      return ok({ access_token: 'new-access', refresh_token: 'new-refresh' });
    if (mode === 'expired' && r.headers.Authorization === 'Bearer test-access')
      return fail(401, 'TOKEN_EXPIRED');
    if (route === '/api/v1/admin/accounts') {
      const page = Number(u.searchParams.get('page'));
      const items =
        mode === 'pages'
          ? [{ id: page, name: 'GPT ' + page }]
          : [
              { id: 20, name: 'GPT One' },
              { id: 21, name: 'GPT Two' },
            ];
      return ok({ items, total: mode === 'pages' ? 2 : 2 });
    }
    if (route.endsWith('/quota/refresh'))
      return ok({
        plan_type: 'plus',
        fetched_at: 1794830400,
        cache_persisted: true,
        credits_cache_persisted: true,
        rate_limit: {
          primary_window: { used_percent: 30, limit_window_seconds: 18000 },
          secondary_window: { used_percent: 70, limit_window_seconds: 604800 },
        },
      });
    if (route.includes('/openai/accounts/') && route.endsWith('/quota')) {
      if (mode === 'old') return fail(404);
      if (mode === 'partial' && route.includes('/21/'))
        return fail(502, 'OPENAI_QUOTA_REQUEST_FAILED');
      if (mode === 'forbidden') return fail(403);
      return ok({
        plan_type: 'plus',
        fetched_at: 1794830400,
        rate_limit: {
          primary_window: { used_percent: 30, limit_window_seconds: 18000 },
          secondary_window: { used_percent: 70, limit_window_seconds: 604800 },
        },
        rate_limit_reset_credits: {
          available_count: 2,
          credits: [{ expires_at: '2026-11-18T00:00:00Z' }],
        },
        credits: { has_credits: true, unlimited: false, balance: '18.40' },
      });
    }
    if (route.startsWith('/api/v1/admin/accounts/'))
      return ok({
        extra:
          mode === 'empty'
            ? {}
            : {
                codex_5h_used_percent: 40,
                codex_7d_used_percent: 80,
                codex_usage_updated_at: '2026-11-16T12:00:00Z',
              },
        credentials: { access_token: 'must-not-export' },
      });
    return fail(404);
  };
  return { calls, transport };
}
test('Login and read-only quota requests use documented endpoints', async () => {
  const b = backend();
  const c = new SubClient(profile(), b.transport);
  await c.login();
  const rows = await c.accounts();
  const card = await c.card(rows[0]!);
  assert.equal(card.windows.length, 2);
  assert.equal(b.calls[0]?.url, 'https://sub.example.test/api/v1/auth/login');
  assert.equal(b.calls.at(-1)?.method, 'GET');
  assert.equal(b.calls.at(-1)?.headers.Authorization, 'Bearer test-access');
  assert.ok(!b.calls.some((r) => r.url.includes('/reset-quota') || r.url.includes('/responses')));
});
test('Card buttons read reset credits and points without consuming reset quota', async () => {
  const b = backend();
  const c = new SubClient(profile(), b.transport);
  await c.login();
  const account = { id: 20, name: 'GPT One' };
  const reset = await c.queryResetCredits(account);
  const credits = await c.queryCredits(account);
  assert.equal(reset.detail.split('\n')[0], '可用重置卡次数：2');
  assert.match(reset.detail, /接口返回到期明细：1 条/);
  assert.match(reset.expandedLines![0] ?? '', /^#1 · 到期：11\/18/);
  assert.equal(reset.expandedTitle, '查看 1 条重置卡明细');
  assert.equal(credits.detail, '点数余额：18.40');
  const quotaCalls = b.calls.filter((r) => r.url.endsWith('/quota'));
  assert.equal(quotaCalls.length, 2);
  assert.ok(quotaCalls.every((r) => r.method === 'GET'));
  const refreshed = await c.refreshUsage(account);
  assert.equal(subWindows(refreshed).length, 2);
  const refresh = b.calls.at(-1)!;
  assert.equal(refresh.method, 'POST');
  assert.ok(refresh.url.endsWith('/quota/refresh'));
  assert.ok(!b.calls.some((r) => r.url.includes('/reset-quota')));
});
test('All accounts produce one card, with independent failures', async () => {
  const b = backend('partial');
  const c = new SubClient(profile(), b.transport);
  await c.login();
  const events: string[] = [];
  const cards = await queryAll(c, (x) => events.push(x.id));
  assert.equal(cards.length, 2);
  assert.equal(cards[0]?.error, undefined);
  assert.ok(cards[1]?.error);
  assert.deepEqual(events, ['20', '21']);
});
test('Restored encrypted session avoids repeating password login', async () => {
  const b = backend();
  const c = new SubClient({ ...profile(), ...auth }, b.transport);
  await c.login();
  await queryAll(c, () => {});
  assert.ok(!b.calls.some((r) => r.url.endsWith('/auth/login')));
});
test('Sealed cards do not expose upstream account labels', async () => {
  const b = backend();
  const c = new SubClient({ ...profile(), sealed: true }, b.transport);
  await c.login();
  const cards = await queryAll(c, () => {});
  assert.equal(cards[0]?.title, 'GPT 账号 #20');
});
test('Expired panel access token rotates its refresh token once', async () => {
  const b = backend('expired');
  const c = new SubClient(profile(), b.transport);
  await c.login();
  await c.accounts();
  assert.equal(c.profile.access_token, 'new-access');
  assert.equal(c.profile.refresh_token, 'new-refresh');
  assert.equal(b.calls.filter((r) => r.url.endsWith('/auth/refresh')).length, 1);
});
test('Optional 2FA login can be continued without re-entering password', async () => {
  const b = backend('otp');
  const c = new SubClient(profile(), b.transport);
  await assert.rejects(c.login(), NeedsOTP);
  await c.login('123456');
  assert.equal(c.profile.access_token, 'test-access');
  assert.equal(b.calls.filter((r) => r.url.endsWith('/auth/login')).length, 1);
});
test('Non-admin login is rejected and server error text is not leaked', async () => {
  const b = backend('nonadmin');
  await assert.rejects(new SubClient(profile(), b.transport).login(), /管理员/);
  const bad = backend('bad-login');
  await assert.rejects(
    new SubClient(profile(), bad.transport).login(),
    (e) => e instanceof Error && !e.message.includes('test-password'),
  );
});
test('Old versions fall back to marked snapshots', async () => {
  const b = backend('old');
  const c = new SubClient(profile(), b.transport);
  await c.login();
  const cards = await queryAll(c, () => {});
  assert.equal(cards[0]?.cached, true);
  assert.equal(cards[0]?.windows[0]?.remaining, 60);
});
test('Permission errors do not silently become old cache results', async () => {
  const b = backend('forbidden');
  const c = new SubClient(profile(), b.transport);
  await c.login();
  await assert.rejects(c.card({ id: 20, name: 'GPT' }), APIError);
  assert.ok(!b.calls.some((r) => r.url.endsWith('/admin/accounts/20')));
});
test('Explicit cache mode never calls live quota', async () => {
  const b = backend();
  const c = new SubClient(profile(), b.transport);
  await c.login();
  await c.card({ id: 20, name: 'GPT' }, true);
  assert.ok(!b.calls.some((r) => r.url.endsWith('/quota')));
});
test('Account pagination uses actual item counts', async () => {
  const b = backend('pages');
  const c = new SubClient(profile(), b.transport);
  await c.login();
  assert.equal((await c.accounts()).length, 2);
});
test('GLM uses a raw Key and never sends model requests', async () => {
  let call: RequestSpec | undefined;
  const cards = await queryGLM({ site: 'cn', key: 'test-key', sealed: false }, async (r) => {
    call = r;
    return {
      status: 200,
      body: JSON.stringify({
        code: 200,
        data: { limits: [{ type: 'TOKENS_LIMIT', percentage: 20, unit: 3, number: 5 }] },
      }),
    };
  });
  assert.equal(cards[0]?.windows[0]?.remaining, 80);
  assert.equal(call?.headers.Authorization, 'test-key');
  assert.equal(call?.method, 'GET');
  assert.ok(call?.url.endsWith('/quota/limit'));
});
