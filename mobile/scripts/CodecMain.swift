import Foundation

@main struct CodecCommand {
  static func main() async {
    do {
      let input=FileHandle.standardInput.readDataToEndOfFile()
      guard let request=try JSONSerialization.jsonObject(with: input) as? [String:Any],let op=request["op"] as? String else { throw VaultFailure.invalid }
      var result:[String:Any]=[:]
      if op=="seal" {
        let data=try NativeVaultCodec.seal(request["plaintext"] as? String ?? "",mode:UInt8(request["mode"] as? Int ?? 1),secret:request["secret"] as? String ?? "")
        result=["ok":true,"blob":data.base64EncodedString()]
      } else if op=="open" {
        guard let data=Data(base64Encoded:request["blob"] as? String ?? "") else { throw VaultFailure.invalid }
        result=["ok":true,"plaintext":try NativeVaultCodec.open(data,secret:request["secret"] as? String ?? "")]
      } else if op=="http" {
        let response=try await SecureHTTP.perform(url:request["url"] as? String ?? "",method:request["method"] as? String ?? "GET",headers:request["headers"] as? [String:String] ?? [:],body:request["body"] as? String)
        result=["ok":true,"status":response.status,"body":response.body]
      } else { throw VaultFailure.invalid }
      FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]))
    } catch {
      let result:[String:Any]=["ok":false,"error":"Native operation rejected"]
      FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject:result))
      exit(1)
    }
  }
}
