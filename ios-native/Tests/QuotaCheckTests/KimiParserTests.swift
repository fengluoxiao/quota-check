import XCTest
@testable import QuotaCheckCore

final class KimiParserTests: XCTestCase {
    func testKimiFixtureOutput() throws {
        let url = Bundle.module.url(forResource: "kimi-usage", withExtension: "json", subdirectory: "Fixtures")!
        let cases = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]] ?? []
        XCTAssertGreaterThanOrEqual(cases.count, 8)
        for test in cases {
            let rows = try kimiWindows(test["payload"])
            let expected = test["expected"] as? [[String: Any]] ?? []
            XCTAssertEqual(rows.count, expected.count, test["name"] as? String ?? "")
            for (index, row) in rows.enumerated() {
                let item = expected[index]
                XCTAssertEqual(row.title, item["title"] as? String ?? "", test["name"] as? String ?? "")
                let parts = item["parts"] as? [String] ?? []
                for part in parts { XCTAssertTrue(row.detail.contains(part), "\(test["name"] ?? "") \(part)") }
                if item["reset"] as? Bool == true { XCTAssertFalse(row.reset.isEmpty) }
            }
        }
    }
}
