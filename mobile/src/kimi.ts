// Schema verified against MoonshotAI/kimi-cli src/kimi_cli/ui/shell/usage.py.
import { AccountCard, KimiProfile, UsageWindow, isRecord, formatTime, validateKey } from './models';
import { APIError, Transport } from './api';
export const KIMI_ENDPOINT = 'https://api.kimi.com/coding/v1/usages';
function amount(value: unknown): number | null {
  if (
    (typeof value !== 'string' && typeof value !== 'number') ||
    (typeof value === 'string' && !value.trim())
  )
    return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? n : null;
}
function display(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
}
function reset(data: Record<string, unknown>): string {
  for (const k of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
    const value = data[k];
    if (value !== undefined && value !== null && value !== '')
      return formatTime(value) || String(value).slice(0, 160);
  }
  for (const k of ['reset_in', 'resetIn', 'ttl']) {
    const value = amount(data[k]);
    if (value !== null) return '接口返回：' + display(value) + ' 秒后重置';
  }
  return '';
}
function label(
  item: Record<string, unknown>,
  detail: Record<string, unknown>,
  index: number,
): string {
  for (const k of ['name', 'title', 'scope']) {
    const value = item[k] || detail[k];
    if (typeof value === 'string' && value.trim()) return value.slice(0, 160);
  }
  const window = isRecord(item.window) ? item.window : {};
  const duration = amount(window.duration ?? item.duration ?? detail.duration);
  const unit = window.timeUnit ?? item.timeUnit ?? detail.timeUnit;
  const names: Record<string, string> = {
    TIME_UNIT_MINUTE: '分钟',
    TIME_UNIT_HOUR: '小时',
    TIME_UNIT_DAY: '天',
    TIME_UNIT_WEEK: '周',
    TIME_UNIT_MONTH: '月',
    TIME_UNIT_SECOND: '秒',
  };
  if (duration !== null && duration > 0 && typeof unit === 'string') {
    if (unit === 'TIME_UNIT_MINUTE' && duration % 60 === 0)
      return display(duration / 60) + ' 小时额度';
    if (names[unit]) return display(duration) + ' ' + names[unit] + '额度';
  }
  return '周期额度 #' + (index + 1);
}
export function kimiWindows(payload: unknown): UsageWindow[] {
  if (!isRecord(payload)) throw new Error('Kimi 接口返回格式异常。');
  const rows: { data: Record<string, unknown>; title: string }[] = [];
  if (isRecord(payload.usage)) rows.push({ data: payload.usage, title: '周额度' });
  const limits = payload.limits === undefined ? [] : payload.limits;
  if (!Array.isArray(limits)) throw new Error('Kimi 周期额度格式异常。');
  for (const [index, item] of limits.entries()) {
    if (!isRecord(item)) throw new Error('Kimi 周期额度格式异常。');
    const detail = item.detail === undefined ? item : item.detail;
    if (!isRecord(detail)) throw new Error('Kimi 周期额度格式异常。');
    rows.push({ data: detail, title: label(item, detail, index) });
  }
  const result: UsageWindow[] = [];
  for (const { data, title } of rows) {
    const total = amount(data.limit);
    let used = amount(data.used),
      remaining = amount(data.remaining);
    if (used === null && total !== null && remaining !== null && remaining <= total)
      used = total - remaining;
    if (remaining === null && total !== null && used !== null)
      remaining = Math.max(0, total - used);
    if (total === null && used === null && remaining === null) continue;
    const percent =
      total !== null && total > 0 && used !== null ? Math.min(100, (100 * used) / total) : null;
    const detail: string[] = [];
    if (used !== null) detail.push('已用 ' + display(used));
    if (total !== null) detail.push('总计 ' + display(total));
    if (remaining !== null) detail.push('剩余 ' + display(remaining));
    result.push({
      title: String(data.name || data.title || title).slice(0, 160),
      used: percent,
      remaining: percent === null ? null : 100 - percent,
      reset: reset(data),
      detail: detail.join(' · ') || '接口未提供具体额度。',
    });
  }
  if (!result.length) throw new Error('Kimi 未返回可用的套餐额度，请使用 Kimi Coding Plan Key。');
  return result;
}
export async function queryKIMI(
  profile: KimiProfile,
  transport: Transport,
): Promise<AccountCard[]> {
  const response = await transport({
    url: KIMI_ENDPOINT,
    method: 'GET',
    headers: { Authorization: 'Bearer ' + validateKey(profile.key), Accept: 'application/json' },
  });
  if (response.status < 200 || response.status >= 300) {
    const errors: Record<number, string> = {
      401: 'Kimi Key 无效或已失效，请使用 Coding Plan Key。',
      403: 'Kimi 查询权限不足，请检查 Coding Plan 套餐状态。',
      404: 'Kimi 用量接口不可用，请确认套餐类型。',
      429: 'Kimi 查询过于频繁，请稍后重试。',
    };
    throw new APIError(
      errors[response.status] || 'Kimi 查询失败（HTTP ' + response.status + '）。',
      response.status,
    );
  }
  if (response.body.length > 2_000_000) throw new Error('Kimi 接口响应过大。');
  let payload: unknown;
  try {
    payload = JSON.parse(response.body);
  } catch {
    throw new Error('Kimi 接口未返回有效 JSON。');
  }
  return kimiWindows(payload).map((w, i) => ({
    id: 'kimi-' + i,
    title: 'Kimi · ' + w.title,
    subtitle: 'Kimi Coding Plan',
    windows: [w],
  }));
}
