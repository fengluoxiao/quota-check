# Quota Check 移动端（iOS 优先）

Expo SDK 58 + React Native 0.88，使用原生视图、输入框、开关、系统弹窗、文件选择与分享。没有 WebView 或内嵌网页界面。iPhone 为单列，iPad 宽屏为双栏。

## 功能

- GLM Coding Plan 国内 / 海外站点额度。
- sub2api 管理员登录、可选 2FA、会话续期、查询全部 GPT/OpenAI OAuth 账号。
- 每个 GPT 账号一张卡片，单账号错误不影响其他卡片。
- 设备加密保存连接，导入后不回填凭据，不提供再次导出。
- 导入和导出与 Windows 版兼容的跨电脑 .sqv 文件。

Windows 用户绑定的本机备份不能在 iOS 解密，需要桌面端另存为跨电脑文件。移动端本地文件采用独立设备模式，不对外导出；共享文件一律要求独立文件密码。

New API 渠道管理仍在桌面端；如果文件里只有 New API 登录信息，请先在桌面端读取 GLM Key，再导出包含 Key 的连接文件。

## 原生模块

modules/quota-vault 包含 iOS Swift / CryptoKit 和 Android Kotlin / JNI 实现。便携文件使用与桌面相同的 AES-256-GCM、Argon2id v1.3（t=3、m=65536 KiB、p=4）和二进制头。

Argon2 C 参考实现固定在上游提交 f57e61e19229e23c4445b85494dbf7c07de721cb，授权说明见 ios/vendor/argon2/LICENSE。本地密钥由 iOS Keychain / Android Keystore（expo-secure-store）保护，配置保存为设备私有加密文件。

网络通过原生 URLSession / HttpURLConnection，拒绝跟随重定向，避免把保存的请求凭据发送给另一个地址。支持自建 HTTP 服务，但 HTTP 不加密网络传输，请优先使用 HTTPS；HTTPS 采用系统证书校验，不放行无效证书。

本地加密与隐藏 UI 不等于能够抵抗控制设备、调试或修改程序的人。文件密码持有人具备解密共享文件的条件。真正不下发服务凭据需要服务器代查。

## 本地开发

需要 Node 24、pnpm 11.25.0。自定义原生模块不能直接在 Expo Go 中运行。

```sh
cd mobile
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm ios
# 或 pnpm android
```

iOS 本地编译需要 Mac 和 Xcode 27。Windows 可以运行类型检查、协议测试和 JS 导出；原生 iOS 编译交给 GitHub Actions。

## GitHub Actions：macOS 27

工作流 .github/workflows/ios.yml 使用官方 xcode-27 ARM64 runner，并检查 sw_vers 确实为 27.x。不是 macos-latest，也不会静默换用 macOS 26。

推送移动端改动会自动运行。工作流依次执行 TypeScript 检查、协议测试、Metro 导出、真实 Swift/C 加密兼容性与重定向检查、Expo prebuild、CocoaPods 和 xcodebuild。默认产出：

- QuotaCheck-ios-unsigned.ipa：真机 arm64 未签名 IPA，需要另行签名后安装。
- QuotaCheck-ios-simulator-arm64.app.zip：Apple Silicon Mac 上的 iOS 27 模拟器 App。
- ios-simulator.png：实际启动后的模拟器截图。
- SHA256SUMS.txt：包的校验文件。

未签名 IPA 不能直接通过普通方式安装到 iPhone，也不能直接提交 App Store。

## 可选：签名 IPA

在仓库 Actions 中手动运行 iOS 工作流，signing 选择 signed。提前配置仓库 Secrets：

- IOS_CERTIFICATE_P12_BASE64：Apple Distribution 证书和私钥的 .p12 文件 Base64。
- IOS_CERTIFICATE_PASSWORD：该 .p12 的导出密码。
- IOS_PROVISIONING_PROFILE_BASE64：匹配 Bundle ID 和分发方式的 provisioning profile Base64。
- IOS_TEAM_ID：Apple Developer Team ID。

可在仓库 Variables 设置 IOS_BUNDLE_IDENTIFIER，默认 com.fengluoxiao.quotacheck。export_method 支持 release-testing（测试设备分发）和 app-store-connect（用于后续 App Store Connect 分发）。工作流不自动上传 App Store。

签名材料仅在临时 keychain 和 runner 临时目录使用，不写入源码或构建附件。源代码、IPA 和模拟器包不是 Apple 账号登录凭据的替代品。

## Kimi Coding Plan

顶部选择 Kimi，在设置中输入 Kimi Code 套餐 Key。查询周额度及接口返回的全部周期额度；Key 使用现有 Keychain / 设备加密存储，支持跨平台 .sqv 导入导出。普通 Moonshot API 余额 Key 不适用。Windows 和移动端使用相同协议测试样例，缺失字段不会补成虚假的可用额度。
