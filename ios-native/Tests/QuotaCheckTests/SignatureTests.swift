import XCTest
@testable import QuotaCheckCore

final class SignatureTests: XCTestCase {
    func testVolcengineSignatureMatchesOfficialVector() throws {
        var profile = Profile(kind: "ark_agent")
        profile.secret = "AKIDEXAMPLE/20261117/cn-beijing/ark/request"
        profile.secret2 = "test-only-secret-key"
        profile.sessionToken = "test-only-session"
        let headers = try signVolc(profile: profile, hash: NativeHash(), stamp: "20261117T010203Z")
        XCTAssertEqual(headers["X-Content-Sha256"], "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
        XCTAssertTrue(headers["Authorization"]?.contains("Credential=AKIDEXAMPLE/20261117/cn-beijing/ark/request") == true)
        XCTAssertTrue(headers["Authorization"]?.hasSuffix("Signature=955d3d29658a18c554d8c9126b59aa3431290019bcac64b64255305511934f22") == true)
    }
}
