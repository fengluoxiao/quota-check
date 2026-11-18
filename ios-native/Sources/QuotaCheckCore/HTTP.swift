import Foundation

struct RequestSpec {
    let url: String
    let method: String
    let headers: [String: String]
    let body: String?
}

struct HTTPResponse {
    let status: Int
    let body: String
}

typealias Transport = @Sendable (RequestSpec) async throws -> HTTPResponse

let nativeTransport: Transport = { request in
    let result = try await SecureHTTP.perform(
        url: request.url,
        method: request.method,
        headers: request.headers,
        body: request.body
    )
    return HTTPResponse(status: result.status, body: result.body)
}
