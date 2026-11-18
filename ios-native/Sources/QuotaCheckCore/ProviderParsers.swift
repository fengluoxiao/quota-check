import Foundation

struct ProviderWindow {
    var title: String
    var used: Double?
    var remaining: Double?
    var details: String
}

private func providerNumber(_ value: Any?, negative: Bool = false) -> Double? {
    guard !isBoolValue(value), !(value is NSNull) else { return nil }
    if let value = value as? String, value.trimmingCharacters(in: .whitespaces).isEmpty { return nil }
    let result: Double?
    if let text = value as? String { result = Double(text) }
    else if let value = value as? NSNumber { result = value.doubleValue }
    else { result = nil }
    guard let result, result.isFinite, negative || result >= 0 else { return nil }
    return result
}

private func makeProviderWindow(title: String, percentRaw: Any?, resetRaw: Any? = nil, detail input: String = "") -> ProviderWindow? {
    var percent = providerNumber(percentRaw)
    if let value = percent, value > 100 { percent = nil }
    if percent == nil && input.isEmpty && (resetRaw == nil || resetRaw is NSNull) { return nil }
    let resetNumber = providerNumber(resetRaw, negative: true)
    var detail = input
    if !isBoolValue(resetRaw), resetRaw != nil, !(resetRaw is NSNull), resetNumber == nil || resetNumber! > 0,
       let resetText = formatProviderTime(resetRaw), !resetText.isEmpty {
        detail += (detail.isEmpty ? "" : "\n") + "重置时间：" + resetText
    }
    if percent == nil && detail.isEmpty { return nil }
    return ProviderWindow(
        title: String(title.prefix(200)),
        used: percent,
        remaining: percent == nil ? nil : 100 - percent!,
        details: detail.isEmpty ? "接口未提供具体次数。" : detail
    )
}

private func formatProviderTime(_ value: Any?) -> String? {
    let result = formatTime(value)
    return result.isEmpty ? nil : result
}

private func countWindow(title: String, usedRaw: Any?, totalRaw: Any?, leftRaw: Any?, resetRaw: Any? = nil, unit: String = "") -> ProviderWindow? {
    var used = providerNumber(usedRaw)
    var remaining = providerNumber(leftRaw)
    let total = providerNumber(totalRaw)
    if used == nil, let total, let remaining, remaining <= total { used = total - remaining }
    if remaining == nil, let used, let total { remaining = max(0, total - used) }
    if used == nil && total == nil && remaining == nil { return nil }
    var details: [String] = []
    if let used { details.append("已用 \(display(used))" + (unit.isEmpty ? "" : " \(unit)")) }
    if let total { details.append("总计 \(display(total))" + (unit.isEmpty ? "" : " \(unit)")) }
    if let remaining { details.append("剩余 \(display(remaining))" + (unit.isEmpty ? "" : " \(unit)")) }
    let percent = total != nil && total! > 0 && used != nil ? min(100, 100 * used! / total!) : nil
    return makeProviderWindow(title: title, percentRaw: percent, resetRaw: resetRaw, detail: details.joined(separator: " · "))
}

private func unwrapAli(_ initial: Any?) throws -> JSON {
    var current = initial
    for _ in 0..<8 {
        guard let data = object(current) else { throw QuotaError("阿里控制台响应格式异常。") }
        let failedRet = (array(data["ret"]) ?? []).contains { value in
            guard let text = value as? String else { return true }
            return !text.hasPrefix("SUCCESS::")
        }
        let badError = data["errorCode"] != nil && !(data["errorCode"] is NSNull) && !allowedErrorCode(data["errorCode"]) && data["success"] as? Bool != true && data["successResponse"] as? Bool != true
        if data["success"] as? Bool == false || data["successResponse"] as? Bool == false || data["failed"] as? Bool == true || failedRet || badError {
            throw QuotaError("阿里控制台认证失效或查询被拒绝，请更新访问令牌。")
        }
        if data["DataV2"] != nil { current = data["DataV2"] }
        else if let nested = object(data["data"]) { current = nested }
        else { return data }
    }
    throw QuotaError("阿里控制台响应嵌套异常。")
}

private func allowedErrorCode(_ value: Any?) -> Bool {
    if let number = value as? NSNumber { return number.intValue == 0 || number.intValue == 200 }
    if let text = value as? String { return ["", "0", "200"].contains(text) }
    return false
}

func parseProvider(id: String, payload: Any?, sealed: Bool = false) throws -> [ProviderWindow] {
    guard let data = object(payload) else { throw QuotaError("额度响应格式异常。") }
    let metadataError = object(data["ResponseMetadata"]) != nil && object(object(data["ResponseMetadata"])!["Error"]) != nil
    if data["success"] as? Bool == false || data["succeed"] as? Bool == false || data["failed"] as? Bool == true || data["error"] != nil || metadataError {
        throw QuotaError("服务拒绝查询，请检查凭据、登录状态或查询权限。")
    }
    var rows: [ProviderWindow?] = []
    if id == "claude" {
        let labels: [(String, String)] = [
            ("five_hour", "5 小时"), ("seven_day", "7 天"), ("seven_day_opus", "7 天 · Opus"),
            ("seven_day_sonnet", "7 天 · Sonnet"), ("seven_day_oauth_apps", "7 天 · OAuth Apps"),
            ("iguana_necktie", "其他周期"),
        ]
        for (key, label) in labels {
            if let item = object(data[key]) {
                rows.append(makeProviderWindow(title: "Claude Code · \(label)", percentRaw: item["utilization"], resetRaw: item["resets_at"]))
            }
        }
    } else if id == "deepseek" || id == "mimo_balance" {
        guard let balances = array(data["balance_infos"]) else { throw QuotaError("接口未返回余额明细。") }
        for raw in balances {
            guard let item = object(raw) else { throw QuotaError("余额明细格式异常。") }
            let currency = String((text(item["currency"]) ?? "").prefix(12))
            let fields: [(String, String)] = id == "deepseek"
                ? [("总余额", "total_balance"), ("现金余额", "topped_up_balance"), ("赠金余额", "granted_balance")]
                : [("账面余额（含冻结）", "total_available"), ("现金余额", "cash_balance"), ("赠金余额", "gift_balance"), ("冻结金额", "frozen_balance"), ("可用授信", "credit_available")]
            let lines: [String] = fields.compactMap { label, key in
                guard let value = providerNumber(item[key], negative: true) else { return nil }
                let formatter = NumberFormatter(); formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.minimumFractionDigits = 2; formatter.maximumFractionDigits = 2
                let amount = formatter.string(from: NSNumber(value: value)) ?? String(value)
                return "\(label) \(amount) \(currency)"
            }
            if !lines.isEmpty {
                rows.append(ProviderWindow(title: (service(id: id)?.label ?? id) + " · " + currency, used: nil, remaining: nil, details: lines.joined(separator: "\n")))
            }
        }
    } else if id == "mimo" {
        guard let quota = object(data["quota"]) else { throw QuotaError("MiMo 未返回套餐积分，请检查是否为 Token Plan Key。") }
        if var row = countWindow(title: "MiMo · 套餐积分", usedRaw: quota["used_credits"], totalRaw: quota["total_credits"], leftRaw: quota["remaining_credits"], unit: "积分") {
            if let period = object(data["period"]), let end = text(period["end_at"]) {
                row.details += "\n周期结束（UTC）：" + String(end.prefix(100))
            }
            rows.append(row)
        } else {
            rows.append(nil)
        }
    } else if id == "ark_agent" {
        guard let result = object(data["Result"]) else { throw QuotaError("当前身份没有可用的个人版 Agent Plan 数据。") }
        for (key, label) in [("AFPFiveHour", "5 小时"), ("AFPDaily", "近一天"), ("AFPWeekly", "近一周"), ("AFPMonthly", "近一月")] {
            if let item = object(result[key]) {
                rows.append(countWindow(title: "方舟 Agent Plan · \(label)", usedRaw: item["Used"], totalRaw: item["Quota"], leftRaw: nil, resetRaw: item["ResetTime"], unit: "AFP"))
            }
        }
    } else if id == "aliyun_token" {
        let root = try unwrapAli(data)
        struct Group { var count: Int; var unit: String; var percentage: Any?; var reset: Any? }
        var groups: [String: Group] = [:]
        let pattern = try NSRegularExpression(pattern: #"^per(\d+)(Hour|Day|Week|Month)(Percentage|ResetTime)$"#)
        for key in root.keys {
            let range = NSRange(key.startIndex..<key.endIndex, in: key)
            guard let match = pattern.firstMatch(in: key, range: range), match.numberOfRanges == 4 else { continue }
            let ns = key as NSString
            let numberPart = Int(ns.substring(with: match.range(at: 1))) ?? 0
            let unitPart = ns.substring(with: match.range(at: 2))
            let field = ns.substring(with: match.range(at: 3))
            let groupKey = "\(numberPart)\(unitPart)"
            var group = groups[groupKey] ?? Group(count: numberPart, unit: unitPart, percentage: nil, reset: nil)
            if field == "Percentage" { group.percentage = root[key] } else { group.reset = root[key] }
            groups[groupKey] = group
        }
        let units: [String: String] = ["Hour": "小时", "Day": "天", "Week": "周", "Month": "月"]
        let hours: [String: Double] = ["Hour": 1, "Day": 24, "Week": 168, "Month": 720]
        for group in groups.values.sorted(by: { $0.count * Int(hours[$0.unit] ?? 1) < $1.count * Int(hours[$1.unit] ?? 1) }) {
            let ratio = providerNumber(group.percentage)
            rows.append(makeProviderWindow(title: "阿里 Token Plan · \(group.count) \(units[group.unit] ?? group.unit)", percentRaw: ratio != nil && ratio! <= 1 ? 100 * ratio! : nil, resetRaw: group.reset))
        }
    } else if id == "aliyun_coding" {
        let root = try unwrapAli(data)
        guard let instances = array(root["codingPlanInstanceInfos"]) else { throw QuotaError("阿里未返回 Coding Plan 套餐列表。") }
        for raw in instances {
            guard let item = object(raw), item["status"] as? String == "VALID", let quota = object(item["codingPlanQuotaInfo"]) else { continue }
            for (key, label) in [("per5Hour", "5 小时"), ("perWeek", "每周"), ("perBillMonth", "账单月")] {
                rows.append(countWindow(title: "阿里 Coding Plan · \(label)", usedRaw: quota[key + "UsedQuota"], totalRaw: quota[key + "TotalQuota"], leftRaw: nil, resetRaw: quota[key + "QuotaNextRefreshTime"]))
            }
        }
    } else {
        guard (data["code"] as? Int) == 0 else { throw QuotaError("讯飞会话已失效或请求被拒绝，请更新登录 Cookie。") }
        let payloadData = object(data["data"])
        let items = array(payloadData?[id == "astron" ? "seats" : "rows"])
        guard let list = items else { throw QuotaError("讯飞未返回套餐列表。") }
        for (index, raw) in list.enumerated() {
            guard let item = object(raw) else { throw QuotaError("讯飞套餐格式异常。") }
            let ident = String(String(describing: item["id"] ?? index + 1).prefix(50))
            if id == "astron" {
                let title = sealed ? "Astron · 席位 #\(ident)" : String((text(item["name"]) ?? text(item["seatTypeName"]) ?? "席位 #\(ident)").prefix(120))
                guard let usage = object(item["usage"]) else {
                    rows.append(ProviderWindow(title: title, used: nil, remaining: nil, details: "该席位尚无积分用量数据。"))
                    continue
                }
                rows.append(countWindow(title: title, usedRaw: usage["usedPoints"], totalRaw: usage["totalAuthorizedPoints"], leftRaw: nil, unit: "积分"))
            } else {
                guard let usage = object(item["codingPlanUsageDTO"]) else { continue }
                let title = sealed ? "星火套餐 #\(ident)" : "星火 · " + String((text(item["name"]) ?? "套餐 #\(ident)").prefix(120))
                for (prefix, label) in [("rp5h", "5 小时"), ("rpw", "每周"), ("package", "套餐总量")] {
                    if var row = countWindow(title: "\(title) · \(label)", usedRaw: usage[prefix + "Usage"], totalRaw: usage[prefix + "Limit"], leftRaw: prefix == "package" ? usage["packageLeft"] : nil) {
                        if let expires = text(item["expiresAt"]) { row.details += "\n套餐到期：" + String(expires.prefix(100)) }
                        rows.append(row)
                    } else {
                        rows.append(nil)
                    }
                }
            }
        }
    }
    let result = rows.compactMap { $0 }
    guard !result.isEmpty else { throw QuotaError("接口未返回可展示的额度或余额，请检查套餐状态；未生成模拟数据。") }
    return result
}
