"""Framework-independent adapter around HeartPy's existing peak detector."""

import math
from numbers import Real

import numpy as np

from ..exceptions import BadSignalWarning
from ..heartpy import process

MAX_SAMPLES = 300_000
MIN_DURATION_SECONDS = 5.0
MAX_DURATION_SECONDS = 600.0
MAX_SAMPLE_RATE = 5_000.0
MAX_BPM = 300.0
MIN_WINDOW_SIZE = 0.1
MAX_WINDOW_SIZE = 2.0


class InvalidSignalError(ValueError):
    """The input or its analysis settings are invalid."""


class AnalysisError(ValueError):
    """A valid input did not contain enough usable heartbeat information."""


def _number(value, name, lower, upper, inclusive_lower=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise InvalidSignalError("{} must be a finite number.".format(name))
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise InvalidSignalError("{} must be a finite number.".format(name)) from exc
    valid_lower = value >= lower if inclusive_lower else value > lower
    if not math.isfinite(value) or not valid_lower or value > upper:
        raise InvalidSignalError("{} is outside its supported range.".format(name))
    return value


def analyze_signal(
    samples,
    sample_rate,
    *,
    bpm_min=40.0,
    bpm_max=180.0,
    window_size=0.75,
    clean_rr=False,
    calc_freq=False,
):
    """Analyse one raw PPG/ECG amplitude array and return JSON-safe Python data.

    ``sample_rate`` is in Hz; samples must be evenly spaced, finite numbers.
    Peak indices are zero based. RR intervals and most HRV measures are in
    milliseconds; ``breathingrate`` is in Hz. Undefined measures are ``None``.
    This function does not need FastAPI and can be used by any Python backend.
    Input is limited to 300,000 samples and 5--600 seconds per call.
    """
    sample_rate = _number(sample_rate, "sample_rate", 0, MAX_SAMPLE_RATE)
    bpm_min = _number(bpm_min, "bpm_min", 0, MAX_BPM)
    bpm_max = _number(bpm_max, "bpm_max", 0, MAX_BPM)
    window_size = _number(
        window_size, "window_size", MIN_WINDOW_SIZE, MAX_WINDOW_SIZE, True
    )
    if bpm_min >= bpm_max:
        raise InvalidSignalError("bpm_min must be less than bpm_max.")
    if not isinstance(clean_rr, bool) or not isinstance(calc_freq, bool):
        raise InvalidSignalError("clean_rr and calc_freq must be booleans.")
    if isinstance(samples, (list, tuple)) and any(
        isinstance(value, (bool, np.bool_)) for value in samples
    ):
        raise InvalidSignalError("samples must contain numbers, not booleans.")
    try:
        data = np.asarray(samples)
    except (TypeError, ValueError) as exc:
        raise InvalidSignalError("samples must be a one-dimensional numeric array.") from exc
    if data.ndim != 1 or data.dtype.kind not in "iuf":
        raise InvalidSignalError("samples must be a one-dimensional numeric array.")
    if not 2 <= data.size <= MAX_SAMPLES:
        raise InvalidSignalError("samples must contain 2--300,000 values.")
    # Copy to isolate callers and concurrent requests from HeartPy processing.
    data = data.astype(np.float64, copy=True)
    if not np.all(np.isfinite(data)):
        raise InvalidSignalError("samples must contain only finite numbers.")
    duration = data.size / sample_rate
    if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
        raise InvalidSignalError("Provide 5--600 seconds of signal per request.")
    if int(window_size * sample_rate) < 1:
        raise InvalidSignalError("window_size must cover at least one sample.")
    if data.min() == data.max():
        raise AnalysisError("The signal is constant; no heartbeat can be detected.")

    try:
        # Never use shared working dictionaries between requests.
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            working, measures = process(
                data,
                sample_rate=sample_rate,
                windowsize=window_size,
                bpmmin=bpm_min,
                bpmmax=bpm_max,
                clean_rr=clean_rr,
                calc_freq=calc_freq,
                working_data={},
                measures={},
            )
    except (BadSignalWarning, ValueError, IndexError, ZeroDivisionError,
            FloatingPointError) as exc:
        raise AnalysisError(
            "No reliable heartbeat could be detected; check signal quality and BPM limits."
        ) from exc

    cleaned_rr = working["RR_list_cor"]
    if len(cleaned_rr) < 2 or not math.isfinite(float(measures["bpm"])):
        raise AnalysisError("Too few usable RR intervals remain after peak rejection.")
    removed = set(int(index) for index in working["removed_beats"])
    peaks = [
        {
            "index": int(index),
            "time_seconds": float(index / sample_rate),
            # Report the original amplitude, even if HeartPy shifted the baseline.
            "value": float(data[int(index)]),
            "accepted": bool(accepted) and int(index) not in removed,
        }
        for index, accepted in zip(working["peaklist"], working["binary_peaklist"])
    ]
    json_measures = {
        name: float(value) if math.isfinite(float(value)) else None
        for name, value in measures.items()
    }
    rr_accepted = [not bool(mask) for mask in working["RR_masklist"]]
    accepted_count = sum(peak["accepted"] for peak in peaks)
    messages = []
    if calc_freq and duration < 300:
        messages.append(
            "Frequency-domain estimates from recordings shorter than 5 minutes "
            "may be unreliable."
        )
    if any(value is None for value in json_measures.values()):
        messages.append("Some measures could not be estimated and are returned as null.")
    return {
        "schema_version": 1,
        "sample_rate": sample_rate,
        "sample_count": int(data.size),
        "duration_seconds": float(duration),
        "peaks": peaks,
        "rr_intervals_ms": [float(value) for value in working["RR_list"]],
        "rr_accepted": rr_accepted,
        "rr_intervals_clean_ms": [float(value) for value in cleaned_rr],
        "measures": json_measures,
        "quality": {
            "detected_peak_count": len(peaks),
            "accepted_peak_count": accepted_count,
            "rejected_peak_count": len(peaks) - accepted_count,
            "valid_rr_count": sum(rr_accepted),
            "rejected_rr_count": len(rr_accepted) - sum(rr_accepted),
        },
        "warnings": messages,
    }
