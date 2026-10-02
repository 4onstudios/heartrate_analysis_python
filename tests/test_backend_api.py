import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from heartpy.backend import analyze_signal, create_app
from heartpy.backend.api import BodyLimitMiddleware, MAX_BODY_BYTES


@pytest.fixture
def client():
    return TestClient(create_app(api_key="", allowed_origins=[]))


def test_api_matches_python_interface(client, payload):
    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    assert response.json() == analyze_signal(**payload)
    assert client.get("/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    assert {"200", "401", "413", "422", "500"} <= set(schema["paths"]["/v1/analyze"]["post"]["responses"])


@pytest.mark.parametrize("change", [
    {"sample_rate": 0}, {"sample_rate": "100"}, {"sample_rate": True},
    {"samples": []}, {"samples": [[1, 2]]}, {"samples": ["1"] * 500},
    {"samples": [True, 1] * 250}, {"samples": [1] * 499},
    {"bpm_min": 180, "bpm_max": 40}, {"window_size": 0},
    {"calc_freq": "false"}, {"unexpected": "field"},
])
def test_validation_errors_do_not_echo_sensor_data(client, payload, change):
    payload.update(change)
    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert all(set(field) == {"path", "message"} for field in error["fields"])


@pytest.mark.parametrize("content", [
    '{"samples":[NaN],"sample_rate":100}',
    '{"samples":[Infinity],"sample_rate":100}',
    '{"samples":[-Infinity],"sample_rate":100}',
    '{"samples":[1],"sample_rate":NaN}',
    '{"samples":',
])
def test_nonfinite_and_malformed_json_do_not_cause_server_errors(client, content):
    response = client.post("/v1/analyze", content=content, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_bad_signal_error(client):
    response = client.post("/v1/analyze", json={"samples": [1] * 500, "sample_rate": 100})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "bad_signal"


def test_unexpected_failure_is_json_and_hides_internal_details(payload, monkeypatch):
    from heartpy.backend import api

    def fail(**_kwargs):
        raise RuntimeError("private internal details")

    monkeypatch.setattr(api, "analyze_signal", fail)
    client = TestClient(create_app(api_key=""), raise_server_exceptions=False)
    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private" not in response.text


def test_optional_bearer_auth_and_public_health(payload):
    client = TestClient(create_app(api_key="test-token", allowed_origins=[]))
    for headers in [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic test-token"}]:
        response = client.post("/v1/analyze", json=payload, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "unauthorized"
    assert client.post("/v1/analyze", json=payload, headers={"Authorization": "Bearer test-token"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_environment_configuration(payload, monkeypatch):
    monkeypatch.setenv("HEARTPY_API_KEY", "from-environment")
    monkeypatch.setenv("HEARTPY_CORS_ORIGINS", "https://app.example.com, https://other.example.com")
    client = TestClient(create_app())
    assert client.post("/v1/analyze", json=payload).status_code == 401
    response = client.post("/v1/analyze", json=payload, headers={
        "Authorization": "Bearer from-environment", "Origin": "https://app.example.com"
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def test_cors_only_allows_configured_origins(payload):
    client = TestClient(create_app(api_key="", allowed_origins=["https://app.example.com"]))
    headers = {"Origin": "https://app.example.com", "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type,authorization"}
    allowed = client.options("/v1/analyze", headers=headers)
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == headers["Origin"]
    headers["Origin"] = "https://untrusted.example.com"
    denied = client.options("/v1/analyze", headers=headers)
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_cors_disabled_by_default(client):
    response = client.get("/health", headers={"Origin": "https://app.example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_oversized_body_with_content_length(client):
    response = client.post("/v1/analyze", content=b" " * (MAX_BODY_BYTES + 1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_streamed_body_limit_without_content_length():
    async def check():
        called = False
        messages = []
        events = iter([
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ])

        async def downstream(*_args):
            nonlocal called
            called = True

        async def receive():
            return next(events)

        async def send(message):
            messages.append(message)

        app = BodyLimitMiddleware(downstream, max_bytes=5)
        await app({"type": "http", "method": "POST", "headers": []}, receive, send)
        assert not called
        assert messages[0]["status"] == 413
        assert json.loads(messages[1]["body"])["error"]["code"] == "request_too_large"

    asyncio.run(check())


def test_can_mount_in_existing_python_backend(payload):
    parent = FastAPI()
    parent.mount("/heart", create_app(api_key="", allowed_origins=[]))
    client = TestClient(parent)
    assert client.post("/heart/v1/analyze", json=payload).status_code == 200
    assert client.get("/heart/docs").status_code == 200
