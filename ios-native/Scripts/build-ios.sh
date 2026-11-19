#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/build"
mkdir -p "$out/Payload/QuotaCheck.app"
mode="${IOS_BUILD_MODE:-simulator}"
build_number="${IOS_BUILD_NUMBER:-1}"
bundle_id="${IOS_BUNDLE_IDENTIFIER:-com.fengluoxiao.quotacheck}"
version="${IOS_APP_VERSION:-2.1.1}"

if [[ "$mode" == "simulator" ]]; then
  sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
  target="arm64-apple-ios17.0-simulator"
  platform="iphonesimulator"
  binary="$out/QuotaCheck-simulator"
elif [[ "$mode" == "device" ]]; then
  sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
  target="arm64-apple-ios17.0"
  platform="iphoneos"
  binary="$out/QuotaCheck-device"
else
  printf 'IOS_BUILD_MODE must be simulator or device\n' >&2; exit 2
fi

c_sources=$(find "$root/Sources/QuotaVaultC" -type f -name '*.c' | sort)
swift_sources=$(find "$root/Sources/QuotaCheckCore" "$root/Sources/QuotaCheckApp" -type f -name '*.swift' | sort)
object_dir="$out/objects-$mode"; rm -rf "$object_dir"; mkdir -p "$object_dir"
objects=()
while IFS= read -r source; do
  object="$object_dir/$(basename "${source%.c}").o"
  clang -c "$source" -o "$object" -O2 -arch arm64 -isysroot "$sdk" -target "$target" \
    -I "$root/Sources/QuotaVaultC" \
    -I "$root/Sources/QuotaVaultC/include" \
    -I "$root/Sources/QuotaVaultC/vendor/argon2/include" \
    -DARGON2_NO_THREADS
  objects+=("$object")
done < <(printf '%s\n' "$c_sources")
swiftc -parse-as-library -swift-version 5 -O -whole-module-optimization \
  -import-objc-header "$root/Sources/QuotaCheckCore/bridge.h" \
  -sdk "$sdk" -target "$target" \
  -I "$root/Sources/QuotaVaultC" \
  -I "$root/Sources/QuotaVaultC/include" \
  -I "$root/Sources/QuotaVaultC/vendor/argon2/include" \
  "${objects[@]}" $swift_sources \
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
/usr/libexec/PlistBuddy -c 'Add :UIDeviceFamily array' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UIDeviceFamily:0 integer 1' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :UIDeviceFamily:1 integer 2' "$app/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleSupportedPlatforms array' "$app/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleSupportedPlatforms:0 string $([[ "$mode" == simulator ]] && echo iPhoneSimulator || echo iPhoneOS)" "$app/Info.plist"

catalog="$out/AppAssets.xcassets"
python3 "$root/Scripts/build-icons.py" "$root/../mobile/assets/icon.png" "$catalog"
xcrun actool "$catalog" --compile "$app" --platform "$platform" --minimum-deployment-target 17.0 \
  --target-device iphone --target-device ipad --app-icon AppIcon --output-partial-info-plist "$out/icon-info-$mode.plist"
python3 - "$app/Info.plist" "$out/icon-info-$mode.plist" <<'PY'
import plistlib,sys
from pathlib import Path
path=Path(sys.argv[1]);info=plistlib.loads(path.read_bytes());icons=plistlib.loads(Path(sys.argv[2]).read_bytes())
info.update(icons)
assert info.get('CFBundleIcons',{}).get('CFBundlePrimaryIcon',{}).get('CFBundleIconName')=='AppIcon'
assert (path.parent/'Assets.car').is_file()
path.write_bytes(plistlib.dumps(info))
PY

if [[ "$mode" == "simulator" ]]; then
  codesign --force --sign - "$app"
  (cd "$(dirname "$app")" && zip -qry -1 "$out/QuotaCheck-ios-simulator-arm64.app.zip" "$(basename "$app")")
else
  ipa_root="$out/ipa"
  rm -rf "$ipa_root"
  mkdir -p "$ipa_root/Payload/QuotaCheck.app"
  cp -R "$app/." "$ipa_root/Payload/QuotaCheck.app/"
  ditto -c -k --sequesterRsrc --keepParent "$ipa_root/Payload" "$out/QuotaCheck-ios-unsigned.ipa"
  rm -rf "$ipa_root"
fi

(cd "$out"; shopt -s nullglob; packages=(*.ipa *.zip); shasum -a 256 "${packages[@]}" > SHA256SUMS.txt)
