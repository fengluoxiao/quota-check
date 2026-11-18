import Foundation
import CryptoKit
import Security
import QuotaVaultC

enum VaultFailure: Error, LocalizedError {
  case invalid, unsupported, windows, password, decrypt, random, kdf
  var errorDescription: String? {
    switch self {
    case .windows: return "此文件绑定 Windows 用户。请在桌面端另存为跨电脑文件后导入。"
    case .password: return "文件密码需要 12 至 1024 个字符。"
    case .decrypt: return "文件密码不正确、设备密钥不匹配或文件已损坏。"
    case .unsupported: return "此连接文件的版本或加密方式不受支持。"
    default: return "连接文件无效或无法处理。"
    }
  }
}
struct NativeVaultCodec {
  static let magic = Data([83,81,86,65,85,76,84,0])
  static let maxBytes = 2 * 1024 * 1024
  static func random(_ count: Int) throws -> Data {
    var bytes = [UInt8](repeating: 0, count: count)
    let status = bytes.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault, count, $0.baseAddress!) }
    guard status == errSecSuccess else { throw VaultFailure.random }; return Data(bytes)
  }
  static func key(mode: UInt8, secret: String, salt: Data) throws -> SymmetricKey {
    if mode == 2 {
      guard let d = Data(base64Encoded: secret), d.count == 32 else { throw VaultFailure.decrypt }; return SymmetricKey(data: d)
    }
    guard mode == 1 else { throw VaultFailure.unsupported }
    let count = secret.unicodeScalars.count
    guard count >= 12 && count <= 1024 else { throw VaultFailure.password }
    let password = Data(secret.utf8); var result = Data(count: 32)
    let code = result.withUnsafeMutableBytes { out in
      password.withUnsafeBytes { pwd in
        salt.withUnsafeBytes { saltBytes in
          qc_argon2id(pwd.bindMemory(to: UInt8.self).baseAddress!, password.count, saltBytes.bindMemory(to: UInt8.self).baseAddress!, salt.count, out.bindMemory(to: UInt8.self).baseAddress!, 32)
        }
      }
    }
    guard code == 0 else { throw VaultFailure.kdf }; return SymmetricKey(data: result)
  }
  static func append32(_ value: Int, to data: inout Data) {
    let n = UInt32(value); data.append(contentsOf: [UInt8(n >> 24), UInt8((n >> 16) & 255), UInt8((n >> 8) & 255), UInt8(n & 255)])
  }
  static func read32(_ data: Data, _ offset: Int) -> Int {
    let b = [UInt8](data); return Int(b[offset]) << 24 | Int(b[offset+1]) << 16 | Int(b[offset+2]) << 8 | Int(b[offset+3])
  }
  static func seal(_ plaintext: String, mode: UInt8, secret: String) throws -> Data {
    let plain = Data(plaintext.utf8)
    guard plain.count <= maxBytes / 2, mode == 1 || mode == 2 else { throw VaultFailure.invalid }
    let salt = try random(16), nonceData = try random(12)
    var header = magic; header.append(1); header.append(mode); append32(0, to: &header)
    header.append(salt); header.append(nonceData); append32(plain.count + 16, to: &header)
    let key = try key(mode: mode, secret: secret, salt: salt)
    let box = try AES.GCM.seal(plain, using: key, nonce: AES.GCM.Nonce(data: nonceData), authenticating: header)
    var file = header; file.append(box.ciphertext); file.append(box.tag); return file
  }
  static func open(_ data: Data, secret: String) throws -> String {
    guard data.count >= 62, data.count <= maxBytes, data.prefix(8) == magic else { throw VaultFailure.invalid }
    let bytes = [UInt8](data); guard bytes[8] == 1 else { throw VaultFailure.unsupported }
    let mode = bytes[9]; if mode == 0 { throw VaultFailure.windows }
    guard mode == 1 || mode == 2, read32(data, 10) == 0 else { throw VaultFailure.unsupported }
    let size = read32(data, 42); guard size >= 16, size + 46 == data.count else { throw VaultFailure.invalid }
    let header = data.prefix(46), salt = data.subdata(in: 14..<30), nonce = data.subdata(in: 30..<42)
    let key = try key(mode: mode, secret: secret, salt: salt)
    do {
      let box = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: nonce), ciphertext: data.subdata(in: 46..<(data.count-16)), tag: data.suffix(16))
      let plain = try AES.GCM.open(box, using: key, authenticating: header)
      guard let result = String(data: plain, encoding: .utf8) else { throw VaultFailure.invalid }; return result
    } catch { throw VaultFailure.decrypt }
  }
}
