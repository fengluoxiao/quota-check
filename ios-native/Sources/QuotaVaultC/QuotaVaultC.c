#include "QuotaVaultC.h"
#include "vendor/argon2/include/argon2.h"
int qc_argon2id(const uint8_t *password, size_t password_len, const uint8_t *salt, size_t salt_len, uint8_t *output, size_t output_len) {
  return argon2id_hash_raw(3, 65536, 4, password, password_len, salt, salt_len, output, output_len);
}
