import Foundation

protocol HashFunctions {
    func sha256(_ value: String) throws -> String
    func hmacSHA256(keyHex: String, message: String) throws -> String
}

struct NativeHash: HashFunctions {
    func sha256(_ value: String) throws -> String { try NativeHashCodec.sha256(value) }
    func hmacSHA256(keyHex: String, message: String) throws -> String { try NativeHashCodec.hmacSHA256(keyHex, message) }
}

func hexBytes(_ value: String) throws -> String {
    value.utf8.map { String(format: "%02x", $0) }.joined()
}

func signVolc(profile: Profile, hash: HashFunctions, stamp: String) throws -> [String: String] {
    guard stamp.range(of: #"^\d{8}T\d{6}Z$"#, options: .regularExpression) != nil else {
        throw QuotaError("签名时间格式无效。")
    }
    var headers = [
        "Content-Type": "application/json",
        "Host": "ark.cn-beijing.volcengineapi.com",
        "X-Date": stamp,
        "X-Content-Sha256": try hash.sha256("{}"),
    ]
    if let token = profile.sessionToken { headers["X-Security-Token"] = token }
    let lower = Dictionary(uniqueKeysWithValues: headers.map { ($0.key.lowercased(), $0.value) })
    let keys = lower.keys.sorted()
    let names = keys.joined(separator: ";")
    let canonical = ["POST", "/", "Action=GetAFPUsage&Version=2024-01-01",
                     keys.map { "\($0):\(lower[$0] ?? "")\n" }.joined(),
                     names, headers["X-Content-Sha256"] ?? ""].joined(separator: "\n")
    let scope = String(stamp.prefix(8)) + "/cn-beijing/ark/request"
    let message = ["HMAC-SHA256", stamp, scope, try hash.sha256(canonical)].joined(separator: "\n")
    var key = try hexBytes(profile.secret2 ?? "")
    for part in [String(stamp.prefix(8)), "cn-beijing", "ark", "request"] {
        key = try hash.hmacSHA256(keyHex: key, message: part)
    }
    headers["Authorization"] = "HMAC-SHA256 Credential=\(profile.secret ?? "")/\(scope), SignedHeaders=\(names), Signature=\(try hash.hmacSHA256(keyHex: key, message: message))"
    return headers
}

func serviceRequest(id: String, record: Profile, page: Int = 0, hash: HashFunctions? = nil, timestamp: String? = nil) throws -> RequestSpec {
    let profile = try validateService(id: id, raw: profileJSON(record))
    guard let spec = service(id: id) else { throw QuotaError("服务连接无效。") }
    var headers = ["Accept": "application/json"]
    let urls: [String: String] = [
        "claude": "https://api.anthropic.com/api/oauth/usage",
        "deepseek": "https://api.deepseek.com/user/balance",
        "mimo": "https://token-plan-cn.xiaomimimo.com/v1/platform/token_plan",
        "mimo_balance": "https://api.xiaomimimo.com/v1/platform/balance",
    ]
    if let url = urls[id] {
        headers["Authorization"] = "Bearer \(profile.secret ?? "")"
        if id == "claude" { headers["anthropic-beta"] = "oauth-2025-04-20" }
        return RequestSpec(url: url, method: "GET", headers: headers, body: nil)
    }
    if spec.auth == "ali" {
        let api = id == "aliyun_token" ? "zeldaHttp.apikeyMgr./tokenplan/personal/api/v2/usage" : "zeldaEasy.broadscope-bailian.codingPlan.queryCodingPlanInstanceInfoV2"
        var data: JSON = id == "aliyun_token" ? [:] : [
            "queryCodingPlanInstanceInfoRequest": [
                "commodityCode": "sfm_codingplan_public_cn",
                "onlyLatestOne": true,
            ] as JSON,
        ]
        data["cornerstoneParam"] = [
            "protocol": "V2", "console": "ONE_CONSOLE", "productCode": "p_efm",
            "switchUserType": 3, "consoleSite": "BAILIAN_ALIYUN",
        ] as JSON
        headers["Authorization"] = "Bearer \(profile.secret ?? "")"
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        let query = "action=BroadScopeAspnGateway&product=sfm_bailian&api=\(encodeQuery(api))"
        let payload = encodeQuery("params") + "=" + encodeQuery(try encodeJSON(["Api": api, "V": "1.0", "Data": data])) + "&region=cn-beijing"
        return RequestSpec(url: "https://bailian-cs.console.aliyun.com/cli/api.json?\(query)", method: "POST", headers: headers, body: payload)
    }
    if id == "ark_agent" {
        guard let hash else { throw QuotaError("原生签名模块不可用。") }
        let stamp = timestamp ?? ISO8601DateFormatter().string(from: Date())
            .replacingOccurrences(of: "-", with: "").replacingOccurrences(of: ":", with: "")
            .replacingOccurrences(of: #"\.\d{3}Z$"#, with: "Z", options: .regularExpression)
        headers.merge(try signVolc(profile: profile, hash: hash, stamp: stamp)) { _, new in new }
        return RequestSpec(url: "https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01", method: "POST", headers: headers, body: "{}")
    }
    guard page >= 0, page < 100 else { throw QuotaError("分页超限。") }
    let route = id == "astron" ? "token-plan/seats?page=\(page)&size=100" : "coding-plan/list?page=\(page + 1)&size=100"
    headers["Cookie"] = profile.secret ?? ""
    headers["Referer"] = "https://maas.xfyun.cn/" + (id == "astron" ? "tokenPlan" : "packageSubscription")
    if let secret2 = profile.secret2 { headers["Authorization"] = secret2 }
    return RequestSpec(url: "https://maas.xfyun.cn/api/v1/gpt-finetune/\(route)", method: "GET", headers: headers, body: nil)
}

private func encodeQuery(_ value: String) -> String {
    var allowed = CharacterSet.urlQueryAllowed
    allowed.remove(charactersIn: "+&=?")
    return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
}

func profileJSON(_ profile: Profile) -> JSON {
    var data: JSON = ["sealed": profile.sealed]
    if let value = profile.secret { data["secret"] = value }
    if let value = profile.secret2 { data["secret2"] = value }
    if let value = profile.sessionToken { data["session_token"] = value }
    return data
}

func queryService(id: String, profile: Profile, transport: Transport, hash: HashFunctions? = NativeHash()) async throws -> [AccountCard] {
    var cards: [AccountCard] = []
    var seen = Set<String>()
    for page in 0..<100 {
        let response = try await transport(serviceRequest(id: id, record: profile, page: page, hash: hash))
        guard (200..<300).contains(response.status) else {
            if [401, 403].contains(response.status) { throw QuotaError("认证失效或没有查询权限，请检查该服务要求的凭据类型。", status: response.status) }
            if response.status == 429 { throw QuotaError("查询过于频繁，请稍后重试。", status: response.status) }
            throw QuotaError("额度查询失败（HTTP \(response.status)）。", status: response.status)
        }
        guard response.body.count <= 2_000_000 else { throw QuotaError("接口响应过大。") }
        let payload = try decodeJSON(response.body)
        if page > 0, let data = object(payload), (data["code"] as? Int) == 0,
           let dataValue = object(data["data"]), let list = array(dataValue[id == "astron" ? "seats" : "rows"]), list.isEmpty {
            return cards
        }
        let windows = try parseProvider(id: id, payload: payload, sealed: profile.sealed)
        let spec = service(id: id)!
        for (index, item) in windows.enumerated() {
            cards.append(AccountCard(
                id: "\(id)-\(page)-\(index)", title: item.title,
                subtitle: spec.kind == .balance ? "账户余额" : spec.label,
                windows: [UsageWindow(title: spec.kind == .balance ? "余额明细" : "额度", used: item.used, remaining: item.remaining, reset: "", detail: item.details)],
                kind: spec.kind
            ))
        }
        guard id == "spark" || id == "astron" else { return cards }
        guard let data = object(payload), let dataValue = object(data["data"]), let list = array(dataValue[id == "astron" ? "seats" : "rows"]) else {
            throw QuotaError("讯飞未返回套餐列表。")
        }
        let marks = list.enumerated().map { index, item in String(describing: object(item)?["id"] ?? index) }
        let mark = (try? encodeJSON(marks)) ?? marks.joined()
        if seen.contains(mark) { throw QuotaError("后台未正确响应分页，已停止以避免重复。") }
        seen.insert(mark)
        let total = providerPublicNumber(dataValue["total"] ?? dataValue["totalCount"])
        if list.count < 100, let total, (page + 1) * 100 >= Int(total) { return cards }
        if list.count < 100 { return cards }
    }
    throw QuotaError("后台数据超过分页上限，未返回截断后的结果。")
}

func providerPublicNumber(_ value: Any?) -> Double? {
    guard !isBoolValue(value), !(value is NSNull), let value = value as? NSNumber else { return nil }
    let result = value.doubleValue
    return result.isFinite && result >= 0 ? result : nil
}
