import XCTest
import Security
@testable import QuotaCheckCore

final class VaultStoreTests: XCTestCase {
    func testKeychainCreationReplacementAndCiphertextRecovery() throws {
        XCTAssertTrue(VaultStore.usesKeychain, "This test must exercise the actual Keychain backend.")
        let account = "native-import-test-" + UUID().uuidString
        defer { VaultStore.deleteKey(account: account) }
        XCTAssertNil(try VaultStore.readKey(account: account))

        let firstKey = try VaultStore.generateKey()
        try VaultStore.writeKey(firstKey, account: account)
        XCTAssertEqual(try VaultStore.readKey(account: account), firstKey)
        let storedKey = try XCTUnwrap(VaultStore.readKey(account: account))
        let blob = try NativeVaultCodec.seal("imported-connection", mode: 2, secret: firstKey)
        XCTAssertEqual(try NativeVaultCodec.open(blob, secret: storedKey), "imported-connection")

        let replacement = try VaultStore.generateKey()
        try VaultStore.writeKey(replacement, account: account)
        XCTAssertEqual(try VaultStore.readKey(account: account), replacement)
        VaultStore.deleteKey(account: account)
        XCTAssertNil(try VaultStore.readKey(account: account))
    }

    func testMalformedLegacyKeyCanBeReplacedByImport() throws {
        let account = "native-import-recovery-" + UUID().uuidString
        defer { VaultStore.deleteKey(account: account) }
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: VaultStore.keychainService,
            kSecAttrAccount as String: account]
        var item = query
        item[kSecValueData as String] = Data()
        XCTAssertEqual(SecItemAdd(item as CFDictionary, nil), errSecSuccess)
        XCTAssertNil(try VaultStore.readKey(account: account))
        let key = try VaultStore.generateKey()
        try VaultStore.writeKey(key, account: account)
        XCTAssertEqual(try VaultStore.readKey(account: account), key)
    }
}
