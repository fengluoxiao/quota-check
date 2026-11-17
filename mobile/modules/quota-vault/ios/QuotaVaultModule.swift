import ExpoModulesCore
import Foundation

public class QuotaVaultModule: Module {
  private func location() throws -> URL {
    let parent = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("QuotaCheck", isDirectory: true)
    try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
    return parent.appendingPathComponent("connections.sqv")
  }
  public func definition() -> ModuleDefinition {
    Name("QuotaVault")
    Function("sha256") { (text: String) throws -> String in try NativeHashCodec.sha256(text) }
    Function("hmacSHA256") { (keyHex: String, text: String) throws -> String in try NativeHashCodec.hmacSHA256(keyHex, text) }
    Function("generateKey") { () throws -> String in try NativeVaultCodec.random(32).base64EncodedString() }
    AsyncFunction("seal") { (plaintext: String, mode: Int, secret: String) throws -> String in
      guard mode == 1 || mode == 2 else { throw VaultFailure.unsupported }
      return try NativeVaultCodec.seal(plaintext, mode: UInt8(mode), secret: secret).base64EncodedString()
    }
    AsyncFunction("open") { (blob: String, secret: String) throws -> String in
      guard let data = Data(base64Encoded: blob) else { throw VaultFailure.invalid }
      return try NativeVaultCodec.open(data, secret: secret)
    }
    Function("readStorage") { () throws -> String? in
      let url = try self.location(); guard FileManager.default.fileExists(atPath: url.path) else { return nil }
      let data = try Data(contentsOf: url); guard data.count <= NativeVaultCodec.maxBytes else { throw VaultFailure.invalid }
      return data.base64EncodedString()
    }
    AsyncFunction("writeStorage") { (blob: String) throws in
      guard let data = Data(base64Encoded: blob), data.count <= NativeVaultCodec.maxBytes else { throw VaultFailure.invalid }
      var url = try self.location(); try data.write(to: url, options: [.atomic, .completeFileProtection])
      var values = URLResourceValues(); values.isExcludedFromBackup = true; try url.setResourceValues(values)
    }
    AsyncFunction("deleteStorage") { () throws in let url = try self.location(); if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) } }
    AsyncFunction("request") { (url: String, method: String, headers: [String:String], body: String?) async throws -> [String:Any] in
      let result = try await SecureHTTP.perform(url: url, method: method, headers: headers, body: body)
      return ["status": result.status, "body": result.body]
    }
  }
}
