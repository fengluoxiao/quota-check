import XCTest
@testable import QuotaCheckCore

final class CodecTests: XCTestCase {
    func testNativeHashAndPortableVaultRoundTrip() throws {
        XCTAssertEqual(try NativeHashCodec.sha256("quota-check"), "d80211816271a3ca9c788e8be5c52c0e62c76b85f8eea3564d2860846641a928")
        XCTAssertEqual(try NativeHashCodec.hmacSHA256(keyHex: "74657374", message: "quota-check"), "3792c792c75b5f8ca269a1a30c792c850f815b9cb2701a671a46c1401fa732db")
        let key = try NativeVaultCodec.random(32).base64EncodedString()
        let vault = VaultData(source: 2, profiles: ["kimi": Profile(kind: "kimi", key: "test-key", sealed: false)])
        let plaintext = try encodeJSON(vault.jsonValue())
        let sealed = try NativeVaultCodec.seal(plaintext, mode: 1, secret: key)
        XCTAssertEqual(try NativeVaultCodec.open(sealed, secret: key), plaintext)
        XCTAssertThrowsError(try NativeVaultCodec.open(sealed, secret: try NativeVaultCodec.random(32).base64EncodedString()))
    }
}
