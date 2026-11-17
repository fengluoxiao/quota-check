#!/usr/bin/env bash
set -euo pipefail
mobile_root="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
argon="$mobile_root/modules/quota-vault/ios/vendor/argon2"
sources=("$mobile_root/modules/quota-vault/ios/QuotaVaultC.c" "$argon/src/argon2.c" "$argon/src/core.c" "$argon/src/encoding.c" "$argon/src/ref.c" "$argon/src/thread.c" "$argon/src/blake2/blake2b.c")
objects=()
for index in "${!sources[@]}"; do
  object="$work_dir/argon-$index.o"
  clang -std=c99 -O2 -DARGON2_NO_THREADS=1 -I"$argon/include" -I"$argon/src" -c "${sources[$index]}" -o "$object"
  objects+=("$object")
done
swiftc -swift-version 5 -import-objc-header "$mobile_root/modules/quota-vault/ios/QuotaVaultC.h" "$mobile_root/modules/quota-vault/ios/NativeVaultCodec.swift" "$mobile_root/modules/quota-vault/ios/NativeHashCodec.swift" "$mobile_root/modules/quota-vault/ios/SecureHTTP.swift" "$mobile_root/scripts/CodecMain.swift" "${objects[@]}" -o "$work_dir/codec-check"
python3 -m venv "$work_dir/python"
"$work_dir/python/bin/python" -m pip install --quiet cryptography==50.0.2
"$work_dir/python/bin/python" "$mobile_root/scripts/crypto_interop.py" "$work_dir/codec-check"
