import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

// Call on a background thread. Add android.permission.INTERNET to your manifest.
// endpoint: your full HTTPS URL, e.g. https://api.example.com/v1/analyze.
// Read result.getJSONArray("peaks") and result.getJSONObject("measures").
// Undefined measures are JSONObject.NULL; check measures.isNull("rmssd").
fun analyzeHeartRate(
    samples: DoubleArray,
    sampleRate: Double,
    endpoint: URL,
    bearerToken: String? = null
): JSONObject {
    val amplitudes = JSONArray()
    samples.forEach { amplitudes.put(it) }
    val body = JSONObject()
        .put("samples", amplitudes)
        .put("sample_rate", sampleRate)
        .toString().toByteArray(Charsets.UTF_8)
    val connection = endpoint.openConnection() as HttpURLConnection
    try {
        connection.requestMethod = "POST"
        connection.connectTimeout = 15_000
        connection.readTimeout = 60_000
        connection.doOutput = true
        connection.setRequestProperty("Content-Type", "application/json")
        if (bearerToken != null) {
            connection.setRequestProperty("Authorization", "Bearer $bearerToken")
        }
        connection.setFixedLengthStreamingMode(body.size)
        connection.outputStream.use { it.write(body) }
        val status = connection.responseCode
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
        if (status !in 200..299) throw IOException("HTTP $status: $response")
        return JSONObject(response)
    } finally {
        connection.disconnect()
    }
}
