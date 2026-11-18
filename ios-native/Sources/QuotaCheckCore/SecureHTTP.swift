import Foundation

struct NativeHTTPResult: Sendable { let status: Int; let body: String }
final class SecureHTTP: NSObject, URLSessionDataDelegate, URLSessionTaskDelegate, @unchecked Sendable {
  private var continuation: CheckedContinuation<NativeHTTPResult, Error>?
  private var bytes = Data(); private var status = 0; private var finished = false
  private var session: URLSession?
  static func perform(url: String, method: String, headers: [String:String], body: String?) async throws -> NativeHTTPResult {
    guard let target = URL(string: url), ["https","http"].contains(target.scheme?.lowercased() ?? ""), target.host != nil, target.user == nil, target.password == nil, ["GET","POST"].contains(method) else { throw URLError(.badURL) }
    let delegate = SecureHTTP()
    return try await withCheckedThrowingContinuation { continuation in
      delegate.continuation = continuation
      let config = URLSessionConfiguration.ephemeral; config.timeoutIntervalForRequest = 30; config.timeoutIntervalForResource = 45
      config.httpShouldSetCookies = false; config.urlCache = nil
      let session = URLSession(configuration: config, delegate: delegate, delegateQueue: nil); delegate.session = session
      var request = URLRequest(url: target); request.httpMethod = method
      for (name,value) in headers { request.setValue(value, forHTTPHeaderField: name) }
      if let body = body { request.httpBody = Data(body.utf8) }
      session.dataTask(with: request).resume()
    }
  }
  func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
  func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
    status = (response as? HTTPURLResponse)?.statusCode ?? 0; completionHandler(.allow)
  }
  func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
    if bytes.count + data.count > 8*1024*1024 { finish(.failure(URLError(.dataLengthExceedsMaximum))); dataTask.cancel(); return }; bytes.append(data)
  }
  func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
    if error != nil { finish(.failure(NSError(domain: "QuotaHTTP", code: 1, userInfo: [NSLocalizedDescriptionKey:"连接失败或超时，请检查网络、证书和站点地址。"]))) }
    else if let text = String(data: bytes, encoding: .utf8) { finish(.success(NativeHTTPResult(status: status, body: text))) }
    else { finish(.failure(URLError(.cannotDecodeContentData))) }
  }
  private func finish(_ result: Result<NativeHTTPResult,Error>) {
    guard !finished else { return }; finished = true; continuation?.resume(with: result); continuation = nil
    session?.invalidateAndCancel(); session = nil
  }
}
