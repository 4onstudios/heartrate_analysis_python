import pytest

import heartpy as hp


@pytest.fixture
def signal():
    data, _ = hp.load_exampledata(0)
    return data


@pytest.fixture
def payload(signal):
    return {"samples": signal.tolist(), "sample_rate": 100.0}
