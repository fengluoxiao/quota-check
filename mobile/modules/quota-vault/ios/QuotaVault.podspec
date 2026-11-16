require 'json'
package = JSON.parse(File.read(File.join(__dir__, '..', 'package.json')))
Pod::Spec.new do |s|
  s.name = 'QuotaVault'
  s.version = package['version']
  s.summary = 'Native encrypted connection files and redirect-safe HTTP for Quota Check'
  s.description = 'CryptoKit AES-GCM, reference Argon2id and app-private encrypted storage.'
  s.author = 'quota-check contributors'
  s.homepage = 'https://github.com/fengluoxiao/quota-check'
  s.license = { :type => 'Proprietary application integration; Argon2 reference CC0' }
  s.platforms = { :ios => '17.0' }
  s.swift_version = '5.9'
  s.source = { :git => 'https://github.com/fengluoxiao/quota-check.git', :tag => 'v1.3.0' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.source_files = '*.{swift,h,c}', 'vendor/argon2/include/*.h', 'vendor/argon2/src/*.h', 'vendor/argon2/src/{argon2,core,encoding,ref,thread}.c', 'vendor/argon2/src/blake2/{blake2b.c,blake2.h,blake2-impl.h,blamka-round-ref.h}'
  s.public_header_files = 'QuotaVaultC.h'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES', 'GCC_PREPROCESSOR_DEFINITIONS' => '$(inherited) ARGON2_NO_THREADS=1', 'HEADER_SEARCH_PATHS' => '$(inherited) "$(PODS_TARGET_SRCROOT)/vendor/argon2/include" "$(PODS_TARGET_SRCROOT)/vendor/argon2/src"' }
end
