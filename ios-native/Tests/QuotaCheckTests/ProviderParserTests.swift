import XCTest
@testable import QuotaCheckCore

final class ProviderParserTests: XCTestCase {
    private func fixture(_ name: String) throws -> Any {
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures")!
        return try JSONSerialization.jsonObject(with: Data(contentsOf: url), options: [.fragmentsAllowed])
    }

    func testProviderFixtureOutput() throws {
        let cases = try fixture("providers-usage") as? [[String: Any]] ?? []
        XCTAssertGreaterThanOrEqual(cases.count, 9)
        for item in cases {
            let id = item["id"] as? String ?? ""
            let rows = try parseProvider(id: id, payload: item["payload"], sealed: false)
            let expected = item["expect"] as? [[String: Any]] ?? []
            XCTAssertEqual(rows.count, expected.count, id)
            for (index, row) in rows.enumerated() {
                let item = expected[index]
                if let used = item["used"] as? NSNumber { XCTAssertEqual(row.used, used.doubleValue, accuracy: 0.0001, id) }
                else { XCTAssertNil(row.used, id) }
                if let remaining = item["remaining"] as? NSNumber { XCTAssertEqual(row.remaining, remaining.doubleValue, accuracy: 0.0001, id) }
                else { XCTAssertNil(row.remaining, id) }
                if let title = item["title"] as? String { XCTAssertTrue(row.title.contains(title), id) }
                if let contains = item["contains"] as? String { XCTAssertTrue(row.details.contains(contains), id) }
            }
        }
    }
}
