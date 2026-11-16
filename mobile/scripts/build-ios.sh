#!/usr/bin/env bash
set -euo pipefail
mobile_root="$(cd "$(dirname "$0")/.." && pwd)"
out="$mobile_root/build-ios"
mkdir -p "$out"
workspace="$(find "$mobile_root/ios" -maxdepth 1 -name '*.xcworkspace' -print -quit)"
if [[ -z "$workspace" ]]; then printf 'No generated Xcode workspace found.\n' >&2; exit 1; fi
scheme=QuotaCheck
mode="${IOS_SIGNING_MODE:-unsigned}"
derived="${RUNNER_TEMP:-$mobile_root/build-ios}/quota-derived"
if [[ "$mode" == signed ]]; then
  : "${IOS_TEAM_ID:?Signed builds need IOS_TEAM_ID}"
  : "${IOS_PROFILE_UUID:?Signed builds need an installed provisioning profile}"
  archive="${RUNNER_TEMP}/QuotaCheck.xcarchive"
  xcodebuild -workspace "$workspace" -scheme "$scheme" -configuration Release -destination 'generic/platform=iOS' -archivePath "$archive" archive CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM="$IOS_TEAM_ID" PROVISIONING_PROFILE_SPECIFIER="$IOS_PROFILE_UUID" CODE_SIGN_IDENTITY='Apple Distribution'
  python3 - <<'PY'
import os,plistlib
from pathlib import Path
options={'method':os.environ.get('IOS_EXPORT_METHOD','release-testing'),'teamID':os.environ['IOS_TEAM_ID'],'signingStyle':'manual','provisioningProfiles':{os.environ['IOS_BUNDLE_IDENTIFIER']:os.environ['IOS_PROFILE_UUID']},'signingCertificate':'Apple Distribution','manageAppVersionAndBuildNumber':False}
p=Path(os.environ['RUNNER_TEMP'])/'QuotaExportOptions.plist';p.write_bytes(plistlib.dumps(options))
PY
  xcodebuild -exportArchive -archivePath "$archive" -exportOptionsPlist "$RUNNER_TEMP/QuotaExportOptions.plist" -exportPath "$out/signed"
  cp "$out/signed/QuotaCheck.ipa" "$out/QuotaCheck-ios-signed.ipa"
else
  xcodebuild -workspace "$workspace" -scheme "$scheme" -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath "$derived" build ARCHS=arm64 ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=''
  app="$derived/Build/Products/Release-iphoneos/QuotaCheck.app"
  package="$(mktemp -d)"
  mkdir -p "$package/Payload"
  ditto "$app" "$package/Payload/QuotaCheck.app"
  (cd "$package" && zip -qry "$out/QuotaCheck-ios-unsigned.ipa" Payload)
  rm -rf "$package"
fi
if [[ "${IOS_BUILD_SIMULATOR:-true}" == true ]]; then
  xcodebuild -workspace "$workspace" -scheme "$scheme" -configuration Release -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' -derivedDataPath "$derived-simulator" build ARCHS=arm64 ONLY_ACTIVE_ARCH=YES CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO
  app="$derived-simulator/Build/Products/Release-iphonesimulator/QuotaCheck.app"
  ditto -c -k --keepParent "$app" "$out/QuotaCheck-ios-simulator-arm64.app.zip"
  simulator="$(xcrun simctl list devices available -j | python3 -c 'import json,sys;d=json.load(sys.stdin);choices=[v for k,a in d["devices"].items() if "iOS-27" in k for v in a if v.get("isAvailable") and v["name"].startswith("iPhone")];assert choices,"No iOS 27 simulator";print(choices[0]["udid"])')"
  xcrun simctl boot "$simulator" || true
  xcrun simctl bootstatus "$simulator" -b
  xcrun simctl install "$simulator" "$app"
  xcrun simctl launch "$simulator" "$IOS_BUNDLE_IDENTIFIER"
  sleep 8
  xcrun simctl openurl "$simulator" 'quota-check://native-check'
  container="$(xcrun simctl get_app_container "$simulator" "$IOS_BUNDLE_IDENTIFIER" data)"
  for attempt in {1..30}; do
    if [[ -f "$container/Documents/native-health.json" ]]; then break; fi
    sleep 2
  done
  cp "$container/Documents/native-health.json" "$out/native-health.json"
  python3 - "$out/native-health.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]));assert report.get('ok'),report
print('Simulator Keychain, native AES/Argon2 and encrypted storage checks passed')
PY
  xcrun simctl io "$simulator" screenshot "$out/ios-simulator.png"
  xcrun simctl spawn "$simulator" launchctl list > "$out/simulator-processes.txt"
  python3 - "$out/simulator-processes.txt" <<'PY'
import os,sys
lines=open(sys.argv[1]).read().splitlines();bundle=os.environ['IOS_BUNDLE_IDENTIFIER']
assert any(bundle in line and line.split()[0]!='-' for line in lines),'Application is not running after launch'
PY
fi
(cd "$out" && shasum -a 256 *.ipa *.zip > SHA256SUMS.txt)
