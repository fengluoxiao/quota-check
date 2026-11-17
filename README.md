# Quota Check · GLM / Kimi / GPT 订阅额度查询

[下载 Windows x64 版本](https://github.com/fengluoxiao/quota-check/releases/latest) · [安全边界](SECURITY.md)

运行 SubscriptionQuota-v1.4.exe。左侧连接服务，右侧显示额度；右上角提供“保存到文件”和“导入文件”。

## 移动端（iOS 优先）

新增 [Expo / React Native 原生移动端](mobile/README.md)，支持 iPhone 单列、iPad 双栏、GLM / Kimi / sub2api、全部账号卡片和跨电脑加密配置。iOS 构建使用官方 `xcode-27`（macOS 27 ARM64）GitHub Actions runner。默认输出未签名真机 IPA 和 iOS 模拟器包；签名版本可配置 Apple 证书后手动构建。

## 一次填写，以后直接查询

在“查询服务”选择 GPT / Codex · sub2api，首次填写 sub2api 管理员站点、邮箱和密码，然后点击“查询全部 GPT 账号”。

登录成功后，程序将账号、密码和登录会话加密保存在本机。下次打开会恢复当前服务，无需重新输入密码，点击查询即可。会话过期时会先尝试续期；服务器撤销登录或要求 2FA 时仍需完成服务器的验证。

程序自动读取全部 OpenAI OAuth 账号。每个账号对应一张卡片，卡片内显示其 5 小时、7 天等实际额度窗口。个别账号失败时，该账号保留错误卡片，其他账号继续显示。

保存后的账号、密码、GLM / Kimi Key 不回填到输入框。输入框没有密码查看按钮。需要更换连接时，点击“更换连接（清除本机保存）”后重新填写。

## 加密连接文件 .sqv

保存的是连接配置与凭据，供重新导入后查询；文件中不保存虚构额度或测试账号。

右上角“保存到文件”提供两种方式：

- 本机备份：文件只能由对应 Windows 用户解密，导入时不需要额外文件密码。
- 跨电脑文件：设置至少 12 个字符的独立文件密码，导入时输入这个文件密码。文件密码与后台登录密码相互独立，程序不保存文件密码。

文件采用带版本号的二进制容器，数据由 AES-256-GCM 加密并进行完整性校验。本机模式通过 Windows 当前用户的 DPAPI 保护随机密钥；跨电脑模式通过 Argon2id（64 MiB、3 次迭代、4 lanes）派生密钥。没有写死在程序中的通用解密密码。文件篡改、错误密码或不匹配的本机用户会导致导入失败。

导入的连接只在程序内部使用：

- 不显示或回填真实登录账号、密码、Key。
- 服务器地址只读，不能通过界面改成其他地址来接收保存的凭据。
- 不提供明文查看、复制凭据或再次导出入口。
- 隐藏原始数据区域；GPT 账号卡片使用账号编号。
- 仍可移除该导入连接，重新填写自己的连接。

### 保护边界

这些措施保护静态文件与日常界面，不能保证掌控运行电脑、能够调试或修改程序的人也提取不到解密后的凭据。跨电脑文件的持有人如果拥有文件密码，也具备解密文件的条件；专有格式不是额外的密码学保护。

如果需要向别人提供查询功能，同时确保真正的账号密码和 Key 始终不下发，需要改用服务器代查，并向对方提供权限受限的查询凭据。当前版本是本地客户端，不作“收件人绝对无法获取凭据”的承诺。

## sub2api 实时额度与后台快照

实时查询使用 GET /api/v1/admin/openai/accounts/{id}/quota。旧版本没有这个接口时，会尝试读取账号详情中的额度快照，明确标注快照来源和采样时间。也可手动选择后台快照模式。

不调用通用主动用量探测、模型生成、额度重置或兑换接口。sub2api 本身已经配置的后台自动行为由该服务控制。多个账号按顺序读取，避免同一登录会话的刷新令牌并发轮换。

站点启用 2FA 时会显示验证码输入区。启用 Turnstile 的站点可在高级选项填写有效 Token，工具不会绕过人机验证。上游 GPT 账号需要已经导入该 sub2api，后台登录用户需要管理员权限。

## GLM Coding Plan 与 New API

GLM 页面支持国内智谱和海外 Z.ai。首次输入 Key 查询成功后自动加密保存，以后直接查询；接口没有提供的次数或重置时间不会推算。

New API 导入入口保留。首次填写的 New API 账号密码也会加密保存；读取渠道原始 Key 仍需超级管理员及服务端要求的安全验证。多 Key 渠道可选择 Key 编号，Key 不回填明文。

## 本机文件

加密连接存储在：%LOCALAPPDATA%\GLMQuota\connections.sqv。

兼容读取上一版通过 DPAPI 保存的 GLM Key。异常日志位于同目录的 errors.jsonl，只记录异常类型、阶段和代码位置，不记录凭据、响应正文或异常消息。

## 环境与构建

Windows 10/11，64 位。exe 内含 Python，需要 Windows App Runtime 2.6.5 或同系列兼容版本（x64），当前电脑已具备该运行时。已保留之前修复的 HTTPS 证书依赖。

源码主要文件：app.py（窗口）、ui_actions.py（凭据与批量查询交互）、vault.py（加密容器）、file_dialogs.py（Windows 文件选择）、sub2api.py、quota.py、newapi.py、settings.py 和 diagnostics.py。

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean GLMQuota.spec
~~~

生成文件为 dist/SubscriptionQuota-v1.2.exe。

## 验证

自动化测试覆盖登录、会话续期、多账号、旧版回退、加密往返、错误密码、错误 Windows 用户、文件篡改、格式校验、密钥字段隐藏和导入连接禁止重导出。隐藏窗口检查覆盖一次点击查全部、单账号失败仍保留全部卡片，以及导入后不回填账号密码、隐藏原始数据和直接查询。

测试服务和测试凭据仅在开发测试目录使用，未打包进产品。你的实际站点仍需在本机工具中连接验证，不必在聊天中提供账号密码。

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

当前版本已通过 68 项自动化测试和 8 项打包后检查。sub2api / New API 端到端交互通过本地协议测试服务验证；私有站点的版本和配置仍需实际连接确认。

此仓库不包含任何真实账号、密码、API Key、本机连接文件或开发日志。Windows exe 发布在 Releases 中，不写入 Git 历史。

## Kimi Coding Plan（Windows / iOS）

从查询服务选择 Kimi，首次填写 Kimi Code 套餐 API Key，成功后本机加密保存；之后点击查询即可。周额度、周期额度及重置时间只按真实接口返回展示，不调用模型，不消耗对话配额。普通 Moonshot 开放平台余额 Key 不适用。

使用官方 Kimi CLI 同源接口：GET https://api.kimi.com/coding/v1/usages，Authorization: Bearer <Coding Plan Key>。协议依据：[官方 CLI 用量查询](https://github.com/MoonshotAI/kimi-cli/blob/9ab1286b8fe4e6bcd116949a27ce5e0ac3389c82/src/kimi_cli/ui/shell/usage.py) 和 [官方平台地址](https://github.com/MoonshotAI/kimi-cli/blob/9ab1286b8fe4e6bcd116949a27ce5e0ac3389c82/src/kimi_cli/auth/platforms.py)，核实日期 2026-11-17。

Kimi 连接可保存到加密 .sqv 文件，在更新后的 Windows / iOS 应用间导入。导入后隐藏 Key 并禁止再次导出；旧版应用不认识新增 Kimi 连接，需要一起更新。已有 GLM / sub2api 文件仍可使用。

缺少 used / remaining 时不会补成零使用，缺少重置时间时不推算。开发测试的协议样例仅位于 tests/fixtures，不会作为产品数据或查询失败后的回退。
