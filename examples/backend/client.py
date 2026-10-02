"""Send HeartPy's example recording to a running analysis backend."""

import argparse
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import heartpy as hp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint", nargs="?", default="http://127.0.0.1:8000/v1/analyze")
    args = parser.parse_args()
    data, _ = hp.load_exampledata(0)
    request = Request(
        args.endpoint,
        data=json.dumps({"samples": data.tolist(), "sample_rate": 100}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = os.environ.get("HEARTPY_API_KEY")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as exc:
        parser.exit(1, "HTTP {}: {}\n".format(exc.code, exc.read().decode("utf-8")))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
