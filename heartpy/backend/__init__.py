"""JSON-ready analysis for Python backends, with an optional HTTP API."""

from .analysis import AnalysisError, InvalidSignalError, analyze_signal

__all__ = ["analyze_signal", "create_app", "AnalysisError", "InvalidSignalError"]


def create_app(**kwargs):
    """Create the optional FastAPI app; install ``heartpy[backend]`` first."""
    try:
        from .api import create_app as factory
    except ModuleNotFoundError as exc:
        if exc.name in {"fastapi", "pydantic", "starlette"}:
            raise ImportError(
                "The HTTP API requires the backend extra: "
                "install this package with pip install '.[backend]'."
            ) from exc
        raise
    return factory(**kwargs)
