import Foundation

func formatTime(_ value: Any?) -> String {
    guard value != nil, !(value is NSNull), let raw = value as? String, !raw.isEmpty || value is NSNumber else {
        if value is NSNumber || value is Int || value is Double { return formatNumberTime(value) }
        return ""
    }
    if let numberValue = number(value, negative: true) { return formatNumberTime(numberValue) }
    return formatDate(parseDate(raw)) ?? String(raw.prefix(160))
}

private func formatNumberTime(_ value: Any?) -> String {
    guard let seconds = number(value, negative: true) else { return "" }
    let date = Date(timeIntervalSince1970: seconds > 100_000_000_000 ? seconds / 1000 : seconds)
    return formatDate(date) ?? ""
}

private func parseDate(_ raw: String) -> Date? {
    if raw.isEmpty { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = formatter.date(from: raw) { return date }
    formatter.formatOptions = [.withInternetDateTime]
    if let date = formatter.date(from: raw) { return date }
    let formats = ["yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss"]
    let local = DateFormatter()
    local.locale = Locale(identifier: "en_US_POSIX")
    local.timeZone = TimeZone.current
    for format in formats { local.dateFormat = format; if let date = local.date(from: raw) { return date } }
    return nil
}

private func formatDate(_ date: Date?) -> String? {
    guard let date else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "zh_CN")
    formatter.timeZone = TimeZone.current
    formatter.dateFormat = "MM/dd HH:mm"
    return formatter.string(from: date)
}

func makeWindow(title: String, usedRaw: Any?, resetRaw: Any? = nil, detail: String = "") -> UsageWindow {
    let used = number(usedRaw)
    let safeUsed: Double? = (used ?? -1) >= 0 ? used : nil
    return UsageWindow(
        title: title,
        used: safeUsed,
        remaining: safeUsed == nil ? nil : max(0, 100 - safeUsed!),
        reset: formatTime(resetRaw),
        detail: detail
    )
}

func glmWindows(_ payload: Any?) throws -> [UsageWindow] {
    guard let data = object(payload) else { throw QuotaError("GLM 返回格式异常。") }
    if data["success"] as? Bool == false { throw QuotaError("GLM 拒绝查询，请检查 Key 和套餐状态。") }
    if let code = data["code"], !allowedResponseCodes(code) { throw QuotaError("GLM 拒绝查询，请检查 Key 和套餐状态。") }
    let root = object(data["data"]) ?? data
    guard let limits = array(root["limits"]) else { throw QuotaError("没有返回套餐额度，请确认使用 Coding Plan Key。") }
    return try limits.filter { object($0) != nil }.map { raw in
        guard let item = object(raw) else { throw QuotaError("GLM 返回格式异常。") }
        let type = text(item["type"]) ?? "额度"
        let unit = number(item["unit"])
        let count = number(item["number"])
        var label = type == "TIME_LIMIT" ? "工具额度" : ["TOKENS_LIMIT", "CREDIT_LIMIT"].contains(type) ? "模型额度" : type
        if unit == 6 { label += " · 每周" }
        else if unit == 3, let count, count != 0 { label += " · " + display(count) + " 小时" }
        else if unit == 5 { label += " · 每月" }
        let used = number(item["currentValue"]), total = number(item["usage"])
        let detail = used != nil && total != nil && used! >= 0 && used! <= total!
            ? "已用 \(display(used!)) / 总计 \(display(total!)) · 剩余 \(display(total! - used!))"
            : ""
        let percent = number(item["percentage"])
        return makeWindow(
            title: label,
            usedRaw: percent != nil && percent! <= 100 ? percent : nil,
            resetRaw: item["nextResetTime"] ?? item["resetTime"] ?? item["resetAt"] ?? item["renewTime"],
            detail: detail
        )
    }
}

private func allowedResponseCodes(_ value: Any?) -> Bool {
    if let number = value as? NSNumber { return [0, 200].contains(number.intValue) }
    if let text = text(value) { return ["0", "200"].contains(text) }
    return false
}

func snapshotWindows(_ extra: JSON) -> [UsageWindow] {
    var out: [UsageWindow] = []
    for (part, label) in [("5h", "5 小时"), ("7d", "7 天")] {
        if extra["codex_\(part)_used_percent"] != nil && !(extra["codex_\(part)_used_percent"] is NSNull) {
            out.append(makeWindow(title: "GPT / Codex · \(label)", usedRaw: extra["codex_\(part)_used_percent"], resetRaw: extra["codex_\(part)_reset_at"]))
        }
    }
    if out.isEmpty {
        for (part, fallback) in [("primary", "主窗口"), ("secondary", "次窗口")] {
            if let used = extra["codex_\(part)_used_percent"], !(used is NSNull) {
                let minutes = number(extra["codex_\(part)_window_minutes"])
                let label = minutes == 10080 ? "7 天" : minutes == 300 ? "5 小时" : minutes != nil ? display(minutes!) + " 分钟" : fallback
                out.append(makeWindow(title: "GPT / Codex · \(label)", usedRaw: used, resetRaw: extra["codex_\(part)_reset_at"]))
            }
        }
    }
    return out
}

func subWindows(_ data: JSON) -> [UsageWindow] {
    var out: [UsageWindow] = []
    func rate(_ raw: Any?, name: String) {
        guard let limits = object(raw) else { return }
        for key in ["primary_window", "secondary_window"] {
            guard let item = object(limits[key]) else { continue }
            let seconds = number(item["limit_window_seconds"] ?? item["rate_limit_window_seconds"])
            let label = seconds == 18000 ? "5 小时" : seconds == 604800 ? "7 天" : seconds != nil ? display(seconds! / 3600) + " 小时" : key == "primary_window" ? "主窗口" : "次窗口"
            var reset: Any? = item["reset_at"]
            let fetched = number(data["fetched_at"]), after = number(item["reset_after_seconds"])
            if reset == nil || reset is NSNull, let fetched, let after { reset = fetched + after }
            out.append(makeWindow(title: "\(name) · \(label)", usedRaw: item["used_percent"], resetRaw: reset))
        }
    }
    rate(data["rate_limit"], name: "GPT / Codex")
    if let additional = array(data["additional_rate_limits"]) {
        for item in additional {
            guard let item = object(item) else { continue }
            rate(item["rate_limit"], name: text(item["limit_name"]) ?? text(item["metered_feature"]) ?? "附加额度")
        }
    }
    rate(data["code_review_rate_limit"], name: "代码审查")
    if out.isEmpty {
        for (key, label) in [("five_hour", "5 小时"), ("seven_day", "7 天"), ("thirty_day", "30 天")] {
            if let item = object(data[key]) {
                out.append(makeWindow(title: "GPT / Codex · \(label)", usedRaw: item["utilization"], resetRaw: item["resets_at"]))
            }
        }
    }
    return out
}
