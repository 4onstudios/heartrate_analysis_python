import Foundation

struct HeartPyPeak: Decodable {
    let index: Int
    let timeSeconds: Double
    let value: Double
    let accepted: Bool
}

struct HeartPyResult: Decodable {
    let schemaVersion: Int
    let sampleRate: Double
    let sampleCount: Int
    let durationSeconds: Double
    let peaks: [HeartPyPeak]
    let rrIntervalsMs: [Double]
    let rrAccepted: [Bool]
    let rrIntervalsCleanMs: [Double]
    let measures: [String: Double?]
    let warnings: [String]
}

struct HeartPyHTTPError: Error {
    let statusCode: Int
    let responseBody: String
}

private struct HeartPyRequest: Encodable {
    let samples: [Double]
    let sampleRate: Double
}

// endpoint: your full HTTPS URL, e.g. https://api.example.com/v1/analyze.
// Requires an iOS version supporting URLSession's async API (iOS 15+).
func analyzeHeartRate(
    samples: [Double],
    sampleRate: Double,
    endpoint: URL,
    bearerToken: String? = nil
) async throws -> HeartPyResult {
    var request = URLRequest(url: endpoint)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if let token = bearerToken {
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    request.httpBody = try encoder.encode(HeartPyRequest(samples: samples, sampleRate: sampleRate))
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse else {
        throw URLError(.badServerResponse)
    }
    guard (200...299).contains(http.statusCode) else {
        throw HeartPyHTTPError(
            statusCode: http.statusCode,
            responseBody: String(data: data, encoding: .utf8) ?? ""
        )
    }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(HeartPyResult.self, from: data)
}
