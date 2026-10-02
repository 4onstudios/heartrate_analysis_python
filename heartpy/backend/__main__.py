"""Run the optional HTTP API with ``python -m heartpy.backend``."""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Serve HeartPy's HTTP analysis API.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.workers < 1:
        parser.error("port must be 1--65535 and workers must be positive")
    try:
        import uvicorn
    except ModuleNotFoundError:
        parser.error("Install this package with pip install '.[backend]' first.")
    uvicorn.run(
        "heartpy.backend.api:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
