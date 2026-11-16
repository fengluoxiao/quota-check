const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export function toBase64(bytes: Uint8Array): string {
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i]!,
      b = bytes[i + 1],
      c = bytes[i + 2];
    const n = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out +=
      alphabet[(n >>> 18) & 63]! +
      alphabet[(n >>> 12) & 63]! +
      (b === undefined ? '=' : alphabet[(n >>> 6) & 63]!) +
      (c === undefined ? '=' : alphabet[n & 63]!);
  }
  return out;
}
export function fromBase64(value: string): Uint8Array {
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value))
    throw new Error('文件编码无效。');
  const out: number[] = [];
  for (let i = 0; i < value.length; i += 4) {
    const a = alphabet.indexOf(value[i]!),
      b = alphabet.indexOf(value[i + 1]!),
      c = value[i + 2] === '=' ? 0 : alphabet.indexOf(value[i + 2]!),
      d = value[i + 3] === '=' ? 0 : alphabet.indexOf(value[i + 3]!);
    const n = (a << 18) | (b << 12) | (c << 6) | d;
    out.push((n >>> 16) & 255);
    if (value[i + 2] !== '=') out.push((n >>> 8) & 255);
    if (value[i + 3] !== '=') out.push(n & 255);
  }
  return new Uint8Array(out);
}
export function fileMode(data: Uint8Array): number {
  if (
    data.length < 62 ||
    data.length > 2 * 1024 * 1024 ||
    [83, 81, 86, 65, 85, 76, 84, 0].some((v, i) => data[i] !== v) ||
    data[8] !== 1
  )
    throw new Error('文件格式或版本不受支持。');
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const wrapped = view.getUint32(10),
    size = view.getUint32(42);
  if (size < 16 || wrapped > 16384 || 46 + wrapped + size !== data.length)
    throw new Error('文件已损坏。');
  const mode = data[9]!;
  if (mode === 0) throw new Error('此文件绑定 Windows 用户，请在桌面端另存为跨电脑文件。');
  if (mode !== 1 || wrapped !== 0) throw new Error('请选择跨电脑加密连接文件。');
  return mode;
}
