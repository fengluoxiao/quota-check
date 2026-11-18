import Foundation

typealias JSON = [String: Any]

func object(_ value: Any?) -> JSON? {
    value as? JSON
}

func array(_ value: Any?) -> [Any]? {
    value as? [Any]
}

func text(_ value: Any?) -> String? {
    value as? String
}

func number(_ value: Any?, negative: Bool = false) -> Double? {
    guard !(value is Bool), let raw = value as? NSNumber else { return nil }
    let converted = raw.isBoolNumber ? raw.boolValue ? 1.0 : 0.0 : raw.doubleValue
    guard converted.isFinite, negative || converted >= 0 else { return nil }
    return converted
}

extension NSNumber {
    var isBoolNumber: Bool {
        let boolID = CFBooleanGetTypeID()
        return CFGetTypeID(self) == boolID
    }
}

func decodeJSON(_ body: String) throws -> Any {
    guard !body.isEmpty, let data = body.data(using: .utf8) else { throw QuotaError("接口没有返回有效 JSON。") }
    let value = try JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
    if let object = value as? JSON { return object }
    if let array = value as? [Any] { return array }
    throw QuotaError("接口响应格式异常。")
}

func display(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.numberStyle = .decimal
    formatter.maximumFractionDigits = 2
    formatter.minimumFractionDigits = 0
    return formatter.string(from: NSNumber(value: value)) ?? String(value)
}

func encodeJSON(_ value: Any) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    return String(data: data, encoding: .utf8) ?? ""
}

struct QuotaError: Error, LocalizedError {
    let message: String
    let status: Int
    let reason: String
    var errorDescription: String? { message }

    init(_ message: String, status: Int = 0, reason: String = "") {
        self.message = message
        self.status = status
        self.reason = reason
    }
}

struct NeedsOTP: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
