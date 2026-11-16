import test from 'node:test';
import assert from 'node:assert/strict';
import {
  exportOwned,
  freshVault,
  glmWindows,
  lockImported,
  normalizeURL,
  numeric,
  snapshotWindows,
  subWindows,
  validateVault,
} from '../src/models';
import { fromBase64, toBase64, fileMode } from '../src/encoding';
test('GLM counts, periods and zero usage are preserved', () => {
  const w = glmWindows({
    code: 200,
    data: {
      limits: [
        { type: 'TOKENS_LIMIT', unit: 3, number: 5, percentage: 0, currentValue: 0, usage: 28000 },
        { type: 'TOKENS_LIMIT', unit: 6, percentage: 98 },
      ],
    },
  });
  assert.equal(w[0]?.remaining, 100);
  assert.match(w[0]!.title, /5 小时/);
  assert.match(w[1]!.title, /每周/);
  assert.equal(w[1]?.remaining, 2);
});
test('GLM business errors and missing quota are rejected', () => {
  assert.throws(() => glmWindows({ code: 401, data: { limits: [] } }));
  assert.throws(() => glmWindows({ data: {} }));
});
test('Invalid numeric percentages never become unused quota', () => {
  for (const v of [null, undefined, true, 'NaN', {}, '']) assert.equal(numeric(v), null);
  const w = subWindows({ rate_limit: { primary_window: { used_percent: null } } });
  assert.equal(w[0]?.remaining, null);
});
test('GPT uses the actual primary period, including weekly free accounts', () => {
  const w = subWindows({
    fetched_at: 1794830400,
    rate_limit: {
      primary_window: { used_percent: 75, limit_window_seconds: 604800, reset_after_seconds: 3600 },
    },
  });
  assert.match(w[0]!.title, /7 天/);
  assert.equal(w[0]?.remaining, 25);
  assert.ok(w[0]?.reset);
});
test('Additional model windows and over-100 percentages are supported', () => {
  const w = subWindows({
    rate_limit: { primary_window: { used_percent: 110, limit_window_seconds: 18000 } },
    additional_rate_limits: [
      {
        limit_name: 'Spark',
        rate_limit: { primary_window: { used_percent: 12, limit_window_seconds: 18000 } },
      },
    ],
  });
  assert.equal(w[0]?.used, 110);
  assert.equal(w[0]?.remaining, 0);
  assert.match(w[1]!.title, /Spark/);
});
test('Legacy snapshots map primary duration, canonical fields win', () => {
  assert.match(
    snapshotWindows({ codex_primary_used_percent: 20, codex_primary_window_minutes: 10080 })[0]!
      .title,
    /7 天/,
  );
  assert.equal(
    snapshotWindows({ codex_5h_used_percent: 0, codex_primary_used_percent: 90 })[0]?.remaining,
    100,
  );
});
test('URL normalization preserves deployments under a subpath', () => {
  assert.equal(normalizeURL(' https://example.test/panel/api/v1/ '), 'https://example.test/panel');
  for (const v of [
    'example.test',
    'file:///x',
    'https://u:p@example.test',
    'https://example.test?q=x',
    'https://example.test/#x',
    'https://example.test/\napi',
  ])
    assert.throws(() => normalizeURL(v));
});
test('Imported credentials are sealed and cannot be re-exported', () => {
  const p = validateVault({
    version: 1,
    source: 0,
    profiles: { glm: { site: 'cn', key: 'test-key', sealed: false } },
  });
  const locked = lockImported(p);
  assert.equal(locked.profiles.glm?.sealed, true);
  assert.equal(p.profiles.glm?.sealed, false);
  assert.throws(() => exportOwned(locked));
});
test('Mixed export excludes sealed connections', () => {
  const p = freshVault();
  p.profiles.glm = { site: 'cn', key: 'test-key', sealed: false };
  p.profiles.sub2api = {
    url: 'https://example.test',
    email: 'test@example.test',
    password: 'test-only',
    sealed: true,
  };
  assert.equal(exportOwned(p).profiles.sub2api, undefined);
});
test('Unknown credential fields and invalid schema are rejected', () => {
  assert.throws(() =>
    validateVault({
      version: 1,
      profiles: { glm: { site: 'cn', key: 'test-key', execute: 'bad' } },
    }),
  );
  assert.throws(() =>
    validateVault({
      version: 1,
      profiles: { sub2api: { url: 'https://u:p@example.test', email: 'a', password: 'b' } },
    }),
  );
});
test('Binary encoding round-trips exact bytes', () => {
  for (let n = 0; n < 80; n++) {
    const b = Uint8Array.from({ length: n }, (_, i) => (i * 39) % 256);
    assert.deepEqual(fromBase64(toBase64(b)), b);
    assert.equal(toBase64(b), Buffer.from(b).toString('base64'));
  }
  assert.throws(() => fromBase64('invalid!'));
});
test('File header rejects Windows-bound files and malformed lengths', () => {
  const b = new Uint8Array(62);
  b.set([83, 81, 86, 65, 85, 76, 84, 0, 1, 1]);
  new DataView(b.buffer).setUint32(42, 16);
  assert.equal(fileMode(b), 1);
  b[9] = 0;
  assert.throws(() => fileMode(b), /Windows/);
  b[9] = 1;
  new DataView(b.buffer).setUint32(42, 17);
  assert.throws(() => fileMode(b));
});
