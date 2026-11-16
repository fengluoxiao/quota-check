import { requireNativeModule } from 'expo-modules-core';
export interface QuotaVaultModule {
  generateKey(): string;
  seal(plaintext: string, mode: number, secret: string): Promise<string>;
  open(blob: string, secret: string): Promise<string>;
  readStorage(): string | null;
  writeStorage(blob: string): Promise<void>;
  deleteStorage(): Promise<void>;
  request(
    url: string,
    method: string,
    headers: Record<string, string>,
    body: string | null,
  ): Promise<{ status: number; body: string }>;
}
export default requireNativeModule<QuotaVaultModule>('QuotaVault');
