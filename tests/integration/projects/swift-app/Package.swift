// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "SwiftApp",
    targets: [
        .target(
            name: "SwiftApp",
            path: "Sources/SwiftApp"
        ),
        .testTarget(
            name: "SwiftAppTests",
            dependencies: ["SwiftApp"],
            path: "Tests/SwiftAppTests"
        ),
    ]
)
