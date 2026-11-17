import Foundation
import CryptoKit

enum NativeHashCodec {
  static func sha256(_ text: String) throws -> String {
    guard text.utf8.count <= 2_000_000 else { throw VaultFailure.invalid }
    return SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
  }
  static func hmacSHA256(_ keyHex: String, _ message: String) throws -> String {
    guard !keyHex.isEmpty, keyHex.count <= 65536, keyHex.count % 2 == 0,
          keyHex.utf8.allSatisfy({ (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }),
          message.utf8.count <= 2_000_000 else { throw VaultFailure.invalid }
    var bytes = [UInt8](); var index = keyHex.startIndex
    while index < keyHex.endIndex {
      let next = keyHex.index(index, offsetBy: 2)
      guard let byte = UInt8(keyHex[index..<next], radix: 16) else { throw VaultFailure.invalid }
      bytes.append(byte); index = next
    }
    return HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: SymmetricKey(data: Data(bytes))).map { String(format: "%02x", $0) }.joined()
  }
}
