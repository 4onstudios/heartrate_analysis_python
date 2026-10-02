# HeartPy as an installable Python backend package

The package provides two interfaces: a regular Python function for any backend
framework, and an optional FastAPI service that native iOS/Android clients can
call. Both return the same JSON-compatible analysis result. No plotting, files,
or database are needed for a request.

## Install

Use Python 3.10 or newer. Apply the patch at the repository root, then install
from that checkout into your backend's environment:

```bash
git apply --check /path/to/heartpy-backend.patch
git apply /path/to/heartpy-backend.patch
python -m pip install .
```

The normal installation provides `heartpy.backend.analyze_signal`. If you want
the HTTP adapter, install its extra instead:

```bash
python -m pip install ".[backend]"
```

This is a fork-specific addition, not an already-published PyPI feature.
Build an installable wheel for another Python backend environment with:

```bash
python -m pip install build
python -m build
python -m pip install "dist/heartpy-1.2.9-py3-none-any.whl[backend]"
```

Your existing `heartpy.process()` calls still work. The new adapter adds input
validation and translates NumPy results into plain Python values.

## Import from your existing backend

```python
import heartpy as hp
from heartpy.backend import analyze_signal, AnalysisError, InvalidSignalError

samples, _ = hp.load_exampledata(0)
result = analyze_signal(samples, sample_rate=100, clean_rr=True)
# Return result from your Django, Flask, FastAPI, or other Python route.
```

Catch `InvalidSignalError` for invalid input and `AnalysisError` when the signal
cannot yield usable heartbeats. Each call uses its own working dictionaries and
copies the input array. If you call the function from an async route, run it in
your framework's thread pool so analysis does not block its event loop.

To mount the supplied HTTP service inside a FastAPI backend:

```python
from fastapi import FastAPI
from heartpy.backend import create_app

app = FastAPI()
app.mount("/heart", create_app())
```

That exposes `/heart/v1/analyze`, `/heart/health`, and `/heart/docs`. A mounted
sub-app does not inherit the parent app's route dependencies; protect the mount
with your authentication middleware or pass an `api_key` to `create_app()`.

## Run the standalone API

```bash
python -m heartpy.backend --host 0.0.0.0 --port 8000
# Equivalent installed command:
heartpy-backend --host 0.0.0.0 --port 8000
```

The default host is `127.0.0.1`. Binding `0.0.0.0` allows access through the
server's network address. A physical phone uses that address, not the phone's
own `localhost`. Production mobile apps should call your backend's HTTPS URL.
For multiple worker processes, add `--workers 2`.

- `GET /health`: public liveness check, `{"status":"ok"}`.
- `POST /v1/analyze`: analyze a recording.
- `GET /docs`: interactive OpenAPI documentation.
- `GET /openapi.json`: schema for generating API clients.

Optional server configuration:

```bash
export HEARTPY_API_KEY="your-server-token"
export HEARTPY_CORS_ORIGINS="https://app.example.com"
python -m heartpy.backend --host 0.0.0.0 --port 8000
```

With a key configured, analysis requests require
`Authorization: Bearer your-server-token`. No key delegates authentication to
the hosting backend. For a public mobile app, authenticate users in your own
backend; do not embed a shared server secret in the app. CORS is disabled by
default and is only needed for browser clients, not native iOS or Android.
You can pass `api_key="..."` and `allowed_origins=["https://app.example.com"]`
directly to `create_app()` instead of using environment variables.

## Request

Send a single channel of **raw, evenly sampled PPG/ECG amplitudes**, not BPM
values, image pixels, or precomputed RR intervals. Supply the actual sensor
sampling rate in Hz. Resample irregular recordings before submitting them.

```json
{
  "samples": [530, 518, 506, 496, 488],
  "sample_rate": 100,
  "bpm_min": 40,
  "bpm_max": 180,
  "window_size": 0.75,
  "clean_rr": false,
  "calc_freq": false
}
```

The five samples above illustrate the format; a real request needs 5--600
seconds of data, such as at least 500 samples at 100 Hz. JSON numbers must be
finite. Strings, booleans in the sample array, unknown fields, and nested
sample arrays are rejected.

| Field | Required | Meaning |
| --- | --- | --- |
| `samples` | Yes | Array of raw amplitudes; at most 300,000 values. |
| `sample_rate` | Yes | Positive sampling rate, at most 5,000 Hz. |
| `bpm_min` | No | Lower bound for peak fitting; default 40, greater than 0. |
| `bpm_max` | No | Upper bound for peak fitting; default 180, at most 300. Must exceed `bpm_min`. |
| `window_size` | No | Rolling-mean window in seconds, 0.1--2.0; default 0.75. Must cover at least one sample. |
| `clean_rr` | No | Apply HeartPy's additional quotient-filter RR cleaning; default false. |
| `calc_freq` | No | Compute frequency-domain HRV measures using Welch; default false. |

The HTTP service also rejects request bodies larger than 8 MiB, including
streamed bodies without a `Content-Length`. Recordings are independent batches,
not a persistent streaming session. Each recording starts its own timeline at
zero. The service keeps no patient records or request results. Configure your
hosting backend's authentication and request-rate controls for public access.

## Response

The following shows an abbreviated response for the included example recording:

```json
{
  "schema_version": 1,
  "sample_rate": 100.0,
  "sample_count": 2483,
  "duration_seconds": 24.83,
  "peaks": [
    {"index": 63, "time_seconds": 0.63, "value": 795.0, "accepted": true}
  ],
  "rr_intervals_ms": [1020.0, 990.0],
  "rr_accepted": [true, true],
  "rr_intervals_clean_ms": [1020.0, 990.0],
  "measures": {"bpm": 58.898847631242, "rmssd": 64.73723110319973},
  "quality": {
    "detected_peak_count": 24,
    "accepted_peak_count": 24,
    "rejected_peak_count": 0,
    "valid_rr_count": 23,
    "rejected_rr_count": 0
  },
  "warnings": []
}
```

`index` refers to the zero-based input sample. `time_seconds = index /
sample_rate`. `value` is its original amplitude, even if HeartPy shifted a
negative baseline internally. `accepted` reflects HeartPy's beat rejection,
including additional removals made by `clean_rr`.

`rr_intervals_ms[i]` spans `peaks[i]` to `peaks[i + 1]`.
`rr_accepted[i]` indicates whether that interval contributes to the measures;
`rr_intervals_clean_ms` contains the intervals retained for computation.
Use the RR mask for interval acceptance instead of reconstructing it from beat
flags. `quality` reports counts, not a clinical confidence score.

`measures` retains HeartPy's keys: `bpm`, `ibi`, `sdnn`, `sdsd`, `rmssd`,
`pnn20`, `pnn50`, `hr_mad`, `sd1`, `sd2`, `s`, `sd1/sd2`, and
`breathingrate`. RR-related time measures are in milliseconds, `s` is in
ms squared, and `breathingrate` is in Hz. The pNN measures are proportions,
not percentages. With `calc_freq=true`, additional keys include `vlf`, `lf`,
`hf`, and `lf/hf`. Undefined or infinite measures are JSON `null`, never NaN
or Infinity. `warnings` explains unavailable measures and short recordings
used for frequency estimates. These are signal estimates, not diagnoses.

## Errors

Errors use a JSON `error` object:

```json
{"error":{"code":"bad_signal","message":"The signal is constant; no heartbeat can be detected."}}
```

| HTTP status | Code | Meaning |
| --- | --- | --- |
| 401 | `unauthorized` | Missing or incorrect token when a server key is enabled. |
| 413 | `request_too_large` | Body exceeds 8 MiB. |
| 422 | `invalid_request` | Invalid JSON, fields, limits, or analysis settings. Includes `fields` with paths and messages. |
| 422 | `invalid_signal` | Input rejected by the Python analysis adapter. |
| 422 | `bad_signal` | No usable heartbeat or too few valid intervals after rejection. |
| 500 | `internal_error` | Unexpected server failure; internal details are not returned. |

## Client examples

Run a real request against the local service:

```bash
python examples/backend/client.py http://127.0.0.1:8000/v1/analyze
```

The client uses the packaged example recording. It reads `HEARTPY_API_KEY`
when testing a key-protected service. To generate a body for curl:

```bash
python -c 'import heartpy as hp,json; x,_=hp.load_exampledata(0); print(json.dumps({"samples":x.tolist(),"sample_rate":100}))' > request.json
curl --fail-with-body http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' --data-binary @request.json
```

Native client helpers are in
[`HeartPyClient.swift`](../examples/backend/HeartPyClient.swift) and
[`HeartPyClient.kt`](../examples/backend/HeartPyClient.kt). Pass your sensor
samples, actual sample rate, and full HTTPS analysis endpoint. Both helpers
send JSON, optionally attach a user bearer token, and check the HTTP status.
The Swift helper uses async `URLSession`; run the Android helper on a
background thread, and declare `android.permission.INTERNET` in the app's
manifest. The examples do not acquire sensor samples or implement login.

## Development checks

```bash
python -m pip install ".[backend,dev]"
python -m pytest -q
python -m build
```

Tests cover the bundled clean and noisy recordings, rejection masks, request
isolation, non-finite inputs/results, body limits, authentication, CORS, and
mounting the API in another backend.
