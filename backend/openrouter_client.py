"""
🌐 OpenRouter Client — Cherry ka cloud LLM brain
Free tier models: MiniMax M3, M2.7, Gemma 4, etc.
"""

import os
import requests
import json
from typing import List, Dict, Optional, Generator


# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("CHERRY_MODEL", "minimax/minimax-m3:free")
FALLBACK_MODELS = [
    "minimax/minimax-m2.7:free",
    "google/gemma-4-31b-it:free",
    "z-ai/glm-5.2:free",
    "openrouter/free",
]

APP_REFERER = "https://cherry.local"
APP_TITLE = "Cherry AI"


class OpenRouterClient:
    """OpenRouter API wrapper for Cherry."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.model = model or DEFAULT_MODEL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": APP_REFERER,
            "X-Title": APP_TITLE,
            "Content-Type": "application/json",
        })

    def health_check(self) -> Dict:
        if not self.api_key or "PUT-YOUR-KEY" in self.api_key:
            return {"status": "no_api_key", "error": "Set OPENROUTER_API_KEY in .env (get free at https://openrouter.ai/keys)"}
        try:
            r = self.session.get(f"{OPENROUTER_BASE}/models", timeout=10)
            if r.status_code == 200:
                models = r.json().get("data", [])
                model_ids = [m["id"] for m in models]
                return {
                    "status": "healthy",
                    "model": self.model,
                    "model_available": self.model in model_ids,
                    "total_models": len(models),
                }
            elif r.status_code == 401:
                return {"status": "auth_error", "code": 401, "error": "Invalid API key"}
            return {"status": "unhealthy", "code": r.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_free_models(self) -> List[Dict]:
        try:
            r = self.session.get(f"{OPENROUTER_BASE}/models", timeout=10)
            if r.status_code == 200:
                models = r.json().get("data", [])
                return [
                    {"id": m["id"], "context": m.get("context_length", "?")}
                    for m in models
                    if str(m.get("pricing", {}).get("prompt", "0")) in ["0", "0", ":0"]
                ]
        except Exception:
            pass
        return []

    def chat(
        self,
        messages: List[Dict],
        model: str = None,
        temperature: float = 0.8,
        max_tokens: int = 300,
        stream: bool = False,
        tools: List[Dict] = None,
        tool_choice: str = None,
    ) -> Dict | Generator:
        if not self.api_key:
            return {
                "error": "OPENROUTER_API_KEY not set. Get one free at https://openrouter.ai/keys",
                "detail": "Add to cherry/.env file"
            }

        use_model = model or self.model
        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        try:
            r = self.session.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json=payload,
                stream=stream,
                timeout=120,
            )
            r.raise_for_status()
            if stream:
                return self._stream_response(r)
            return r.json()
        except requests.exceptions.HTTPError as e:
            # Try fallback models
            if e.response.status_code in [404, 429, 503]:
                for fb in FALLBACK_MODELS:
                    if fb != use_model:
                        try:
                            payload["model"] = fb
                            r = self.session.post(
                                f"{OPENROUTER_BASE}/chat/completions",
                                json=payload,
                                timeout=60,
                            )
                            r.raise_for_status()
                            return r.json()
                        except Exception:
                            continue
            return {"error": f"HTTP {e.response.status_code}", "detail": e.response.text[:300]}
        except Exception as e:
            return {"error": str(e)}

    def _stream_response(self, response) -> Generator:
        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8") if isinstance(line, bytes) else line
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue

    def chat_simple(
        self,
        user_message: str,
        system_prompt: str = None,
        model: str = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        result = self.chat(messages, model=model)
        if isinstance(result, dict):
            if "error" in result:
                return f"[Error: {result['error']}]"
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return ""


_client: Optional[OpenRouterClient] = None

def get_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


if __name__ == "__main__":
    print("🌐 OpenRouter Client Test")
    print("=" * 50)
    client = get_client()
    health = client.health_check()
    print(f"Status: {health['status']}")
    if "model" in health:
        print(f"Model: {health['model']}")
        print(f"Available: {health.get('model_available')}")
    if "error" in health:
        print(f"Error: {health['error']}")

    if health["status"] == "healthy":
        print("\n🧪 Testing chat...")
        result = client.chat_simple(
            "Say hi in Hinglish as Cherry, a loving girlfriend. 1 sentence only.",
            system_prompt="You are Cherry, a sweet Hinglish-speaking girlfriend. Be brief."
        )
        print(f"Cherry: {result}")