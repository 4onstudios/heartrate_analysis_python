# HeartPy - Python Heart Rate Analysis Toolkit

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.1324311.svg)](https://doi.org/10.5281/zenodo.1324311) [![Build Status](https://travis-ci.org/paulvangentcom/heartrate_analysis_python.svg?branch=master)](https://travis-ci.org/paulvangentcom/heartrate_analysis_python) [![codecov](https://codecov.io/gh/paulvangentcom/heartrate_analysis_python/branch/master/graph/badge.svg)](https://codecov.io/gh/paulvangentcom/heartrate_analysis_python) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/heartpy)


**Like HeartPy? Don't forget to leave a star!**


# Structural update

HeartPy V1.2 has landed! The structure of the package has been reworked to be in separate modules now in preparation of the next big update, which will feature many analysis expansions and the first steps towards a GUI for HeartPy. HeartPy has been growing steadily and had reached the point where it became cluttered and unwieldy to keep in a single file. The API remains unchanged.

An 'Examples' folder has been added to the repo which will be expanded soon. Now there's two notebooks explaining how to analyse ppg signals from smartwatches and smart rings.

Colorblind support has been added, see [this notebook in the examples folder](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/6_colorblind_mode/Colorblind_mode.ipynb)

# Installation

This checkout requires Python 3.10 or newer. Install the local package with pip:
```
python -m pip install .
```

Alternatively, we're also on PIP:
```
python -m pip install heartpy
```

That's it! Note that Github always has the newest version.

## Python backend and mobile API

This fork adds a framework-independent, JSON-ready analysis interface:

```python
import heartpy as hp
from heartpy.backend import analyze_signal

samples, _ = hp.load_exampledata(0)
result = analyze_signal(samples, sample_rate=100)
print(result["measures"]["bpm"])
print(result["peaks"])  # indices, times, original amplitudes, accepted/rejected
```

To expose it to iOS or Android over HTTP, install the optional backend extra
from this checkout:

```bash
python -m pip install ".[backend]"
python -m heartpy.backend --host 0.0.0.0 --port 8000
```

The API accepts raw PPG/ECG samples at `POST /v1/analyze`. Interactive API docs
are at `/docs`. You can also import `create_app()` and mount the API inside an
existing Python backend. The analysis function itself does not require FastAPI.

See [the backend integration guide](docs/backend.md) for request and response
formats, authentication, package installation, and Swift/Android client examples.
The backend extra is supplied by this fork; a plain PyPI `heartpy` installation
does not include these changes until they are published.

### Integrate in your own external API service (Django + DRF)

If you already run a Django API, install this package in that service and call
`analyze_signal()` from your endpoint.

```python
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from heartpy.backend import analyze_signal, InvalidSignalError, AnalysisError


class AnalyzeHeartSignalView(APIView):
    def post(self, request):
        try:
            result = analyze_signal(
                samples=request.data["samples"],
                sample_rate=float(request.data["sample_rate"]),
                bpm_min=request.data.get("bpm_min", 40),
                bpm_max=request.data.get("bpm_max", 180),
                window_size=request.data.get("window_size", 0.75),
                clean_rr=request.data.get("clean_rr", False),
                calc_freq=request.data.get("calc_freq", False),
            )
            return Response(result, status=status.HTTP_200_OK)
        except InvalidSignalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except AnalysisError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

This lets your external service remain the public API surface (auth, rate-limit,
logging), while HeartPy stays an internal package dependency.

For full request validation and production notes, see
[docs/backend.md](docs/backend.md#import-from-your-existing-backend).

### Integrate in your own external API service (FastAPI)

If your external service is FastAPI, call `analyze_signal()` directly in your
route and keep auth/rate-limit/logging in your own API layer.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from heartpy.backend import analyze_signal, InvalidSignalError, AnalysisError

app = FastAPI()


class AnalyzeRequest(BaseModel):
    samples: list[float]
    sample_rate: float
    bpm_min: float = 40
    bpm_max: float = 180
    window_size: float = 0.75
    clean_rr: bool = False
    calc_freq: bool = False


@app.post("/api/v1/heart/analyze")
def analyze(req: AnalyzeRequest):
    try:
        return analyze_signal(
            samples=req.samples,
            sample_rate=req.sample_rate,
            bpm_min=req.bpm_min,
            bpm_max=req.bpm_max,
            window_size=req.window_size,
            clean_rr=req.clean_rr,
            calc_freq=req.calc_freq,
        )
    except InvalidSignalError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
```

# Documentation

The official documentation is online! [You can find the official documentation here](https://python-heart-rate-analysis-toolkit.readthedocs.io)

# Python versions
This backend-enabled release supports Python 3.10 and newer. Older HeartPy
releases are needed for applications that still use legacy Python versions.

# Tutorial notebooks are now available in Examples/
These show how to handle various analysis tasks with HeartPy, from smartwatch data, smart ring data, regular PPG, and regular (and very noisy) ECG. The notebooks sometimes don't render through the github engine, so either open them locally, or use an online viewer like [nbviewer](https://nbviewer.jupyter.org/).

We recommend you follow the notebooks in order:
- [1. Analysing a PPG signal](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/1_regular_PPG/Analysing_a_PPG_signal.ipynb), a notebook for starting out with HeartPy using built-in examples.
- [2. Analysing an ECG signal](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/2_regular_ECG/Analysing_a_regular_ECG_signal.ipynb), a notebook for working with HeartPy and typical ECG data.
- [3. Analysing smartwatch data](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/3_smartwatch_data/Analysing_Smartwatch_Data.ipynb), a notebook on analysing low resolution PPG data from a smartwatch.
- [4. Analysing smart ring data](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/4_smartring_data/Analysing_Smart_Ring_Data.ipynb), a notebook on analysing smart ring PPG data.
- [5. Analysing noisy ECG data](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/5_noisy_ECG/Analysing_Noisy_ECG.ipynb), an advanced notebook on working with very noisy ECG data, using data from the MIT-BIH noise stress test dataset.
- [6. Colorblind mode - How To and Styles](https://github.com/paulvangentcom/heartrate_analysis_python/blob/master/examples/6_colorblind_mode/Colorblind_mode.ipynb)



# More information
**HeartPy**, the **Python Heart Rate Analysis Toolkit** is a module for heart rate analysis in Python. It started as pure-python implementation to analyse physiological data taken in naturalistic driving and cycling experiments.

The module takes a discrete heart rate signal and outputs time-domain and frequency-domain measures often found in scientific literature:


Time domain:
* beats per minute, BPM
* interbeat interval, IBI
* standard deviation  if intervals between adjacent beats, SDNN
* standard deviation of successive differences between adjacent R-R intervals, SDSD
* root mean square of successive differences between adjacend R-R intervals, RMSSD
* proportion of differences between R-R intervals greater than 20ms, 50ms, pNN20, pNN50
* median absolute deviation, MAD
* Poincare analysis (SD1, SD2, S, SD1/SD2)
* Poincare plotting

Frequency domain (ranges per Shaffer and Ginsberg: https://doi.org/10.3389/fpubh.2017.00258)
* very low frequency component (0.0033–0.04 Hz), VLF
* low frequency component (0.04–0.15 Hz), LF
* high frequency component (0.15–0.4 Hz), HF
* lf/hf ratio, LF/HF

**When using the package in your research, please cite**:

van Gent, P., Farah, H., van Nes, N., & van Arem, B. (2019). Analysing Noisy Driver Physiology Real-Time Using Off-the-Shelf Sensors: Heart Rate Analysis Software from the Taking the Fast Lane Project. Journal of Open Research Software, 7(1), 32. DOI: http://doi.org/10.5334/jors.241

van Gent, P., Farah, H., van Nes, N., & van Arem, B. (2019). HeartPy: A novel heart rate algorithm for the analysis of noisy signals. Transportation Research Part F: Traffic Psychology and Behaviour, 66, 368–378. https://doi.org/10.1016/j.trf.2019.09.015

## Documentation

[You can find the official documentation here](https://python-heart-rate-analysis-toolkit.readthedocs.io)

The module is also to some extent described in my tutorial series:

* [Analyzing a Discrete Heart Rate Signal Using Python - Part 1](http://www.paulvangent.com/2016/03/15/analyzing-a-discrete-heart-rate-signal-using-python-part-1/)
* [Analyzing a Discrete Heart Rate Signal Using Python - Part 2](http://www.paulvangent.com/2016/03/21/analyzing-a-discrete-heart-rate-signal-using-python-part-2/)
* [Analyzing a Discrete Heart Rate Signal Using Python - Part 3](http://www.paulvangent.com/2016/03/30/analyzing-a-discrete-heart-rate-signal-using-python-part-3/)
* Analyzing a Discrete Heart Rate Signal Using Python - Part 4: in development


## License
The module is licensed under the [MIT License](https://opensource.org/licenses/MIT)

## Validation
Initial results of the validation have been reported in [1, 2].


[1]van Gent, P., Farah, H., van Nes, N., & van Arem, B. (2018). Heart Rate Analysis for Human Factors: Development and Validation of an Open Source Toolkit for Noisy Naturalistic Heart Rate Data. In Proceedings of the 6th HUMANIST Conference (pp. 173–178).

[2] van Gent, P., Farah, H., van Nes, N., & van Arem, B. (2019). HeartPy: A novel heart rate algorithm for the analysis of noisy signals. Transportation Research Part F: Traffic Psychology and Behaviour, 66, 368–378. https://doi.org/10.1016/j.trf.2019.09.015



## To-do

The module is still in active development. See the changelog for past changes. The to-do for the coming months is:

to do before V1.3
- [X] Same but for PPG - morphology too variable, method unstable
- [ ] Add 'strictness parameter' to affect how HeartPy evaluates peaks for acceptance/rejection
- [ ] Add method to handle NaN data automatically
- [ ] clean_rr method now removes incorrect values, update to allow for replacement by median of surrounding data points
	- [ ] add method that can fill in missing R-peaks, settable to search for either local optimum OR mean imputation. 
- [ ] Report validation performance on repo (published paper + key-points document once published)
- [ ] Change backend structure in anticipation of GUI development
- [ ] Develop GUI for HeartPy
