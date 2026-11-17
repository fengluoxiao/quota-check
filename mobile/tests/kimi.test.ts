import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { kimiWindows, queryKIMI, KIMI_ENDPOINT } from '../src/kimi';
import { lockImported, exportOwned, validateVault } from '../src/models';
import type { RequestSpec } from '../src/api';
const cases = JSON.parse(
  readFileSync(new URL('../../tests/fixtures/kimi-usage.json', import.meta.url), 'utf8'),
) as {
  name: string;
  payload: unknown;
  expected: {
    title: string;
    used: number | null;
    remaining: number | null;
    parts: string[];
    reset?: boolean;
  }[];
}[];
for (const c of cases)
  test('Kimi ' + c.name, () => {
    const windows = kimiWindows(c.payload);
    assert.equal(windows.length, c.expected.length);
    windows.forEach((w, i) => {
      const e = c.expected[i]!;
      assert.equal(w.title, e.title);
      assert.equal(w.used, e.used);
      assert.equal(w.remaining, e.remaining);
      for (const part of e.parts) assert.ok(w.detail.includes(part));
      if (e.reset) assert.ok(w.reset);
    });
  });
test('Kimi invalid and missing responses cannot look like unused quota', () => {
  for (const p of [
    null,
    [],
    {},
    { error: { message: 'test-secret' } },
    { usage: { used: true } },
    { limits: 'bad' },
    { limits: [null] },
    { limits: [{ detail: [] }] },
  ])
    assert.throws(() => kimiWindows(p));
});
test('Kimi sends exactly one GET to the subscription endpoint with Bearer auth', async () => {
  const calls: RequestSpec[] = [];
  const cards = await queryKIMI({ key: ' Bearer test-key ', sealed: false }, async (r) => {
    calls.push(r);
    return { status: 200, body: JSON.stringify(cases[0]!.payload) };
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0]!.url, KIMI_ENDPOINT);
  assert.equal(calls[0]!.method, 'GET');
  assert.equal(calls[0]!.headers.Authorization, 'Bearer test-key');
  assert.equal(calls[0]!.body, undefined);
  assert.equal(cards.length, 2);
  assert.equal(cards[0]!.title, 'Kimi · 周额度');
});
test('Kimi errors never expose the backend response or saved key', async () => {
  for (const status of [301, 401, 403, 404, 429, 500])
    await assert.rejects(
      queryKIMI({ key: 'test-secret', sealed: false }, async () => ({
        status,
        body: 'test-secret',
      })),
      (e) => e instanceof Error && !e.message.includes('test-secret'),
    );
  for (const body of ['invalid-json', 'x'.repeat(2_000_001)])
    await assert.rejects(
      queryKIMI({ key: 'test-key', sealed: false }, async () => ({ status: 200, body })),
    );
});
test('Kimi portable profiles remain source 2, hide imported keys and reject re-export', () => {
  const v = validateVault({
    version: 1,
    source: 2,
    profiles: { kimi: { key: 'test-key', sealed: false } },
  });
  assert.equal(v.source, 2);
  assert.equal(exportOwned(v).profiles.kimi!.key, 'test-key');
  const imported = lockImported(v);
  assert.equal(imported.source, 2);
  assert.equal(imported.profiles.kimi!.sealed, true);
  assert.throws(() => exportOwned(imported));
  const mixed = validateVault({
    ...imported,
    profiles: { ...imported.profiles, glm: { site: 'cn', key: 'owned-test-key', sealed: false } },
  });
  const exported = exportOwned(mixed);
  assert.equal(exported.profiles.kimi, undefined);
  assert.equal(exported.source, 0);
});
