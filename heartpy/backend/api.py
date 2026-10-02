"""Optional HTTP adapter. Install this package's ``backend`` extra."""

import hmac
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from starlette.exceptions import HTTPException

from .analysis import (
    MAX_BPM,
    MAX_DURATION_SECONDS,
    MAX_SAMPLE_RATE,
    MAX_SAMPLES,
    MAX_WINDOW_SIZE,
    MIN_DURATION_SECONDS,
    MIN_WINDOW_SIZE,
    AnalysisError,
    InvalidSignalError,
    analyze_signal,
)

MAX_BODY_BYTES = 8 * 1024 * 1024


def _error(status_code, code, message, **extra):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, **extra}},
    )


class BodyLimitMiddleware:
    """Bound JSON bytes before parsing, including requests without Content-Length."""

    def __init__(self, app, max_bytes=MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > self.max_bytes
        except ValueError:
            too_large = False
        chunks = []
        size = 0
        while not too_large:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                too_large = True
                break
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        if too_large:
            response = _error(413, "request_too_large", "Request body exceeds the 8 MiB limit.")
            await response(scope, receive, send)
            return

        body = b"".join(chunks)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_body, send)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    samples: list[FiniteFloat] = Field(
        min_length=2, max_length=MAX_SAMPLES, description="Evenly spaced raw PPG/ECG amplitudes."
    )
    sample_rate: FiniteFloat = Field(gt=0, le=MAX_SAMPLE_RATE, description="Sampling rate in Hz.")
    bpm_min: FiniteFloat = Field(default=40, gt=0, le=MAX_BPM)
    bpm_max: FiniteFloat = Field(default=180, gt=0, le=MAX_BPM)
    window_size: FiniteFloat = Field(default=0.75, ge=MIN_WINDOW_SIZE, le=MAX_WINDOW_SIZE)
    clean_rr: bool = False
    calc_freq: bool = False

    @model_validator(mode="after")
    def check_settings(self):
        if self.bpm_min >= self.bpm_max:
            raise ValueError("bpm_min must be less than bpm_max.")
        duration = len(self.samples) / self.sample_rate
        if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
            raise ValueError("Provide 5--600 seconds of signal per request.")
        if int(self.window_size * self.sample_rate) < 1:
            raise ValueError("window_size must cover at least one sample.")
        return self


class Peak(BaseModel):
    index: int
    time_seconds: float
    value: float
    accepted: bool


class Quality(BaseModel):
    detected_peak_count: int
    accepted_peak_count: int
    rejected_peak_count: int
    valid_rr_count: int
    rejected_rr_count: int


class AnalyzeResponse(BaseModel):
    schema_version: int
    sample_rate: float
    sample_count: int
    duration_seconds: float
    peaks: list[Peak]
    rr_intervals_ms: list[float]
    rr_accepted: list[bool]
    rr_intervals_clean_ms: list[float]
    measures: dict[str, float | None]
    quality: Quality
    warnings: list[str]


class ValidationField(BaseModel):
    path: list[str | int]
    message: str


class ErrorDetails(BaseModel):
    code: str
    message: str
    fields: list[ValidationField] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetails


def create_app(*, api_key=None, allowed_origins=None):
    """Build a standalone or mountable ASGI app.

    Defaults read HEARTPY_API_KEY and comma-separated HEARTPY_CORS_ORIGINS.
    No key means authentication is delegated to the hosting backend.
    CORS is disabled unless origins are explicitly supplied.
    """
    if api_key is None:
        api_key = os.environ.get("HEARTPY_API_KEY", "")
    if allowed_origins is None:
        allowed_origins = [
            item.strip()
            for item in os.environ.get("HEARTPY_CORS_ORIGINS", "").split(",")
            if item.strip()
        ]
    app = FastAPI(title="HeartPy Backend", version="1.2.9")
    app.add_middleware(BodyLimitMiddleware)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    bearer = HTTPBearer(auto_error=False)

    def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if api_key and (
            credentials is None
            or not hmac.compare_digest(
                credentials.credentials.encode("utf-8"), api_key.encode("utf-8")
            )
        ):
            raise HTTPException(
                status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError):
        # Do not echo raw sensor samples or non-finite JSON values in errors.
        return _error(
            422,
            "invalid_request",
            "Request validation failed.",
            fields=[{"path": list(item["loc"]), "message": item["msg"]} for item in exc.errors()],
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        response = _error(exc.status_code, "unauthorized" if exc.status_code == 401 else "http_error",
                          str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        return _error(500, "internal_error", "Analysis failed unexpectedly.")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post(
        "/v1/analyze",
        response_model=AnalyzeResponse,
        dependencies=[Depends(authenticate)] if api_key else [],
        responses={
            401: {"model": ErrorResponse, "description": "Missing or incorrect bearer token."},
            413: {"model": ErrorResponse, "description": "Request exceeds the 8 MiB limit."},
            422: {"model": ErrorResponse, "description": "Invalid request or unusable signal."},
            500: {"model": ErrorResponse, "description": "Unexpected analysis failure."},
        },
    )
    def analyze(payload: AnalyzeRequest):
        # A sync handler runs in FastAPI's worker pool, keeping the event loop free.
        try:
            return analyze_signal(**payload.model_dump())
        except InvalidSignalError as exc:
            return _error(422, "invalid_signal", str(exc))
        except AnalysisError as exc:
            return _error(422, "bad_signal", str(exc))

    return app
