import Foundation

func liveUsage(_ payload: Any?) throws -> JSON {
    guard let data = object(payload) else { throw QuotaError("额度响应格式异常。") }
    guard let usage = object(data["usage"] ?? data) else { throw QuotaError("额度响应格式异常。") }
    return usage
}

func resetCreditCard(_ payload: Any?) throws -> UsageWindow {
    let credits = try liveUsage(payload)["rate_limit_reset_credits"]
    guard let credit = object(credits), let rawCount = credit["available_count"] as? Int, rawCount >= 0 else {
        throw QuotaError("当前 sub2api / 上游响应没有返回重置卡次数。")
    }
    var details = ["可用重置卡次数：\(display(Double(rawCount)))"]
    var expanded: [String] = []
    if let grants = array(credit["credits"]) {
        let now = Date()
        let expirations: [(Any, Date)] = grants.compactMap { raw in
            guard let grant = object(raw), grant["expires_at"] != nil, !(grant["expires_at"] is NSNull) else { return nil }
            guard let date = parseExposedDate(grant["expires_at"]) else { return nil }
            return (grant["expires_at"], date)
        }
        let nearest = expirations.map({ $0.1 }).min(by: { current, value in
            let currentFuture = current >= now, valueFuture = value >= now
            if currentFuture != valueFuture { return currentFuture }
            return abs(value.timeIntervalSince(now)) < abs(current.timeIntervalSince(now))
        }) {
            details.append("最近到期：\(formatTime(nearest.timeIntervalSince1970))")
        }
        for (index, raw) in grants.enumerated() {
            let time = object(raw).flatMap { formatTime($0["expires_at"]) } ?? ""
            expanded.append("#\(index + 1) · " + (time.isEmpty ? "接口未返回到期时间" : "到期：\(time)"))
        }
        if rawCount != grants.count { details.append("接口计数与明细条数不同；仅展示返回明细，不推算差额。") }
        if grants.count > 5 { details.append("明细较多，展开查看。") }
    } else {
        details.append("接口未返回到期明细，无法核对每张卡。")
    }
    return UsageWindow(
        title: "重置卡次数", used: nil, remaining: nil, reset: "", detail: details.joined(separator: "\n"),
        expandedTitle: expanded.isEmpty ? nil : "查看 \(expanded.count) 条重置卡明细",
        expandedLines: expanded.isEmpty ? nil : expanded
    )
}

private func parseExposedDate(_ value: Any?) -> Date? {
    guard !(value is Bool), !(value is NSNull) else { return nil }
    if let raw = value as? String {
        if let seconds = Double(raw) { return Date(timeIntervalSince1970: seconds > 100_000_000_000 ? seconds / 1000 : seconds) }
        let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: raw) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: raw)
    }
    if let seconds = (value as? NSNumber)?.doubleValue { return Date(timeIntervalSince1970: seconds > 100_000_000_000 ? seconds / 1000 : seconds) }
    return nil
}

func codexCreditCard(_ payload: Any?) throws -> UsageWindow {
    let credits = try liveUsage(payload)["credits"]
    guard let credit = object(credits) else { throw QuotaError("当前 sub2api / 上游响应没有返回点数余额。") }
    let detail: String
    if credit["unlimited"] as? Bool == true { detail = "点数余额：接口标记为不限量" }
    else if let balance = text(credit["balance"]), !balance.trimmingCharacters(in: .whitespaces).isEmpty {
        guard let value = Double(balance), value.isFinite, value >= 0, balance.count <= 64 else {
            throw QuotaError("点数余额格式无效，未推算可用余额。")
        }
        detail = "点数余额：\(balance)"
    }
    else if credit["has_credits"] as? Bool == false { detail = "点数余额：接口返回没有可展示余额" }
    else { throw QuotaError("接口未返回具体点数余额，未推算可用余额。") }
    return UsageWindow(title: "Codex 点数", used: nil, remaining: nil, reset: "", detail: detail)
}

func glmCards(profile: Profile, transport: Transport) async throws -> [AccountCard] {
    let url = (profile.site ?? "cn") == "global" ? "https://api.z.ai/api/monitor/usage/quota/limit" : "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
    let response = try await transport(RequestSpec(url: url, method: "GET", headers: ["Authorization": try validateKey(profile.key ?? ""), "Accept": "application/json"], body: nil))
    guard response.status < 300 else {
        if response.status == 401 { throw QuotaError("GLM Key 无效或已失效。", status: response.status) }
        throw QuotaError("GLM 请求失败（HTTP \(response.status)）。", status: response.status)
    }
    return try glmWindows(decodeJSON(response.body)).enumerated().map { index, item in
        AccountCard(id: "glm-\(index)", title: item.title, subtitle: profile.site == "global" ? "Z.ai" : "智谱 BigModel", windows: [item])
    }
}

func kimiWindows(_ payload: Any?) throws -> [UsageWindow] {
    guard let data = object(payload) else { throw QuotaError("Kimi 接口返回格式异常。") }
    var rows: [(JSON, String)] = []
    if let usage = object(data["usage"]) { rows.append((usage, "周额度")) }
    let limits = array(data["limits"]) ?? []
    for (index, raw) in limits.enumerated() {
        guard let item = object(raw), let detail = object(item["detail"] ?? item) else { throw QuotaError("Kimi 周期额度格式异常。") }
        rows.append((detail, kimiLabel(item: item, detail: detail, index: index)))
    }
    var result: [UsageWindow] = []
    for (data, fallback) in rows {
        let total = kimiAmount(data["limit"])
        var used = kimiAmount(data["used"]), remaining = kimiAmount(data["remaining"])
        if used == nil, let total, let remaining, remaining <= total { used = total - remaining }
        if remaining == nil, let total, let used { remaining = max(0, total - used) }
        if total == nil && used == nil && remaining == nil { continue }
        let percent = total != nil && total! > 0 && used != nil ? min(100, 100 * used! / total!) : nil
        var details: [String] = []
        if let used { details.append("已用 \(display(used))") }
        if let total { details.append("总计 \(display(total))") }
        if let remaining { details.append("剩余 \(display(remaining))") }
        let title = String(((text(data["name"]) ?? text(data["title"])) ?? fallback).prefix(160))
        result.append(UsageWindow(title: title, used: percent, remaining: percent == nil ? nil : 100 - percent!, reset: kimiReset(data), detail: details.joined(separator: " · ").isEmpty ? "接口未提供具体额度。" : details.joined(separator: " · ")))
    }
    guard !result.isEmpty else { throw QuotaError("Kimi 未返回可用的套餐额度，请使用 Kimi Coding Plan Key。") }
    return result
}

private func kimiAmount(_ value: Any?) -> Double? {
    guard !(value is Bool), !(value is NSNull) else { return nil }
    if let text = value as? String, !text.trimmingCharacters(in: .whitespaces).isEmpty, let value = Double(text), value.isFinite, value >= 0 { return value }
    if let value = value as? NSNumber, value.doubleValue.isFinite, value.doubleValue >= 0 { return value.doubleValue }
    return nil
}

private func kimiReset(_ data: JSON) -> String {
    for key in ["reset_at", "resetAt", "reset_time", "resetTime"] {
        if let value = data[key], !(value is NSNull) {
            let formatted = formatTime(value)
            return formatted.isEmpty ? String(String(describing: value).prefix(160)) : formatted
        }
    }
    for key in ["reset_in", "resetIn", "ttl"] {
        if let value = kimiAmount(data[key]) { return "接口返回：\(display(value)) 秒后重置" }
    }
    return ""
}

private func kimiLabel(item: JSON, detail: JSON, index: Int) -> String {
    for key in ["name", "title", "scope"] {
        if let value = text(item[key] ?? detail[key]), !value.trimmingCharacters(in: .whitespaces).isEmpty { return String(value.prefix(160)) }
    }
    let window = object(item["window"]) ?? [:]
    let duration = kimiAmount(window["duration"] ?? item["duration"] ?? detail["duration"])
    let unit = window["timeUnit"] ?? item["timeUnit"] ?? detail["timeUnit"]
    let names: [String: String] = ["TIME_UNIT_MINUTE": "分钟", "TIME_UNIT_HOUR": "小时", "TIME_UNIT_DAY": "天", "TIME_UNIT_WEEK": "周", "TIME_UNIT_MONTH": "月", "TIME_UNIT_SECOND": "秒"]
    if let duration, duration > 0, let unit = text(unit) {
        if unit == "TIME_UNIT_MINUTE", duration.truncatingRemainder(dividingBy: 60) == 0 { return display(duration / 60) + " 小时额度" }
        if let name = names[unit] { return display(duration) + " \(name)额度" }
    }
    return "周期额度 #\(index + 1)"
}

func queryKimi(profile: Profile, transport: Transport) async throws -> [AccountCard] {
    let response = try await transport(RequestSpec(url: "https://api.kimi.com/coding/v1/usages", method: "GET", headers: ["Authorization": "Bearer " + (try validateKey(profile.key ?? "")), "Accept": "application/json"], body: nil))
    guard (200..<300).contains(response.status) else {
        let messages: [Int: String] = [401: "Kimi Key 无效或已失效，请使用 Coding Plan Key。", 403: "Kimi 查询权限不足，请检查 Coding Plan 套餐状态。", 404: "Kimi 用量接口不可用，请确认套餐类型。", 429: "Kimi 查询过于频繁，请稍后重试。"]
        throw QuotaError(messages[response.status] ?? "Kimi 查询失败（HTTP \(response.status)）。", status: response.status)
    }
    guard response.body.count <= 2_000_000 else { throw QuotaError("Kimi 接口响应过大。") }
    return try kimiWindows(decodeJSON(response.body)).enumerated().map { index, item in
        AccountCard(id: "kimi-\(index)", title: "Kimi · \(item.title)", subtitle: "Kimi Coding Plan", windows: [item])
    }
}

final class SubClient: @unchecked Sendable {
    let url: String
    var profile: Profile
    var pending = ""
    let transport: Transport

    init(profile: Profile, transport: @escaping Transport = nativeTransport) throws {
        self.url = try normalizeURL(profile.url ?? "")
        var value = profile
        value.url = self.url
        self.profile = value
        self.transport = transport
    }

    private func once(_ route: String, body: JSON? = nil, auth: Bool = true) async throws -> Any {
        var headers = ["Accept": "application/json"]
        if auth, let access = profile.accessToken { headers["Authorization"] = "Bearer " + (try validateKey(access)) }
        if body != nil { headers["Content-Type"] = "application/json" }
        let response = try await transport(RequestSpec(
            url: url + "/api/v1" + route, method: body == nil ? "GET" : "POST", headers: headers,
            body: body.flatMap { try? encodeJSON($0) }
        ))
        guard response.body.count <= 8 * 1024 * 1024 else { throw QuotaError("后台响应过大。") }
        let payload: Any
        do { payload = try decodeJSON(response.body) } catch { throw QuotaError("后台没有返回有效 JSON，请检查站点地址。", status: response.status) }
        guard let value = object(payload) else { throw QuotaError("后台返回格式异常。") }
        if response.status >= 300 || matchesCode(value["code"], 0) == false {
            let reason = text(value["reason"]) ?? String(describing: value["code"] ?? response.status)
            let statusMessages: [Int: String] = [401: "后台登录已过期或邮箱密码错误。", 403: "后台拒绝请求，请检查管理员权限。", 404: "当前版本没有此接口或账号不存在。", 429: "请求过于频繁，请稍后再试。"]
            let errors: [String: String] = [
                "INVALID_CREDENTIALS": "邮箱或密码不正确。", "INVALID_PASSWORD": "邮箱或密码不正确。",
                "ADMIN_REQUIRED": "需要 sub2api 管理员权限。",
                "ADMIN_COMPLIANCE_ACK_REQUIRED": "请先在 sub2api 后台完成部署确认。",
                "OPENAI_QUOTA_AUTH_FAILED": "上游 GPT 授权失效，请在 sub2api 后台重新授权。",
                "OPENAI_QUOTA_UPSTREAM_ERROR": "sub2api 查询上游额度失败，请检查账号授权。",
                "OPENAI_QUOTA_REQUEST_FAILED": "sub2api 无法连接上游，请检查服务端代理。",
                "CAPTCHA_REQUIRED": "站点需要人机验证，请在设置中填写有效凭据。",
                "CAPTCHA_INVALID": "站点人机验证未通过。",
            ]
            throw QuotaError(errors[reason] ?? statusMessages[response.status] ?? "后台请求失败，请检查账号和站点配置。", status: response.status, reason: reason)
        }
        return value["data"] ?? NSNull()
    }

    private func accept(_ data: Any?, requireUser: Bool = true) throws {
        guard let value = object(data), let access = text(value["access_token"]) else { throw QuotaError("登录响应缺少访问令牌。") }
        profile.accessToken = try validateKey(access)
        if let refresh = text(value["refresh_token"]) { profile.refreshToken = try validateKey(refresh) }
        if requireUser {
            guard let user = object(value["user"]), user["role"] as? String == "admin" else {
                profile.accessToken = nil; profile.refreshToken = nil
                throw QuotaError("读取 GPT 账号额度需要 sub2api 管理员。")
            }
            profile.user = PanelUser(id: value2Int(user["id"]), email: text(user["email"]), username: text(user["username"]), role: "admin")
        }
        pending = ""
    }

    func login(code: String = "", captcha: String = "", force: Bool = false) async throws {
        if !pending.isEmpty {
            guard code.range(of: #"^\d{6}$"#, options: .regularExpression) != nil else { throw NeedsOTP(message: "请输入 6 位登录验证码。") }
            try accept(await once("/auth/login/2fa", body: ["temp_token": pending, "totp_code": code], auth: false))
            return
        }
        if !force, profile.accessToken != nil, profile.user?.role == "admin" { return }
        guard let email = profile.email, !email.isEmpty, let password = profile.password, !password.isEmpty else {
            throw QuotaError("保存的会话失效，请由连接所有者更新登录信息。")
        }
        var body: JSON = ["email": email.trimmingCharacters(in: .whitespaces), "password": password]
        if !captcha.isEmpty { body["turnstile_token"] = captcha }
        let data = try await once("/auth/login", body: body, auth: false)
        if let value = object(data), value["requires_2fa"] as? Bool == true {
            guard let token = text(value["temp_token"]) else { throw QuotaError("缺少临时验证凭据。") }
            pending = token
            profile.accessToken = nil; profile.refreshToken = nil
            if !code.isEmpty { try await login(code: code, captcha: captcha); return }
            throw NeedsOTP(message: "该账号需要 2FA，请填写验证码后再次查询。")
        }
        try accept(data)
    }

    func request(_ route: String, body: JSON? = nil) async throws -> Any {
        do { return try await once(route, body: body) }
        catch let error as QuotaError {
            guard error.status == 401, let refresh = profile.refreshToken, !error.reason.hasPrefix("OPENAI_") else { throw error }
            try accept(await once("/auth/refresh", body: ["refresh_token": refresh], auth: false), requireUser: false)
            return try await once(route, body: body)
        }
    }

    private func accountId(_ account: Account) throws -> Int {
        guard account.id > 0 else { throw QuotaError("请选择有效的 GPT 账号。") }
        return account.id
    }

    func queryUsage(account: Account) async throws -> Any {
        try await request("/admin/openai/accounts/\(try accountId(account))/quota")
    }

    func queryResetCredits(account: Account) async throws -> UsageWindow {
        try resetCreditCard(await queryUsage(account: account))
    }

    func queryCredits(account: Account) async throws -> UsageWindow {
        try codexCreditCard(await queryUsage(account: account))
    }

    func refreshUsage(account: Account) async throws -> JSON {
        guard let data = object(try await request("/admin/openai/accounts/\(try accountId(account))/quota/refresh", body: [:])) else {
            throw QuotaError("sub2api 刷新额度响应格式异常。")
        }
        return data
    }

    func accounts() async throws -> [Account] {
        var rows: [Account] = []
        var seen = Set<Int>()
        var processed = 0
        for page in 1...100 {
            let data = try await request("/admin/accounts?page=\(page)&page_size=100&platform=openai&type=oauth")
            guard let value = object(data), let items = array(value["items"]) else { throw QuotaError("账号列表格式异常。") }
            processed += items.count
            for raw in items {
                guard let row = object(raw), let id = row["id"] as? Int, id > 0, !seen.contains(id),
                      (text(row["platform"]) ?? "openai") == "openai", (text(row["type"]) ?? "oauth") == "oauth" else { continue }
                seen.insert(id)
                rows.append(Account(id: id, name: text(row["name"]) ?? "", platform: text(row["platform"]), type: text(row["type"]), status: text(row["status"])))
            }
            let total = value["total"] as? Int
            if items.isEmpty || (total != nil ? processed >= total! : items.count < 100) { break }
        }
        return rows
    }

    func card(account: Account, cached: Bool = false) async throws -> AccountCard {
        let title = profile.sealed ? "GPT 账号 #\(account.id)" : (account.name.isEmpty ? "GPT 账号 #\(account.id)" : account.name)
        if !cached {
            do {
                let data = try await request("/admin/openai/accounts/\(account.id)/quota")
                guard let value = object(data) else { throw QuotaError("额度响应格式异常。") }
                let subtitle = [text(value["plan_type"]), "实时额度", formatTime(value["fetched_at"])].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
                return AccountCard(id: String(account.id), title: title, subtitle: subtitle, windows: subWindows(value), actions: ["reset", "credits", "refresh"])
            } catch let error as QuotaError where [404, 405, 501].contains(error.status) { _ = error }
        }
        let accountData = try await request("/admin/accounts/\(account.id)")
        guard let value = object(accountData), let extra = object(value["extra"]) else { throw QuotaError("后台没有可用额度快照。") }
        let windows = snapshotWindows(extra)
        guard !windows.isEmpty else { throw QuotaError("后台还没有该账号的额度快照。") }
        let subtitle = ["后台快照", formatTime(extra["codex_usage_updated_at"])].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
        return AccountCard(id: String(account.id), title: title, subtitle: subtitle, windows: windows, cached: true, actions: ["reset", "credits", "refresh"])
    }
}

func queryAll(client: SubClient, onCard: @escaping @Sendable (AccountCard) -> Void) async throws -> [AccountCard] {
    var accounts: [Account]
    do { accounts = try await client.accounts() }
    catch let error as QuotaError where error.status == 401 {
        try await client.login(force: true)
        accounts = try await client.accounts()
    }
    var out: [AccountCard] = []
    for account in accounts {
        let card: AccountCard
        do { card = try await client.card(account: account, cached: client.profile.cached) }
        catch {
            card = AccountCard(id: String(account.id), title: client.profile.sealed ? "GPT 账号 #\(account.id)" : (account.name.isEmpty ? "GPT 账号 #\(account.id)" : account.name), subtitle: "读取失败", windows: [], error: (error as? LocalizedError)?.errorDescription ?? "读取失败，请检查后台。", actions: ["reset", "credits", "refresh"])
        }
        out.append(card); onCard(card)
    }
    return out
}

struct Account {
    var id: Int
    var name: String
    var platform: String?
    var type: String?
    var status: String?
}

private func value2Int(_ value: Any?) -> Int? {
    value as? Int
}

private func matchesCode(_ left: Any?, _ expected: Int) -> Bool {
    if let number = left as? NSNumber { return number.intValue == expected }
    if let text = left as? String { return text == String(expected) }
    return false
}
