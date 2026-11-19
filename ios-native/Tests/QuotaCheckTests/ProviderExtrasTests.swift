import XCTest
import Security
@testable import QuotaCheckCore

final class ProviderExtrasTests: XCTestCase {
    func testSharedContractAndRedaction() throws {
        let url = Bundle.module.url(forResource: "extras-usage", withExtension: "json", subdirectory: "Fixtures")!
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [[String: Any]]
        for item in cases {
            let rows = try ProviderExtras.parse(item["provider"] as! String, item["action"] as! String, item["payload"], now: Date(timeIntervalSince1970: 1795046400))
            XCTAssertEqual(rows.count, item["count"] as? Int)
            XCTAssertTrue(rows[0].detail.contains(item["value"] as! String))
            XCTAssertEqual(rows[0].expandedLines?.count ?? 0, item["expanded"] as? Int)
            XCTAssertFalse(String(describing: rows).contains("never-export-handle"))
            XCTAssertNil(rows[0].used)
        }
    }

    func testMissingAndMalformedValuesRemainUnknown() throws {
        for name in ["glm", "claude", "mimo_balance", "ark_agent"] {
            for (action, _) in ProviderExtras.actions(name) { XCTAssertThrowsError(try ProviderExtras.parse(name, action, [:])) }
        }
        XCTAssertThrowsError(try ProviderExtras.parse("claude", "reset", ["cedar_ember": ["eligible": true, "grants": [["resets_left": true, "paused": false]]]]))
        XCTAssertThrowsError(try ProviderExtras.parse("mimo_balance", "daily", ["data": [["date": "2026-11-19", "name": "model"]]]))
        XCTAssertEqual(try ProviderExtras.parse("claude", "reset", ["cedar_ember": ["eligible": true, "grants": []]])[0].detail.components(separatedBy: "\n")[0], "0 次可用")
    }

    func testRequestsUseOnlyReadEndpoints() throws {
        var profile = Profile(kind: "glm"); profile.site = "cn"; profile.consoleToken = "Bearer console-only"
        let glm = try ProviderExtras.request("glm", "reset", profile)
        XCTAssertEqual(glm.headers["Authorization"], "Bearer console-only")
        XCTAssertEqual(glm.method, "GET")
        profile.kind = "mimo_balance"; profile.secret = "test-only"
        let request = try ProviderExtras.request("mimo_balance", "daily", profile, now: Date(timeIntervalSince1970: 1795021200))
        XCTAssertTrue(request.url.contains("start_date=2026-11-13&end_date=2026-11-19"))
        profile.kind = "ark_agent"; profile.secret2 = "test-only"
        let ark = try ProviderExtras.request("ark_agent", "subscription", profile)
        XCTAssertTrue(ark.url.contains("Action=ListSubscribeTrade"))
        XCTAssertEqual(ark.body, "{\"ResourceNames\":[\"RealAgentPlanPersonal\"]}")
    }

    func testGlmConsoleCredentialRoundTripAndSealing() throws {
        let raw: JSON = ["version": 1, "source": 0, "profiles": ["glm": ["site": "cn", "key": "test-key", "console_token": "Bearer test-console", "sealed": false]]]
        let vault = try validateVault(raw)
        XCTAssertEqual(try validateVault(vault.jsonValue()).profiles["glm"]?.consoleToken, "Bearer test-console")
        XCTAssertThrowsError(try exportOwned(lockImported(raw)))
    }

    func testLegacyExpoKeychainQueryUsesOriginalAliasesAndDataAccount() {
        let queries = VaultStore.legacyExpoQueries()
        XCTAssertEqual(queries.count, 2)
        XCTAssertEqual(queries[0][kSecAttrService as String] as? String, "com.fengluoxiao.quotacheck.vault:no-auth")
        XCTAssertEqual(queries[1][kSecAttrService as String] as? String, "com.fengluoxiao.quotacheck.vault")
        XCTAssertNotNil(queries[0][kSecAttrAccount as String] as? Data)
        XCTAssertEqual(queries[0][kSecAttrAccount as String] as? Data, queries[0][kSecAttrGeneric as String] as? Data)
    }
}
