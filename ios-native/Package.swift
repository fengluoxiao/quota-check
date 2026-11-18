// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "QuotaCheckNative",
    platforms: [.iOS(.v17), .macOS(.v14)],
    targets: [
        .target(
            name: "QuotaVaultC",
            path: "Sources/QuotaVaultC",
            publicHeadersPath: ".",
            cSettings: [.define("ARGON2_NO_THREADS"), .headerSearchPath("vendor/argon2/include")]
        ),
        .target(
            name: "QuotaCheckCore",
            dependencies: ["QuotaVaultC"],
            path: "Sources/QuotaCheckCore"
        ),
        .executableTarget(
            name: "QuotaCheckApp",
            dependencies: ["QuotaCheckCore"],
            path: "Sources/QuotaCheckApp"
        ),
        .testTarget(
            name: "QuotaCheckTests",
            dependencies: ["QuotaCheckCore"],
            path: "Tests/QuotaCheckTests",
            resources: [.copy("Fixtures")]
        ),
    ]
)
