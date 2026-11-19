import Foundation

func normalizeURL(_ value: String) throws -> String {
    let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
    var trimmed = text
    while trimmed.hasSuffix("/") { trimmed.removeLast() }
    guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased(),
          ["https", "http"].contains(scheme), !url.host.orEmpty.isEmpty,
          url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
          !trimmed.rangeOfCharacter(from: .whitespacesAndNewlines).isNotNil else {
        throw QuotaError("请输入完整的 HTTPS 或 HTTP 站点地址。")
    }
    for suffix in ["/api/v1", "/api"] where trimmed.lowercased().hasSuffix(suffix) {
        trimmed.removeLast(suffix.count)
        break
    }
    return trimmed
}

func validateKey(_ value: String) throws -> String {
    let text = value.trimmingCharacters(in: .whitespacesAndNewlines)
    let stripped = text.replacingOccurrences(
        of: "^Bearer\\s+", with: "", options: [.regularExpression, .caseInsensitive]
    )
    guard !stripped.isEmpty, stripped.unicodeScalars.allSatisfy({ $0.value >= 0x21 && $0.value <= 0x7e }) else {
        throw QuotaError("请输入有效的 Key，不能含空格或换行。")
    }
    return stripped
}

private func checkedString(_ value: Any?, field: String) throws -> String {
    guard let text = value as? String, text.count <= 32_768 else {
        throw QuotaError("连接字段格式无效：" + field)
    }
    return text
}

func headerSecret(_ value: Any?, required: Bool = true) throws -> String {
    guard let text = (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) else {
        if required { throw QuotaError("请先填写对应的访问凭据。") }
        return ""
    }
    guard text.count <= 32_768 else { throw QuotaError("凭据格式或长度无效。") }
    if required && text.isEmpty { throw QuotaError("请先填写对应的访问凭据。") }
    guard text.unicodeScalars.allSatisfy({ $0.value >= 0x20 && $0.value <= 0x7e }) else {
        throw QuotaError("凭据含有换行、控制字符或非英文字符。")
    }
    return text
}

func validateService(id: String, raw: Any?) throws -> Profile {
    guard let spec = service(id: id), let data = object(raw) else { throw QuotaError("服务连接无效。") }
    let allowed = Set(spec.fields.map(\.key) + ["sealed"])
    guard data.keys.allSatisfy(allowed.contains) else { throw QuotaError("服务连接包含不支持的字段。") }
    if let sealed = data["sealed"], !(sealed is Bool) { throw QuotaError("连接保护标记无效。") }
    var profile = Profile(kind: id)
    profile.sealed = data["sealed"] as? Bool == true
    for field in spec.fields {
        var value = try headerSecret(data[field.key], required: field.required)
        if !value.isEmpty && spec.auth != "cookie" && spec.auth != "volc" {
            value = value.replacingOccurrences(
                of: "^Bearer\\s+", with: "", options: [.regularExpression, .caseInsensitive]
            ).trimmingCharacters(in: .whitespaces)
            if value.contains(where: { $0 == " " }) { throw QuotaError("访问令牌含有空格。") }
        }
        if !value.isEmpty || field.required {
            switch field.key {
            case "secret": profile.secret = value
            case "secret2": profile.secret2 = value
            default: profile.sessionToken = value
            }
        }
    }
    return profile
}

func validateVault(_ value: Any?) throws -> VaultData {
    guard let data = object(value), (data["version"] as? Int) == 1, let rawProfiles = object(data["profiles"]) else {
        throw QuotaError("连接文件格式不受支持。")
    }
    var out = freshVault()
    if let source = data["source"] as? Int, (0...11).contains(source) { out.source = source }
    for name in rawProfiles.keys.sorted() {
        let raw = rawProfiles[name]
        if service(id: name) != nil {
            out.profiles[name] = try validateService(id: name, raw: raw)
            continue
        }
        guard let item = object(raw) else { throw QuotaError("连接信息格式无效。") }
        let allowed: [String: Set<String>] = [
            "kimi": ["key", "sealed"],
            "glm": ["site", "key", "sealed", "console_token"],
            "newapi": ["url", "username", "password", "sealed"],
            "sub2api": ["url", "email", "password", "access_token", "refresh_token", "user", "sealed", "cached"],
        ]
        guard let allowedKeys = allowed[name], item.keys.allSatisfy(allowedKeys.contains) else {
            throw QuotaError("连接文件包含不支持的字段。")
        }
        if let sealed = item["sealed"], !(sealed is Bool) { throw QuotaError("连接保护标记无效。") }
        var profile = Profile(kind: name)
        profile.sealed = item["sealed"] as? Bool == true
        if name == "kimi" {
            profile.key = try validateKey(try checkedString(item["key"], field: "key"))
        } else if name == "glm" {
            guard let site = item["site"] as? String, ["cn", "global"].contains(site) else {
                throw QuotaError("GLM 站点无效。")
            }
            profile.site = site
            profile.key = try validateKey(try checkedString(item["key"], field: "key"))
            if let token = item["console_token"] { profile.consoleToken = try headerSecret(token) }
        } else if name == "newapi" {
            profile.url = try normalizeURL(try checkedString(item["url"], field: "url"))
            profile.username = try checkedString(item["username"], field: "username")
            profile.password = try checkedString(item["password"], field: "password")
        } else {
            profile.url = try normalizeURL(try checkedString(item["url"], field: "url"))
            profile.email = try checkedString(item["email"], field: "email")
            for key in ["password", "access_token", "refresh_token"] {
                if let value = item[key] {
                    let text = try checkedString(value, field: key)
                    switch key {
                    case "password": profile.password = text
                    case "access_token": profile.accessToken = text
                    default: profile.refreshToken = text
                    }
                }
            }
            guard !(profile.email ?? "").isEmpty, profile.password != nil || profile.refreshToken != nil else {
                throw QuotaError("sub2api 连接信息不完整。")
            }
            if let cached = item["cached"], !(cached is Bool) { throw QuotaError("读取方式无效。") }
            profile.cached = item["cached"] as? Bool == true
            if let user = object(item["user"]) {
                let userKeys = Set(["id", "email", "username", "role"])
                guard user.keys.allSatisfy(userKeys.contains) else { throw QuotaError("登录会话格式无效。") }
                var panel = PanelUser(id: nil, email: nil, username: nil, role: nil)
                if let id = user["id"], !(id is NSNull) {
                    guard let number = id as? Int else { throw QuotaError("登录用户 ID 无效。") }
                    panel.id = number
                }
                for key in ["email", "username", "role"] where user[key] != nil && !(user[key] is NSNull) {
                    let value = try checkedString(user[key], field: key)
                    if key == "email" { panel.email = value }
                    if key == "username" { panel.username = value }
                    if key == "role" { panel.role = value }
                }
                profile.user = panel
            }
        }
        out.profiles[name] = profile
    }
    return out
}

func lockImported(_ value: Any?) throws -> VaultData {
    var vault = try validateVault(value)
    guard !vault.profiles.isEmpty else { throw QuotaError("文件中没有连接。") }
    for key in vault.profiles.keys { vault.profiles[key]?.sealed = true }
    return vault
}

func exportOwned(_ value: VaultData) throws -> VaultData {
    var vault = value
    for key in vault.profiles.keys where vault.profiles[key]?.sealed == true {
        vault.profiles.removeValue(forKey: key)
    }
    guard !vault.profiles.isEmpty else { throw QuotaError("导入连接只能查询，不能再次导出。") }
    let candidates: [(Int, String)] = [(0, "glm"), (1, "sub2api"), (2, "kimi")] + services.map { ($0.source, $0.id) }
    if service(source: vault.source) == nil && ![1, 2].contains(vault.source) {
        if let found = candidates.first(where: { vault.profiles[$0.1] != nil }) { vault.source = found.0 }
    }
    return vault
}

extension Optional where Wrapped == String {
    var orEmpty: String { self ?? "" }
}

extension Optional where Wrapped == Range<String.Index> {
    var isNotNil: Bool { self != nil }
}
