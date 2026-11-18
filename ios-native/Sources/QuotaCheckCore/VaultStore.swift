import Foundation
import Security

enum VaultStore {
    static let keychainService = "com.fengluoxiao.quotacheck.native.vault"
    static let keychainAccount = "vault-key"
    #if targetEnvironment(simulator)
    static let usesKeychain = false
    #else
    static let usesKeychain = true
    #endif

    private static func fallbackKeyURL() throws -> URL {
        let file = try storageURL()
        return file.deletingLastPathComponent().appendingPathComponent("native-key.sqkey")
    }

    static func storageURL() throws -> URL {
        let parent = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("QuotaCheck", isDirectory: true)
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        return parent.appendingPathComponent("connections.sqv")
    }

    static func generateKey() throws -> String {
        try NativeVaultCodec.random(32).base64EncodedString()
    }

    private static func keychainQuery(account: String = keychainAccount) -> [String: Any] {
        var query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: keychainService,
         kSecAttrAccount as String: account]
        return query
    }

    static func readKey(account: String = keychainAccount) throws -> String? {
        if !usesKeychain {
            var url = try fallbackKeyURL()
            guard FileManager.default.fileExists(atPath: url.path) else { return nil }
            return try String(contentsOf: url, encoding: .utf8)
        }
        var query = keychainQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw QuotaError("本机连接密钥不可用，请导入备份或清除本机连接。") }
        return String(data: data, encoding: .utf8)
    }

    static func writeKey(_ value: String, account: String = keychainAccount) throws {
        guard let data = value.data(using: .utf8) else { throw VaultFailure.invalid }
        if !usesKeychain {
            var url = try fallbackKeyURL()
            try data.write(to: url, options: [.atomic, .completeFileProtection])
            var values = URLResourceValues(); values.isExcludedFromBackup = true
            try url.setResourceValues(values)
            return
        }
        var query = keychainQuery(account: account)
        let status = SecItemAdd(query as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let update: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
            let updateStatus = SecItemUpdate(query as CFDictionary, update as CFDictionary)
            guard updateStatus == errSecSuccess else { throw VaultFailure.invalid }
        } else if status != errSecSuccess { throw VaultFailure.invalid }
    }

    static func deleteKey(account: String = keychainAccount) {
        if !usesKeychain {
            if let url = try? fallbackKeyURL(), FileManager.default.fileExists(atPath: url.path) {
                try? FileManager.default.removeItem(at: url)
            }
            return
        }
        SecItemDelete(keychainQuery(account: account) as CFDictionary)
    }

    static func readStorage() throws -> Data? {
        let url = try storageURL()
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let data = try Data(contentsOf: url)
        guard data.count <= NativeVaultCodec.maxBytes else { throw VaultFailure.invalid }
        return data
    }

    static func writeStorage(_ data: Data) throws {
        guard data.count <= NativeVaultCodec.maxBytes else { throw VaultFailure.invalid }
        var url = try storageURL()
        try data.write(to: url, options: [.atomic, .completeFileProtection])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try url.setResourceValues(values)
    }

    static func deleteStorage() throws {
        let url = try storageURL()
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }

    static func load() throws -> VaultData {
        guard let blob = try readStorage() else { return freshVault() }
        guard let key = try readKey() else { throw QuotaError("本机连接密钥不可用，请导入备份或清除本机连接。") }
        let plaintext = try NativeVaultCodec.open(blob, secret: key)
        let decoded = try decodeJSON(plaintext)
        return try validateVault(decoded)
    }

    static func save(_ value: VaultData, replace: Bool = false) throws {
        let validated = try validateVault(value.jsonValue())
        var key = try readKey()
        if key == nil {
            if (try readStorage()) != nil && !replace {
                throw QuotaError("本机连接无法解密，请先导入备份或清除连接。")
            }
            key = try generateKey()
            try writeKey(key!)
        }
        let blob = try NativeVaultCodec.seal(try encodeJSON(validated.jsonValue()), mode: 2, secret: key!)
        try writeStorage(blob)
    }

    static func clear() throws {
        try deleteStorage()
        deleteKey()
    }
}
