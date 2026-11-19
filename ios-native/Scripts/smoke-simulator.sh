#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bundle_id="${IOS_BUNDLE_IDENTIFIER:-com.fengluoxiao.quotacheck}"
app="$root/build/Payload/QuotaCheck.app"
out="$root/build"
simulator="${IOS_SMOKE_UDID:-$(xcrun simctl list devices available -j | python3 -c 'import json,sys;d=json.load(sys.stdin);choices=[v for k,a in d["devices"].items() if "iOS-27" in k for v in a if v.get("isAvailable") and v["name"].startswith("iPhone")];assert choices,"No iOS 27 simulator";print(choices[0]["udid"])')}"
xcrun simctl boot "$simulator" || true
xcrun simctl bootstatus "$simulator" -b
xcrun simctl install "$simulator" "$app"
xcrun simctl terminate "$simulator" "$bundle_id" 2>/dev/null || true
SIMCTL_CHILD_NATIVE_SMOKE_CHECK=1 xcrun simctl launch "$simulator" "$bundle_id"
sleep 15
container="$(xcrun simctl get_app_container "$simulator" "$bundle_id" data)"
for attempt in {1..30}; do
  if [[ -f "$container/Documents/native-health.json" ]]; then break; fi
  sleep 2
done
cp "$container/Documents/native-health.json" "$out/native-health.json"
python3 - "$out/native-health.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]));assert report.get('ok'),report
assert report.get('providerUI') == 9,report
assert report.get('crypto') is True and report.get('storage') is True and report.get('signing') is True,report
assert report.get('keychain') is True or report.get('keychainFallback') is True,report
assert report.get('importPersistence') is True,report
print('Native Swift app health checks passed')
PY
xcrun simctl io "$simulator" screenshot "$out/ios-simulator.png"
sleep 2
xcrun simctl io "$simulator" screenshot "$out/ios-simulator.png"
xcrun simctl spawn "$simulator" launchctl list > "$out/simulator-processes.txt"
python3 - "$out/simulator-processes.txt" "$bundle_id" <<'PY'
import sys
lines=open(sys.argv[1]).read().splitlines();bundle=sys.argv[2]
assert any(bundle in line and line.split()[0] != '-' for line in lines),'Application is not running'
PY
(cd "$out" && shopt -s nullglob; packages=(*.ipa *.zip); test "${#packages[@]}" -gt 0; shasum -a 256 "${packages[@]}" > SHA256SUMS.txt)
