import Foundation

enum ServiceKind: String {
    case quota
    case balance
}

struct ServiceField {
    let key: String
    let label: String
    let required: Bool
}

struct ServiceSpec {
    let source: Int
    let id: String
    let label: String
    let auth: String
    let fields: [ServiceField]
    let help: String
    let kind: ServiceKind
}

let services: [ServiceSpec] = [
    ServiceSpec(
        source: 3, id: "claude", label: "Claude Code", auth: "bearer",
        fields: [ServiceField(key: "secret", label: "Claude OAuth Access Token", required: true)],
        help: "使用 Claude Code 的 OAuth 访问令牌，不是 Anthropic 开放平台 API Key。令牌过期后需更新。",
        kind: .quota
    ),
    ServiceSpec(
        source: 4, id: "aliyun_token", label: "阿里百炼 Token Plan", auth: "ali",
        fields: [ServiceField(key: "secret", label: "百炼控制台 Access Token", required: true)],
        help: "使用 bailian auth login --console 获得的控制台访问令牌，不是模型 sk- Key。当前连接国内北京站点。",
        kind: .quota
    ),
    ServiceSpec(
        source: 5, id: "aliyun_coding", label: "阿里百炼 Coding Plan", auth: "ali",
        fields: [ServiceField(key: "secret", label: "百炼控制台 Access Token", required: true)],
        help: "使用百炼 CLI 控制台访问令牌查询国内 Coding Plan；模型调用 Key 不具有控制台查询权限。",
        kind: .quota
    ),
    ServiceSpec(
        source: 6, id: "ark_agent", label: "方舟 Agent Plan · 个人版", auth: "volc",
        fields: [
            ServiceField(key: "secret", label: "火山 Access Key ID", required: true),
            ServiceField(key: "secret2", label: "Secret Access Key", required: true),
            ServiceField(key: "session_token", label: "STS Session Token（临时凭据时必填）", required: false),
        ],
        help: "查询个人版 Agent Plan 的 AFP 额度。使用有 GetAFPUsage 权限的 AK/SK；若为 STS，必须同时填写 Session Token。",
        kind: .quota
    ),
    ServiceSpec(
        source: 7, id: "mimo", label: "小米 MiMo Token Plan", auth: "bearer",
        fields: [ServiceField(key: "secret", label: "MiMo Token Plan API Key", required: true)],
        help: "查询套餐周期积分。普通按量计费 Key 请改选 MiMo API 余额。",
        kind: .quota
    ),
    ServiceSpec(
        source: 8, id: "spark", label: "讯飞星火 Coding Plan", auth: "cookie",
        fields: [
            ServiceField(key: "secret", label: "maas.xfyun.cn 登录 Cookie", required: true),
            ServiceField(key: "secret2", label: "控制台 Authorization（可选）", required: false),
        ],
        help: "使用自己登录讯飞 MaaS 控制台后的完整 Cookie（含 ssoSessionId、tenantToken）。会话过期需更新；只读取套餐列表。",
        kind: .quota
    ),
    ServiceSpec(
        source: 9, id: "astron", label: "讯飞 Astron Token Plan", auth: "cookie",
        fields: [
            ServiceField(key: "secret", label: "maas.xfyun.cn 登录 Cookie", required: true),
            ServiceField(key: "secret2", label: "控制台 Authorization（可选）", required: false),
        ],
        help: "逐席位读取真实已用积分与总积分，不把席位数量当作 Token 额度。Cookie 过期后需重新登录官网更新。",
        kind: .quota
    ),
    ServiceSpec(
        source: 10, id: "deepseek", label: "DeepSeek API 余额", auth: "bearer",
        fields: [ServiceField(key: "secret", label: "DeepSeek API Key", required: true)],
        help: "查询官方 API 账户余额（现金、赠金与总余额），不是订阅窗口百分比。",
        kind: .balance
    ),
    ServiceSpec(
        source: 11, id: "mimo_balance", label: "小米 MiMo API 余额", auth: "bearer",
        fields: [ServiceField(key: "secret", label: "小米普通 API Key", required: true)],
        help: "查询按量计费账户余额、冻结资金及可用授信。Token Plan Key 请改选 MiMo Token Plan。",
        kind: .balance
    ),
]

func service(id: String) -> ServiceSpec? {
    services.first { $0.id == id }
}

func service(source: Int) -> ServiceSpec? {
    services.first { $0.source == source }
}

struct UsageWindow {
    var title: String
    var used: Double?
    var remaining: Double?
    var reset: String
    var detail: String
    var expandedTitle: String?
    var expandedLines: [String]?
}

struct AccountCard {
    var id: String
    var title: String
    var subtitle: String
    var windows: [UsageWindow]
    var error: String?
    var cached = false
    var kind: ServiceKind = .quota
    var actions: [String] = []
    var queries: [String: [UsageWindow]] = [:]
}

extension AccountCard: Identifiable {}

extension ServiceKind: Identifiable {
    public var id: String { rawValue }
}

struct PanelUser {
    var id: Int?
    var email: String?
    var username: String?
    var role: String?
}

struct Profile {
    var kind: String
    var site: String?
    var key: String?
    var url: String?
    var email: String?
    var password: String?
    var accessToken: String?
    var refreshToken: String?
    var user: PanelUser?
    var username: String?
    var secret: String?
    var secret2: String?
    var sessionToken: String?
    var cached = false
    var sealed = false
}

struct VaultData {
    var source = 0
    var profiles: [String: Profile] = [:]

    func jsonValue() throws -> JSON {
        var profiles: JSON = [:]
        for (name, profile) in profiles.sorted(by: { $0.key < $1.key }) {
            var value: JSON = ["sealed": profile.sealed]
            switch profile.kind {
            case "kimi":
                value["key"] = profile.key ?? ""
            case "glm":
                value["site"] = profile.site ?? "cn"
                value["key"] = profile.key ?? ""
            case "newapi":
                value["url"] = profile.url ?? ""
                value["username"] = profile.username ?? ""
                value["password"] = profile.password ?? ""
            case "sub2api":
                value["url"] = profile.url ?? ""
                value["email"] = profile.email ?? ""
                if let password = profile.password { value["password"] = password }
                if let access = profile.accessToken { value["access_token"] = access }
                if let refresh = profile.refreshToken { value["refresh_token"] = refresh }
                value["cached"] = profile.cached
                if let user = profile.user {
                    var item: JSON = ["role": user.role ?? "admin"]
                    if let id = user.id { item["id"] = id }
                    if let email = user.email { item["email"] = email }
                    if let username = user.username { item["username"] = username }
                    value["user"] = item
                }
            default:
                value["secret"] = profile.secret ?? ""
                if let secret2 = profile.secret2 { value["secret2"] = secret2 }
                if let session = profile.sessionToken { value["session_token"] = session }
            }
            profiles[name] = value
        }
        return ["version": 1, "source": source, "profiles": profiles]
    }
}

extension ServiceKind: Sendable {}

func freshVault() -> VaultData { VaultData() }
