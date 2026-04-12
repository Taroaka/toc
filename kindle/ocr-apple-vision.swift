import AppKit
import Foundation
import Vision

let arguments = CommandLine.arguments
if arguments.count < 2 {
    fputs("usage: ocr-apple-vision.swift <image-path>\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: arguments[1])
guard let image = NSImage(contentsOf: imageURL) else {
    fputs("failed to load image\n", stderr)
    exit(1)
}

var rect = NSRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    fputs("failed to resolve cgImage\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["ja-JP", "en-US"]

do {
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])
    for observation in request.results ?? [] {
        if let candidate = observation.topCandidates(1).first {
            print(candidate.string)
        }
    }
} catch {
    fputs("ocr failed: \(error)\n", stderr)
    exit(1)
}
