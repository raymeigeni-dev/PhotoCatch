import Foundation
import RealityKit

struct ProbeResult: Encodable {
    let ok: Bool
    let supported: Bool
    let macOSVersion: String
    let architecture: String
    let inputDirectory: String?
    let imageCount: Int?
    let outputPath: String?
    let outputBytes: Int64?
    let error: String?
}

func emit(_ result: ProbeResult, exitCode: Int32) -> Never {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    if let data = try? encoder.encode(result), let value = String(data: data, encoding: .utf8) {
        print(value)
    } else {
        print("{\"ok\":false,\"error\":\"Could not encode result\"}")
    }
    exit(exitCode)
}

func imageFiles(in directory: URL) throws -> [URL] {
    try FileManager.default.contentsOfDirectory(
        at: directory,
        includingPropertiesForKeys: [.isRegularFileKey],
        options: [.skipsHiddenFiles]
    )
    .filter { ["jpg", "jpeg", "png", "heic", "tif", "tiff"].contains($0.pathExtension.lowercased()) }
    .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
}

@main
struct PhotoCatchAppleCapture {
    static func main() async {
        let args = Array(CommandLine.arguments.dropFirst())
        let version = ProcessInfo.processInfo.operatingSystemVersion
        let versionString = "\(version.majorVersion).\(version.minorVersion).\(version.patchVersion)"
        #if arch(arm64)
        let architecture = "arm64"
        #elseif arch(x86_64)
        let architecture = "x86_64"
        #else
        let architecture = "unknown"
        #endif

        guard PhotogrammetrySession.isSupported else {
            emit(ProbeResult(ok: false, supported: false, macOSVersion: versionString,
                architecture: architecture, inputDirectory: nil, imageCount: nil,
                outputPath: nil, outputBytes: nil,
                error: "RealityKit PhotogrammetrySession is not supported on this Mac."), exitCode: 2)
        }
        guard args.count == 2 else {
            emit(ProbeResult(ok: false, supported: true, macOSVersion: versionString,
                architecture: architecture, inputDirectory: nil, imageCount: nil,
                outputPath: nil, outputBytes: nil,
                error: "Usage: photocatch-apple-capture <image-directory> <output.usdz>"), exitCode: 64)
        }

        let input = URL(fileURLWithPath: args[0], isDirectory: true).standardizedFileURL
        let output = URL(fileURLWithPath: args[1]).standardizedFileURL
        do {
            var isDirectory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: input.path, isDirectory: &isDirectory),
                  isDirectory.boolValue else {
                throw NSError(domain: "PhotoCatchAppleCapture", code: 10,
                    userInfo: [NSLocalizedDescriptionKey: "Input path is not a directory"])
            }
            let images = try imageFiles(in: input)
            guard images.count >= 3 else {
                throw NSError(domain: "PhotoCatchAppleCapture", code: 11,
                    userInfo: [NSLocalizedDescriptionKey: "At least 3 supported image files are required"])
            }
            guard !output.path.hasPrefix(input.path + "/"), output.path != input.path else {
                throw NSError(domain: "PhotoCatchAppleCapture", code: 12,
                    userInfo: [NSLocalizedDescriptionKey: "Output must be outside the input image directory"])
            }
            try FileManager.default.createDirectory(
                at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
            if FileManager.default.fileExists(atPath: output.path) {
                try FileManager.default.removeItem(at: output)
            }

            var configuration = PhotogrammetrySession.Configuration()
            configuration.sampleOrdering = .sequential
            configuration.featureSensitivity = .high
            configuration.isObjectMaskingEnabled = true
            let session = try PhotogrammetrySession(input: input, configuration: configuration)
            let request = PhotogrammetrySession.Request.modelFile(url: output, detail: .full)
            try session.process(requests: [request])

            var requestFailure: String?
            for try await event in session.outputs {
                print(String(describing: event))
                if case .requestError(_, let error) = event {
                    requestFailure = error.localizedDescription
                }
                if case .processingCancelled = event {
                    requestFailure = requestFailure ?? "Photogrammetry processing was cancelled."
                    break
                }
                if case .processingComplete = event { break }
            }
            if let requestFailure {
                throw NSError(domain: "PhotoCatchAppleCapture", code: 20,
                    userInfo: [NSLocalizedDescriptionKey: requestFailure])
            }
            let attrs = try FileManager.default.attributesOfItem(atPath: output.path)
            let bytes = (attrs[.size] as? NSNumber)?.int64Value ?? 0
            guard bytes > 0 else {
                throw NSError(domain: "PhotoCatchAppleCapture", code: 21,
                    userInfo: [NSLocalizedDescriptionKey: "Object Capture produced no usable output"])
            }
            emit(ProbeResult(ok: true, supported: true, macOSVersion: versionString,
                architecture: architecture, inputDirectory: input.path, imageCount: images.count,
                outputPath: output.path, outputBytes: bytes, error: nil), exitCode: 0)
        } catch {
            emit(ProbeResult(ok: false, supported: true, macOSVersion: versionString,
                architecture: architecture, inputDirectory: input.path, imageCount: nil,
                outputPath: output.path, outputBytes: nil, error: error.localizedDescription), exitCode: 1)
        }
    }
}
