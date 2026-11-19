import Foundation
import CoreFoundation

enum ProviderExtras {
    static func actions(_ name: String) -> [(String, String)] {
        switch name {
        case "glm": return [("reset", "重置卡"), ("boost", "加油包")]
        case "claude": return [("reset", "重置次数"), ("spend", "额外消费")]
        case "mimo_balance": return [("daily", "近7天用量"), ("bill", "近7天账单")]
        case "ark_agent": return [("subscription", "订阅到期")]
        default: return []
        }
    }

    static func number(_ raw: Any?) -> Double? {
        if let value = raw as? NSNumber {
            guard CFGetTypeID(value) != CFBooleanGetTypeID(), value.doubleValue.isFinite else { return nil }
            return value.doubleValue
        }
        if let raw = raw as? String, let value = Double(raw), value.isFinite { return value }
        return nil
    }

    static func flag(_ raw: Any?) -> Bool? {
        guard let value = raw as? NSNumber, CFGetTypeID(value) == CFBooleanGetTypeID() else { return nil }
        return value.boolValue
    }

    static func date(_ raw: Any?) -> Date? {
        if let n = number(raw) { return Date(timeIntervalSince1970: n > 1e11 ? n / 1000 : n) }
        guard let raw = raw as? String, !raw.isEmpty else { return nil }
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let result = iso.date(from: raw) { return result }
        iso.formatOptions = [.withInternetDateTime]
        if let result = iso.date(from: raw) { return result }
        let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(secondsFromGMT: 0)
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f.date(from: raw)
    }

    static func time(_ date: Date) -> String {
        let f = DateFormatter(); f.locale = Locale(identifier: "zh_CN"); f.dateFormat = "yyyy-MM-dd HH:mm zzz"
        return f.string(from: date)
    }

    static func result(_ title: String, _ value: String, _ lines: [String] = [], _ expanded: [String] = []) -> UsageWindow {
        UsageWindow(title: title, used: nil, remaining: nil, reset: "", detail: ([value] + lines).joined(separator: "\n"),
                    expandedTitle: expanded.isEmpty ? nil : "查看 \(expanded.count) 条明细", expandedLines: expanded.isEmpty ? nil : expanded)
    }

    static func request(_ name: String, _ action: String, _ profile: Profile, now: Date = Date()) throws -> RequestSpec {
        guard actions(name).contains(where: { $0.0 == action }) else { throw QuotaError("此服务不支持该查询。") }
        var headers = ["Accept": "application/json"]
        let url: String
        if name == "ark_agent" {
            let body = "{\"ResourceNames\":[\"RealAgentPlanPersonal\"]}"
            let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(secondsFromGMT: 0); f.dateFormat = "yyyyMMdd'T'HHmmss'Z'"
            headers.merge(try signVolc(profile: profile, hash: NativeHash(), stamp: f.string(from: now), action: "ListSubscribeTrade", body: body)) { _, new in new }
            return RequestSpec(url: "https://ark.cn-beijing.volcengineapi.com/?Action=ListSubscribeTrade&Version=2024-01-01", method: "POST", headers: headers, body: body)
        } else if name == "glm" {
            guard profile.site == "cn" else { throw QuotaError("当前只核实了国内 GLM 控制台的权益查询接口。") }
            guard let token = profile.consoleToken, !token.isEmpty else { throw QuotaError("请在设置中添加 GLM 网页控制台 Authorization，再查询重置卡或加油包。") }
            headers["Authorization"] = try headerSecret(token)
            url = "https://www.bigmodel.cn" + (action == "reset" ? "/api/biz/customer-package-reset/list?targetType=PERSONAL" : "/api/biz/boosterPack/usage/remaining")
        } else if name == "claude" {
            headers["Authorization"] = "Bearer " + (try validateKey(profile.secret ?? ""))
            headers["anthropic-beta"] = "oauth-2025-04-20"
            headers["User-Agent"] = "claude-cli/2.1.0 (external, cli)"
            url = "https://api.anthropic.com/api/oauth/usage" + (action == "reset" ? "?cedar_ember=1" : "")
        } else {
            headers["Authorization"] = "Bearer " + (try validateKey(profile.secret ?? ""))
            var calendar = Calendar(identifier: .gregorian); calendar.timeZone = TimeZone(secondsFromGMT: 8 * 3600)!
            let f = DateFormatter(); f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = calendar.timeZone; f.dateFormat = "yyyy-MM-dd"
            let start = calendar.date(byAdding: .day, value: -6, to: now)!
            url = "https://api.xiaomimimo.com/v1/platform/" + (action == "daily" ? "usage" : "billing") + "/daily?start_date=\(f.string(from: start))&end_date=\(f.string(from: now))"
        }
        return RequestSpec(url: url, method: "GET", headers: headers, body: nil)
    }

    static func fetch(_ name: String, _ action: String, _ profile: Profile, transport: Transport = nativeTransport) async throws -> [UsageWindow] {
        let response = try await transport(request(name, action, profile))
        guard (200..<300).contains(response.status) else {
            if [401, 403].contains(response.status) { throw QuotaError("附加查询凭据失效、无权限或该权益未向当前账号开放。") }
            if [400, 404, 405].contains(response.status) { throw QuotaError("该账号或服务版本不支持此附加查询。") }
            throw QuotaError("附加查询失败（HTTP \(response.status)）。")
        }
        guard response.body.utf8.count <= 2_000_000 else { throw QuotaError("附加信息响应过大。") }
        return try parse(name, action, decodeJSON(response.body))
    }

    static func parse(_ name: String, _ action: String, _ payload: Any?, now: Date = Date()) throws -> [UsageWindow] {
        guard let payload = object(payload) else { throw QuotaError("附加信息响应格式异常。") }
        if name == "ark_agent" {
            guard object(object(payload["ResponseMetadata"])?["Error"]) == nil,
                  let data = object(payload["Result"]), let items = array(data["InfoList"]) else { throw QuotaError("方舟未返回订阅明细，请检查 ListSubscribeTrade 查询权限。") }
            if items.isEmpty { return [result("方舟 · 个人订阅", "接口未返回订阅记录")] }
            return try items.enumerated().map { index, raw in
                guard let item = object(raw) else { throw QuotaError("方舟订阅格式异常。") }
                let end = date(item["EndTime"])
                let valid = end != nil && end!.timeIntervalSince1970 > 0
                return result("方舟 · 个人订阅 #\(index + 1)", valid ? (end! <= now ? "已到期" : "订阅到期：" + time(end!)) : "接口未返回有效到期时间")
            }
        }
        if name == "glm" {
            guard flag(payload["success"]) == true, number(payload["code"]) == 200, let data = object(payload["data"]) else {
                throw QuotaError("GLM 控制台会话失效或无查询权限，请更新控制台凭据。")
            }
            if action == "reset" {
                var rows: [UsageWindow] = []
                for (key, title) in [("fiveHourResets", "GLM · 5 小时重置卡"), ("weekResets", "GLM · 周重置卡")] {
                    guard let grants = array(data[key]) else { continue }
                    guard grants.count <= 1000, grants.allSatisfy({ object($0).flatMap { flag($0["available"]) } != nil }) else { throw QuotaError("GLM 重置卡明细无效。") }
                    let valid = grants.compactMap(object).filter { flag($0["available"]) == true }
                    let dates = valid.compactMap { date($0["expireTime"]) }.sorted()
                    let lines = dates.first.map { ["最近到期：" + time($0)] } ?? []
                    let expanded = valid.enumerated().map { index, grant in
                        "#\(index + 1) · " + (date(grant["expireTime"]).map { "到期：" + time($0) } ?? "接口未返回有效到期时间")
                    }
                    rows.append(result(title, "\(valid.count) 次可用", lines, expanded))
                }
                if !rows.isEmpty { return rows }
            } else {
                let total = number(data["totalMagnitude"]), left = number(data["totalBalance"])
                if (total != nil && total! < 0) || (left != nil && left! < 0) { throw QuotaError("GLM 加油包额度无效。") }
                if total != nil || left != nil {
                    var lines: [String] = []
                    if let total, total >= 0 { lines.append("总额度：" + display(total)) }
                    if let left, left >= 0 { lines.append("剩余额度：" + display(left)) }
                    if let expires = date(data["nearestExpireTime"]) { lines.append("最近到期：" + time(expires)) }
                    return [result("GLM · 加油包", left.map { "剩余 " + display($0) } ?? "接口未返回剩余额度", lines)]
                }
            }
        } else if name == "claude", action == "reset" {
            guard let data = object(payload["cedar_ember"]), let eligible = flag(data["eligible"]) else { throw QuotaError("当前 Claude 账号未返回重置权益，无法确认次数。") }
            if !eligible { return [result("Claude · 重置次数", "账号暂无重置资格")] }
            guard let grants = array(data["grants"]), grants.count <= 200 else { throw QuotaError("Claude 重置权益明细无效。") }
            var dates: [Date?] = []
            for raw in grants {
                guard let grant = object(raw), let left = number(grant["resets_left"]), left >= 0, left <= 1000, left.rounded() == left,
                      let paused = flag(grant["paused"]) else { throw QuotaError("Claude 重置权益数量无效。") }
                if let totalRaw = grant["resets_total"], !(totalRaw is NSNull) {
                    guard let total = number(totalRaw), total >= left, total.rounded() == total else { throw QuotaError("Claude 重置权益数量无效。") }
                }
                let start = date(grant["starts_at"]), end = date(grant["ends_at"])
                for (key, parsed) in [("starts_at", start), ("ends_at", end)] {
                    if let raw = grant[key], !(raw is NSNull), (raw as? String) != "", parsed == nil { throw QuotaError("Claude 重置权益时间无效。") }
                }
                if paused || (start != nil && start! > now) || (end != nil && end! <= now) { continue }
                guard dates.count + Int(left) <= 1000 else { throw QuotaError("Claude 重置权益数量超限。") }
                dates.append(contentsOf: Array(repeating: end, count: Int(left)))
            }
            dates.sort { ($0 ?? .distantFuture) < ($1 ?? .distantFuture) }
            var lines: [String] = []
            if let first = dates.first, let first { lines.append("最近到期：" + time(first)) }
            lines.append("持有次数不代表当前可立即兑换。")
            let expanded = dates.enumerated().map { index, d in "#\(index + 1) · " + (d.map { "到期：" + time($0) } ?? "接口未设置到期时间") }
            return [result("Claude · 重置次数", "\(dates.count) 次可用", lines, expanded)]
        } else if name == "claude" {
            guard let data = object(payload["extra_usage"]), let enabled = flag(data["is_enabled"]) else { throw QuotaError("Claude 未返回额外消费信息。") }
            var lines: [String] = []
            for (key, label) in [("monthly_limit", "月消费上限"), ("used_credits", "已消费额度"), ("utilization", "使用比例")] {
                if let value = number(data[key]), value >= 0 { lines.append(label + "：" + display(value) + (key == "utilization" ? "%" : "（接口计费单位）")) }
            }
            lines.append("消费上限不是钱包余额；金额单位未确认时保留接口计费单位。")
            return [result("Claude · 额外消费", enabled ? "已开启" : "未开启", lines)]
        } else if name == "mimo_balance" {
            guard payload["error"] == nil, let items = array(payload["data"]) else { throw QuotaError("MiMo 未返回有效用量或账单明细。") }
            var expanded: [String] = []
            let fields = action == "daily" ? [("consumed_amount", "消费金额"), ("request_count", "请求次数")] : [("original_amount", "原价"), ("discount_amount", "折扣减免"), ("gift_amount", "赠金抵扣"), ("final_paid_amount", "实付")]
            for raw in items {
                guard let item = object(raw) else { throw QuotaError("MiMo 明细格式无效。") }
                var parts = [String((text(item["date"]) ?? "日期未返回").prefix(32))]
                if action == "daily", let name = text(item["name"]) { parts.append(String(name.prefix(160))) }
                let currency = String((text(item["currency"]) ?? "").prefix(12))
                var hasValue = false
                for (key, label) in fields {
                    if let value = number(item[key]) {
                        hasValue = true
                        parts.append(label + " " + (key == "consumed_amount" ? String(format: "%.6f", value) : display(value)) + (key == "request_count" ? "" : " " + currency))
                    }
                }
                guard hasValue else { throw QuotaError("MiMo 明细缺少消费数值。") }
                expanded.append(parts.joined(separator: " · "))
            }
            return [result("MiMo · " + (action == "daily" ? "近7天日用量" : "近7天日账单"), "\(items.count) 条记录", ["日期范围为北京时间今天及前6天。"], expanded)]
        }
        throw QuotaError("接口没有返回可展示的附加信息；未推算数据。")
    }
}
