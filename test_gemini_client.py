import httpx
import pytest

from ecopulse.recommendations.gemini_client import GeminiClient, GeminiError


def client_returning(status, payload):
    def handler(request: httpx.Request):
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "generateContent" in str(request.url)
        return httpx.Response(status, json=payload)

    return GeminiClient("test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_returns_text_from_first_candidate():
    payload = {"candidates": [{"content": {"parts": [{"text": '{"ok": '}, {"text": "true}"}]}}]}
    assert client_returning(200, payload).generate_json("sys", "user") == '{"ok": true}'


def test_http_error_raises():
    with pytest.raises(GeminiError, match="429"):
        client_returning(429, {"error": "quota"}).generate_json("sys", "user")


def test_unexpected_shape_raises():
    with pytest.raises(GeminiError):
        client_returning(200, {"candidates": []}).generate_json("sys", "user")


def test_network_failure_raises():
    def handler(request):
        raise httpx.ConnectError("boom")

    client = GeminiClient("k", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(GeminiError):
        client.generate_json("sys", "user")
