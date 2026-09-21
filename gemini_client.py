"""A small Gemini REST client. It uses httpx and needs no Google SDK."""

import httpx

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    """Raised when the Gemini API cannot be reached or returns something unusable."""


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout: float = 20.0,
        http_client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._http_client = http_client

    def generate_json(self, system_instruction: str, user_payload: str) -> str:
        """Send a prompt and return the raw text of the reply (expected to be JSON)."""
        url = f"{BASE_URL}/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        try:
            if self._http_client is not None:
                response = self._http_client.post(url, json=body, headers=headers)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as err:
            raise GeminiError(f"could not reach Gemini: {type(err).__name__}") from err

        if response.status_code != 200:
            raise GeminiError(f"Gemini returned HTTP {response.status_code}")
        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts).strip()
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise GeminiError("unexpected response shape from Gemini") from err
        if not text:
            raise GeminiError("Gemini returned an empty reply")
        return text
