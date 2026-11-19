# 服务接入说明（v2.1.1）

全部查询均为读取操作，不发送模型消息、不刷新或重置套餐、不购买、分配、轮换或导出服务端 Key。没有模拟额度回退。服务源地址固定，拒绝重定向，不能把导入凭据改发至其他地址。

## 卡片附加查询（Windows 与原生 SwiftUI iOS）

主额度查询成功后，在卡片下方按需读取；失败不会清空已经查询成功的额度。结果保留摘要，明细可以展开/收起。

| 服务 | 附加按钮 | 凭据和范围 |
| --- | --- | --- |
| GLM 国内 Coding Plan | 重置卡、加油包 | 另需网页控制台请求头中的完整 Authorization；套餐 Key 不替代网页会话。Windows 首次点击时添加，iOS 在设置中填写可选控制台字段，成功后加密保存。分别展示 5 小时/周重置卡次数与到期、加油包总额/剩余/最近到期。Z.ai 暂不使用国内接口。 |
| Claude Code | 重置次数、额外消费 | 复用 OAuth。重置使用可选 `cedar_ember=1`，只解析资格、次数、暂停和生效/到期时间；不保存 grant ID、兑换句柄。缺少该权益时提示不可确认，而非补零。消费上限和已消费保留接口计费单位，不称为钱包余额。 |
| MiMo API 余额 | 近7天用量、近7天账单 | 复用普通 API Key（不是 Token Plan Key）；日期参数取北京时间今天及前6天。只投影日期、模型/插件名称、请求次数、消费、折扣、赠金抵扣和实付；不展示响应中的 API Key 字段。 |
| 方舟个人 Agent Plan | 订阅到期 | 复用 AK/SK/STS，增加 `ListSubscribeTrade` 查询权限，限定 `RealAgentPlanPersonal`，逐条展示接口返回的 EndTime；不把额度窗口刷新时间当成订阅到期。 |

MiMo 套餐同时补充 `plan_code`、`auto_renew`、`claw_enabled`，普通余额补充 `credit_limit`，仅在实际返回时展示。其他未查到可靠权益接口的服务保持已有周期/余额查询。

GLM 控制台凭据以 `console_token` 可选字段保存在 GLM 连接内，导入后同样不可见、不可再次导出。旧文件无需此字段即可继续查询主额度。含此新字段的文件应在 v2.1.0 及以上版本间传递。Expo 客户端仅保留文件字段兼容；新增附加按钮以 Windows 和独立 SwiftUI 客户端为准。

本版不接方舟按模型时序明细：官方 CLI 说明了 GetUsageDetails，但本次未核实完整请求字段契约；不猜测请求体或把通用 API 用量伪装为套餐明细。

核实日期：2026-11-19。GLM 控制台接口与 Claude 可选权益不是公开稳定契约，可能因账号资格、权限或厂商升级返回不可用。未用用户真实凭据查询验证。

- GLM：[重置卡规则](https://docs.bigmodel.cn/cn/coding-plan/faq)，官网个人用量页面当前前端的 `GET /api/biz/customer-package-reset/list?targetType=PERSONAL`、`GET /api/biz/boosterPack/usage/remaining`。
- Claude：[OAuth 附加权益读取实现（第三方 CodexBar）](https://github.com/steipete/CodexBar/blob/main/Sources/CodexBarCore/Providers/Claude/ClaudeOAuth/ClaudeOAuthUsageFetcher.swift)、[重置权益字段](https://github.com/steipete/CodexBar/blob/main/Sources/CodexBarCore/Providers/Claude/ClaudeRateLimitResetCredits.swift)。
- MiMo：[官方日用量](https://mimo.mi.com/docs/zh-CN/api/asset/consumption-get)、[官方日账单](https://mimo.mi.com/docs/zh-CN/api/asset/daily-bill-get)。
- 方舟：[官方 CLI 订阅读取与到期字段](https://github.com/volcengine/ark-cli/blob/main/skills/arkcli-plans/references/arkcli-plans-get.md)。

| 服务 | 填写的凭据 | 展示的数据 | 范围 |
| --- | --- | --- | --- |
| GLM Coding Plan | 套餐 API Key | 真实周期额度 | 国内 / Z.ai |
| GPT / Codex · sub2api | 后台地址、管理员邮箱和密码 | 全部 OpenAI OAuth 账号 | 保持已有实现 |
| Kimi Coding Plan | Kimi Code 套餐 Key | 周额度及接口返回的各周期 | 普通 Moonshot 余额 Key 不适用 |
| Claude Code | OAuth Access Token | 5 小时、7 天、Opus / Sonnet 等窗口 | 普通 Anthropic API Key 不适用；过期需更新 OAuth 访问令牌 |
| 阿里 Token Plan | 百炼 CLI 控制台 Access Token | 返回的月 / 周 / 小时比例和重置时间 | 国内北京控制台；不是模型 sk- Key |
| 阿里 Coding Plan | 百炼 CLI 控制台 Access Token | 5 小时、每周、账单月额度 | 国内北京控制台有效套餐 |
| 方舟 Agent Plan | Access Key ID、Secret Access Key，可选 STS Session Token | AFP 5 小时、日 / 周 / 月窗口 | 个人版；IAM 身份需要 GetAFPUsage 权限，临时凭据必须保留 STS Token |
| MiMo Token Plan | 套餐 API Key | 周期积分总额、已用、剩余、周期结束 | 单独的 token-plan-cn 服务 |
| MiMo API 余额 | 普通 API Key | 账面余额、现金、赠金、冻结、授信 | 余额不是套餐额度；账面余额包含冻结资金 |
| 讯飞星火 Coding Plan | MaaS 登录 Cookie，可选控制台 Authorization | 5 小时、周、套餐总用量 | 官网控制台读取接口，会话过期需重新登录官网更新 |
| Astron Token Plan | MaaS 登录 Cookie，可选控制台 Authorization | 每个席位的积分已用、总额 | 自动读取所有页；席位数量不会被标为 Token 额度 |
| DeepSeek | API Key | 总余额、现金、赠金与币种 | 账户 API 余额，不是订阅窗口 |

## 凭据与文件

在 Windows 左侧或移动端服务列表选择目标服务后，界面会显示对应字段。百炼控制台令牌来自官方 CLI 的 console 登录身份（bailian auth login --console）；模型 API Key 没有控制台查询权限。讯飞使用自己登录 maas.xfyun.cn 后的 Cookie；不要把其他站点 Cookie 混入。所有字段以密码框显示，查询成功后加密保存，不回填明文。

切换服务会清空共享的未保存输入，防止凭据被发往其他厂商。每家凭据独立存入现有 .sqv 容器，Windows 使用 DPAPI、iOS 使用 Keychain 保护设备密钥；跨设备文件采用 Argon2id + AES-256-GCM。包含新服务的文件需要更新两端应用。导入后禁止重新导出、隐藏凭据与原始数据；这些措施不能抵抗控制设备或修改程序的人。

讯飞席位响应可能附带 API Key、Secret、电话和姓名；解析后仅保留展示所需额度字段，原始响应不写入本地设置或原始数据区域。导入的 Astron 连接使用席位编号。Cookie / OAuth / 控制台令牌可能失效；应用会报错，用户需在官网或官方 CLI 更新令牌。

## 接口依据

核实日期：2026-11-17。控制台接口会随厂商版本变化，不能承诺永久稳定。

- Kimi：[官方 CLI](https://github.com/MoonshotAI/kimi-cli/blob/main/src/kimi_cli/ui/shell/usage.py)，GET https://api.kimi.com/coding/v1/usages。
- Claude Code：Anthropic 官方分发的 @anthropic-ai/claude-code 2.0.76 CLI 源码中的 /api/oauth/usage 路径，现有 OAuth 使用接口；GET https://api.anthropic.com/api/oauth/usage。未把普通模型 Key 当成订阅凭据。
- 阿里：[官方 Token Plan 读取](https://github.com/modelstudioai/cli/blob/main/packages/commands/src/commands/usage/token-plan.ts)、[Coding Plan 读取](https://github.com/modelstudioai/cli/blob/main/packages/commands/src/commands/usage/coding-plan.ts)、[控制台网关认证与编码](https://github.com/modelstudioai/cli/blob/main/packages/core/src/console/gateway.ts)。只 POST 官方 CLI 网关的 usage / queryCodingPlanInstanceInfoV2 读取动作。
- 方舟：[官方 GetAFPUsage API](https://docs.volcengine.com/docs/ark/get-afp-usage-api?lang=zh)、[官方 CLI 用量说明](https://github.com/volcengine/ark-cli/blob/main/skills/arkcli-usage/references/arkcli-usage-plan.md)、[官方 SDK V4 签名](https://github.com/volcengine/volcengine-python-sdk/blob/master/volcenginesdkcore/signv4.py)。签名测试值由官方 SDK 离线生成。只调用 GetAFPUsage，不读取或创建 API Key。
- MiMo：[套餐积分](https://mimo.mi.com/docs/zh-CN/api/asset/credits-get)、[账户余额](https://mimo.mi.com/docs/zh-CN/api/asset/balance-get)。
- 讯飞：[官方 Token Plan 文档](https://www.xfyun.cn/doc/spark/TokenPlan.html)，及 MaaS 当前发布的 /js/index-fb8e20e9.js、/js/cpAndTpTool-c4de2e65.js、/js/index-7bea7e69.js。分别读取 /api/v1/gpt-finetune/coding-plan/list 和 /api/v1/gpt-finetune/token-plan/seats。没有调用 purchase / assign / refresh-key 等写入接口。
- DeepSeek：[官方余额 API](https://api-docs.deepseek.com/api/get-user-balance)，GET https://api.deepseek.com/user/balance。

## 验证范围

Windows / 移动端使用同一组协议样例，覆盖缺失字段、错误凭据、零用量、负余额、比例单位、分页和敏感字段过滤。样例只用于开发测试，不打包为查询数据，不在请求失败时显示。未持有用户各厂商真实登录凭据，未声称已验证某个实际订阅账号；真实账号需填写对应凭据后查询。

## iOS 包标识与图标

v2.1.1 恢复原有 Bundle ID `com.fengluoxiao.quotacheck`，应用名称为“额度查询”，原图标通过 asset catalog 编译，覆盖 iPhone/iPad 全套尺寸。构建校验 CFBundleIcons、AppIcon 和 Assets.car。独立 `.native` 预览包仍是另一个 App；其本机连接需用原始 .sqv 迁移。旧 Expo 原包名覆盖升级时保留加密文件，并尝试读取已知旧 Keychain 服务别名后迁移；签名团队变化导致的 Keychain 隔离仍需导入文件。
