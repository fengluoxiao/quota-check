#!/usr/bin/env bash
set -euo pipefail
: "${IOS_CERTIFICATE_P12_BASE64:?Configure IOS_CERTIFICATE_P12_BASE64}"
: "${IOS_CERTIFICATE_PASSWORD:?Configure IOS_CERTIFICATE_PASSWORD}"
: "${IOS_PROVISIONING_PROFILE_BASE64:?Configure IOS_PROVISIONING_PROFILE_BASE64}"
: "${IOS_TEAM_ID:?Configure IOS_TEAM_ID}"
umask 077
signing_dir="$RUNNER_TEMP/quota-signing"
mkdir -p "$signing_dir"
printf '%s' "$IOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$signing_dir/distribution.p12"
printf '%s' "$IOS_PROVISIONING_PROFILE_BASE64" | base64 --decode > "$signing_dir/profile.mobileprovision"
keychain_password="$(openssl rand -hex 32)"
printf '::add-mask::%s\n' "$keychain_password"
keychain_path="$signing_dir/build.keychain-db"
security create-keychain -p "$keychain_password" "$keychain_path"
security set-keychain-settings -lut 21600 "$keychain_path"
security unlock-keychain -p "$keychain_password" "$keychain_path"
security import "$signing_dir/distribution.p12" -P "$IOS_CERTIFICATE_PASSWORD" -A -t cert -f pkcs12 -k "$keychain_path"
security set-key-partition-list -S apple-tool:,apple: -k "$keychain_password" "$keychain_path"
security list-keychains -d user -s "$keychain_path" "$HOME/Library/Keychains/login.keychain-db"
security cms -D -i "$signing_dir/profile.mobileprovision" > "$signing_dir/profile.plist"
python3 - <<'PY'
import os,plistlib,re,shutil
from pathlib import Path
folder=Path(os.environ['RUNNER_TEMP'])/'quota-signing';profile=plistlib.loads((folder/'profile.plist').read_bytes());uuid=profile['UUID']
assert re.fullmatch(r'[A-Fa-f0-9-]+',uuid),'Invalid profile UUID'
team=os.environ['IOS_TEAM_ID'];assert team in profile.get('TeamIdentifier',[]),'Profile Team ID differs'
app_id=profile['Entitlements']['application-identifier'];expected=team+'.'+os.environ['IOS_BUNDLE_IDENTIFIER']
assert app_id==expected or app_id==team+'.*','Profile Bundle ID differs'
for directory in ('Library/MobileDevice/Provisioning Profiles','Library/Developer/Xcode/UserData/Provisioning Profiles'):
 target=Path.home()/directory;target.mkdir(parents=True,exist_ok=True);shutil.copy2(folder/'profile.mobileprovision',target/(uuid+'.mobileprovision'))
with open(os.environ['GITHUB_ENV'],'a') as f:f.write('IOS_PROFILE_UUID='+uuid+'\n')
PY
printf 'IOS_SIGNING_KEYCHAIN=%s\n' "$keychain_path" >> "$GITHUB_ENV"
