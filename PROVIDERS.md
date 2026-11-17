# 服务接入说明（v1.5.0）

全部查询均为读取操作，不发送模型消息、不刷新或重置套餐、不购买、分配、轮换或导出服务端 Key。没有模拟额度回退。服务源地址固定，拒绝重定向，不能把导入凭据改发至其他地址。

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
