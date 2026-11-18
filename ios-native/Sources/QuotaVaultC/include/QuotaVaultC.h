#ifndef QUOTA_VAULT_C_H
#define QUOTA_VAULT_C_H
#include <stddef.h>
#include <stdint.h>
int qc_argon2id(const uint8_t *password, size_t password_len, const uint8_t *salt, size_t salt_len, uint8_t *output, size_t output_len);
#endif
