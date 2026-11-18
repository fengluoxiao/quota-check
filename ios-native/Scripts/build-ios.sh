#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/build"
mkdir -p "$out/Payload/QuotaCheck.app"
mode="${IOS_BUILD_MODE:-simulator}"
build_number="${IOS_BUILD_NUMBER:-1}"
bundle_id="${IOS_BUNDLE_IDENTIFIER:-com.fengluoxiao.quotacheck.native}"
version="${IOS_APP_VERSION:-2.0.0}"

if [[ "$mode" == "simulator" ]]; then
  sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
  target="arm64-apple-ios17.0-simulator"
  binary="$out/QuotaCheck-simulator"
elif [[ "$mode" == "device" ]]; then
  sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
  target="arm64-apple-ios17.0"
  binary="$out/QuotaCheck-device"
else
  printf 'IOS_BUILD_MODE must be simulator or device\n' >&2; exit 2
fi

c_sources=$(find "$root/Sources/QuotaVaultC" -type f -name '*.c' | sort)
swift_sources=$(find "$root/Sources/QuotaCheckCore" "$root/Sources/QuotaCheckApp" -type f -name '*.swift' | sort)
swiftc -parse-as-library -swift-version 5 -O -whole-module-optimization \
  -sdk "$sdk" -target "$target" \
  -I "$root/Sources/QuotaVaultC" \
  -I "$root/Sources/QuotaVaultC/include" \
  -I "$root/Sources/QuotaVaultC/vendor/argon2/include" \
  $c_sources $swift_sources \
  -o "$binary"

app="$out/Payload/QuotaCheck.app"
rm -rf "$app"; mkdir -p "$app"
cp "$binary" "$app/QuotaCheck"
printf 'APPL????' > "$app/PkgInfo"
/usr/libexec/PlistBuddy -c 'Clear dict' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleDevelopmentRegion string zh_CN' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleDisplayName string 额度查询' "$app/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleExecutable string QuotaCheck" "$app/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $bundle_id" "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleInfoDictionaryVersion string 6.0' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleName string QuotaCheck' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundlePackageType string APPL' "$app/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $version" "$app/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $build_number" "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :LSRequiresIPhoneOS bool true' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :ITSAppUsesNonExemptEncryption bool true' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :MinimumOSVersion string 17.0' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity dict' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity:NSAllowsArbitraryLoads bool true' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :NSAppTransportSecurity:NSAllowsLocalNetworking bool true' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UILaunchScreen dict' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UIRequiredDeviceCapabilities array' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UIRequiredDeviceCapabilities:0 string arm64' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UISupportedInterfaceOrientations array' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UISupportedInterfaceOrientations:0 string UIInterfaceOrientationPortrait' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UISupportedInterfaceOrientations:1 string UIInterfaceOrientationLandscapeLeft' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UISupportedInterfaceOrientations:2 string UIInterfaceOrientationLandscapeRight' "$app/Info.plist"

if [[ "$mode" == "simulator" ]]; then
  codesign --force --sign - "$app"
  zip -qry -1 "$out/QuotaCheck-ios-simulator-arm64.app.zip" "$app"
else
  mkdir -p "$out/PayloadDevice/QuotaCheck.app"
  rm -rf "$out/PayloadDevice/QuotaCheck.app"; mkdir -p "$out/PayloadDevice/QuotaCheck.app"
  cp -R "$app/." "$out/PayloadDevice/QuotaCheck.app/"
  (cd "$out/PayloadDevice" && zip -qry -1 "$out/QuotaCheck-ios-unsigned.ipa" Payload)
  rm -rf "$out/PayloadDevice"
fi
