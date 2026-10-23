// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PhotoCatchAppleObjectCapture",
    platforms: [.macOS(.v12)],
    products: [
        .executable(name: "photocatch-apple-capture", targets: ["PhotoCatchAppleCapture"])
    ],
    targets: [
        .executableTarget(
            name: "PhotoCatchAppleCapture",
            linkerSettings: [.linkedFramework("RealityKit")]
        )
    ]
)
