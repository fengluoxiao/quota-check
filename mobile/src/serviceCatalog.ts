import raw from './provider-catalog.json';
export type ServiceId =
  | 'claude'
  | 'aliyun_token'
  | 'aliyun_coding'
  | 'ark_agent'
  | 'mimo'
  | 'spark'
  | 'astron'
  | 'deepseek'
  | 'mimo_balance';
export interface ServiceProfile {
  secret: string;
  secret2?: string;
  session_token?: string;
  sealed: boolean;
}
export interface ServiceSpec {
  source: number;
  id: ServiceId;
  label: string;
  auth: string;
  fields: { key: 'secret' | 'secret2' | 'session_token'; label: string; required: boolean }[];
  help: string;
  kind: 'quota' | 'balance';
}
export const SERVICES = raw as ServiceSpec[];
export function serviceForSource(source: number): ServiceSpec | undefined {
  return SERVICES.find((s) => s.source === source);
}
export function serviceForId(id: string): ServiceSpec | undefined {
  return SERVICES.find((s) => s.id === id);
}
export function headerSecret(value: unknown, required = true): string {
  if (typeof value !== 'string' || value.length > 32768) throw new Error('凭据格式或长度无效。');
  const text = value.trim();
  if (required && !text) throw new Error('请先填写对应的访问凭据。');
  if (/[^\x20-\x7e]/.test(text)) throw new Error('凭据含有换行、控制字符或非英文字符。');
  return text;
}
export function validateService(id: ServiceId, raw: unknown): ServiceProfile {
  const spec = serviceForId(id);
  if (!spec || typeof raw !== 'object' || raw === null || Array.isArray(raw))
    throw new Error('服务连接无效。');
  const data = raw as Record<string, unknown>;
  if (Object.keys(data).some((k) => k !== 'sealed' && !spec.fields.some((f) => f.key === k)))
    throw new Error('服务连接包含不支持的字段。');
  if (data.sealed !== undefined && typeof data.sealed !== 'boolean')
    throw new Error('连接保护标记无效。');
  const out: ServiceProfile = { secret: '', sealed: data.sealed === true };
  for (const f of spec.fields) {
    let value = headerSecret(data[f.key] ?? '', f.required);
    if (value && spec.auth !== 'cookie' && spec.auth !== 'volc') {
      value = value.replace(/^Bearer\s+/i, '').trim();
      if (/\s/.test(value)) throw new Error('访问令牌含有空格。');
    }
    if (value || f.required) out[f.key] = value;
  }
  return out;
}
