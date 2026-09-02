"""
🤖 Ollama Client — Cherry ka actual LLM brain
"""

import os
import requests
import json
from typing import List, Dict, Optional, Generator


# Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("CHERRY_MODEL", "qwen2.5:3b")
CODER_MODEL = os.getenv("CHERRY_CODER_MODEL", "qwen2.5:3b")


class OllamaClient:
    """Cherry ka LLM client."""

    def __init__(self, host: str = None, model: str = None):
        self.host = host or OLLAMA_HOST
        self.model = model or DEFAULT_MODEL
        self.coder_model = CODER_MODEL

    def health_check(self) -> Dict:
        """Ollama server health check."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            if r.status_code == 200:
                data = r.json()
                return {
                    "status": "healthy",
                    "host": self.host,
                    "models": [m["name"] for m in data.get("models", [])]
                }
            return {"status": "unhealthy", "code": r.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_models(self) -> List[str]:
        """Available models list."""
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def pull_model(self, model_name: str) -> Dict:
        """Model pull karta hai (background download)."""
        try:
            r = requests.post(
                f"{self.host}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600
            )
            return r.json() if r.status_code == 200 else {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def chat(
        self,
        messages: List[Dict],
        model: str = None,
        temperature: float = 0.8,
        stream: bool = False
    ) -> Dict | Generator:
        """
        Ollama ko chat request bhejta hai.

        messages: [{"role": "system/user/assistant", "content": "..."}]
        """
        use_model = model or self.model
        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "top_k": 40,
                "num_ctx": 2048,  # Smaller ctx = MUCH faster on CPU
                "num_predict": 100,  # Cap to 100 tokens = short focused replies
                "repeat_penalty": 1.3,  # Stronger anti-repetition
                "stop": ["\n\n\n", "Rajjoo:", "User:", "Assistant:"]  # Stop on loops
            }
        }

        try:
            r = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                stream=stream,
                timeout=120
            )
            r.raise_for_status()

            if stream:
                return self._stream_response(r)
            return r.json()
        except requests.exceptions.ConnectionError:
            return {
                "error": "Cannot connect to Ollama",
                "detail": f"Make sure Ollama is running at {self.host}"
            }
        except Exception as e:
            return {"error": str(e)}

    def _stream_response(self, response) -> Generator:
        """Stream response ko words mein todta hai."""
        for line in response.iter_lines():
            if line:
                try:
                    chunk = json.loads(line)
                    if "message" in chunk:
                        yield chunk["message"].get("content", "")
                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

    def chat_simple(self, user_message: str, system_prompt: str = None,
                    model: str = None) -> str:
        """Simple chat helper."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        result = self.chat(messages, model=model)
        if isinstance(result, dict):
            if "error" in result:
                return f"[Error: {result['error']}]"
            return result.get("message", {}).get("content", "")
        return ""

    def generate(self, prompt: str, model: str = None, stream: bool = False) -> str | Generator:
        """Single-prompt generation (no chat history)."""
        use_model = model or self.model
        try:
            r = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": stream
                },
                timeout=120
            )
            r.raise_for_status()
            if stream:
                return r.iter_lines()
            return r.json().get("response", "")
        except Exception as e:
            return f"[Error: {e}]"


# Singleton
_client: Optional[OllamaClient] = None

def get_client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client


if __name__ == "__main__":
    print("🤖 Ollama Client Test")
    print("=" * 50)
    client = get_client()
    health = client.health_check()
    print(f"Status: {health['status']}")
    print(f"Host: {health.get('host', 'N/A')}")
    if "models" in health:
        print(f"Models: {health['models']}")

    if health["status"] == "healthy":
        print("\n🧪 Testing chat...")
        result = client.chat_simple(
            "Say hi in one short sentence as Cherry, Rajjoo's AI girlfriend",
            system_prompt="You are Cherry, a cute Hinglish-speaking AI girlfriend. Reply in 1 sentence only."
        )
        print(f"Cherry: {result}")
