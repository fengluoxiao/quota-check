import * as SecureStore from 'expo-secure-store';
import Native from '../modules/quota-vault';
import { VaultData, freshVault, validateVault } from './models';
import type { Transport } from './api';
const KEY = 'quota-check.device-key.v1';
const options: SecureStore.SecureStoreOptions = {
  keychainService: 'com.fengluoxiao.quotacheck.vault',
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};
export const nativeTransport: Transport = (r) =>
  Native.request(r.url, r.method, r.headers, r.body ?? null);
export async function loadVault(): Promise<VaultData> {
  const blob = Native.readStorage();
  if (!blob) return freshVault();
  const key = await SecureStore.getItemAsync(KEY, options);
  if (!key) throw new Error('本机连接密钥不可用，请导入备份或清除本机连接。');
  return validateVault(JSON.parse(await Native.open(blob, key)) as unknown);
}
export async function saveVault(value: VaultData, replace = false): Promise<void> {
  const data = validateVault(value);
  let key = await SecureStore.getItemAsync(KEY, options);
  if (!key) {
    if (Native.readStorage() && !replace)
      throw new Error('本机连接无法解密，请先导入备份或清除连接。');
    key = Native.generateKey();
    await SecureStore.setItemAsync(KEY, key, options);
  }
  const blob = await Native.seal(JSON.stringify(data), 2, key);
  await Native.writeStorage(blob);
}
export async function clearVault(): Promise<void> {
  await Native.deleteStorage();
  await SecureStore.deleteItemAsync(KEY, options);
}
