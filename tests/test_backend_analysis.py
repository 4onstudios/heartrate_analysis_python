import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

import heartpy as hp
from heartpy.backend import AnalysisError, InvalidSignalError, analyze_signal


def test_reference_recording_peaks_and_units(signal):
    result = analyze_signal(signal, 100)
    assert result["schema_version"] == 1
    assert result["sample_count"] == 2483
    assert result["duration_seconds"] == 24.83
    assert result["measures"]["bpm"] == pytest.approx(58.898847631242)
    assert [peak["index"] for peak in result["peaks"][:5]] == [63, 165, 264, 360, 460]
    assert result["peaks"][0] == {
        "index": 63, "time_seconds": 0.63, "value": float(signal[63]), "accepted": True
    }
    assert result["rr_intervals_ms"][:5] == [1020, 990, 960, 1000, 1050]
    assert len(result["rr_intervals_ms"]) == len(result["peaks"]) - 1
    assert len(result["rr_accepted"]) == len(result["rr_intervals_ms"])
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("clean", [False, True])
def test_noisy_recording_retains_heartpy_rejection_and_metrics(clean):
    signal, timer = hp.load_exampledata(1)
    rate = hp.get_samplerate_mstimer(timer)
    working, measures = hp.process(signal.copy(), rate, clean_rr=clean)
    result = analyze_signal(signal, rate, clean_rr=clean)
    assert result["measures"]["bpm"] == pytest.approx(measures["bpm"])
    assert result["rr_intervals_clean_ms"] == list(working["RR_list_cor"])
    assert result["rr_accepted"] == [mask == 0 for mask in working["RR_masklist"]]
    removed = set(working["removed_beats"])
    assert any(not peak["accepted"] for peak in result["peaks"])
    for peak, index, flag in zip(result["peaks"], working["peaklist"], working["binary_peaklist"]):
        assert peak["index"] == index
        assert peak["accepted"] == (bool(flag) and index not in removed)
    assert result["quality"]["valid_rr_count"] == len(result["rr_intervals_clean_ms"])


def test_negative_baseline_values_and_input_are_preserved(signal):
    signal = signal - 1500
    original = signal.copy()
    result = analyze_signal(signal, 100)
    np.testing.assert_array_equal(signal, original)
    assert result["peaks"][0]["value"] == float(original[63])
    assert result["measures"]["bpm"] == pytest.approx(58.898847631242)


def test_request_isolation_with_concurrent_recordings(signal):
    rates = [100, 125, 100, 125]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda rate: analyze_signal(signal, rate), rates))
    assert results[0] == results[2]
    assert results[1] == results[3]
    assert results[0]["sample_rate"] == 100
    assert results[1]["sample_rate"] == 125
    assert results[0]["measures"]["bpm"] != results[1]["measures"]["bpm"]


@pytest.mark.parametrize("samples,rate", [
    ([], 100), ([[1, 2], [3, 4]], 100), (["1"] * 500, 100),
    ([True, 1] * 250, 100), ([1, float("nan")] * 250, 100),
    ([1, float("inf")] * 250, 100), ([1] * 500, 0),
    ([1] * 500, True), ([1] * 500, float("inf")),
    ([1] * 500, "100"), ([1] * 500, 5001), ([1] * 500, 10 ** 1000),
    ([1] * 499, 100), ([1] * 6010, 10), ([1] * 300_001, 1000),
])
def test_invalid_inputs(samples, rate):
    with pytest.raises(InvalidSignalError):
        analyze_signal(samples, rate)


@pytest.mark.parametrize("settings", [
    {"bpm_min": 180, "bpm_max": 40}, {"bpm_max": 301},
    {"bpm_min": float("nan")}, {"window_size": 0},
    {"window_size": 2.1}, {"clean_rr": "false"}, {"calc_freq": 1},
])
def test_invalid_settings(signal, settings):
    with pytest.raises(InvalidSignalError):
        analyze_signal(signal, 100, **settings)


def test_unusable_signals(signal):
    with pytest.raises(AnalysisError, match="constant"):
        analyze_signal([1] * 500, 100)
    with pytest.raises(AnalysisError, match="No reliable heartbeat"):
        analyze_signal(signal, 100, bpm_min=220, bpm_max=230)


@pytest.mark.filterwarnings("ignore:Short signal")
def test_optional_frequency_analysis(signal):
    result = analyze_signal(signal, 100, calc_freq=True)
    assert result["measures"]["lf"] == pytest.approx(3368.0157636195145)
    assert result["measures"]["hf"] == pytest.approx(1548.2394628175164)
    assert any("5 minutes" in item for item in result["warnings"])
    json.dumps(result, allow_nan=False)


def test_undefined_metrics_are_json_null(signal, monkeypatch):
    from heartpy.backend import analysis
    original = analysis.process

    def process_with_undefined(*args, **kwargs):
        working, measures = original(*args, **kwargs)
        measures.update(breathingrate=np.nan, **{"sd1/sd2": np.inf})
        return working, measures

    monkeypatch.setattr(analysis, "process", process_with_undefined)
    result = analyze_signal(signal, 100)
    assert result["measures"]["breathingrate"] is None
    assert result["measures"]["sd1/sd2"] is None
    assert any("null" in item for item in result["warnings"])
    json.dumps(result, allow_nan=False)
