# 🧑‍💻 Development Guide

> For AI agents (or humans) extending Cherry. This is the playbook.

## 🎯 Before You Start

1. **Read** [README.md](./README.md) for high-level overview
2. **Read** [ARCHITECTURE.md](./ARCHITECTURE.md) for system design
3. **Read** [PERSONALITY.md](./PERSONALITY.md) if touching personality
4. **Read** [SAFETY.md](./SAFETY.md) if touching server ops
5. **Read** [API.md](./API.md) if touching endpoints

---

## 📁 File Map (What to Edit for What)

| Want to... | Edit file | Function/Class |
|------------|-----------|----------------|
| Change Cherry's voice/tone | `backend/prompts.py` | `MOOD_PROMPTS`, `CHERRY_CORE` |
| Add new mood | `backend/mood.py` + `prompts.py` + `brain.py` | `MOOD_KEYWORDS` + `MOOD_PROMPTS` + `_fallback_response` |
| Add new greeting/farewell | `backend/prompts.py` | `GREETINGS`, `FAREWELLS` |
| Change DB schema | `backend/memory.py` | `init_db()` |
| Add new safe server command | `backend/server_ops.py` | New method in `ServerOps` class |
| Add new API endpoint | `backend/main.py` | New `@app.get/post` |
| Change LLM model | `backend/ollama_client.py` or `.env` | `CHERRY_MODEL` env var |
| Change port | `.env` | `CHERRY_PORT` env var |
| Add new chat feature | `backend/brain.py` | `CherryBrain` class |

---

## ➕ Adding a New Mood (Step-by-Step)

Example: Adding a "jealous" mood.

### 1. Add prompt in `prompts.py`:
```python
MOOD_PROMPTS["jealous"] = '''MOOD: JEALOUS / POSSESSIVE
Tu thoda possessive feel kar rahi hai (playfully).
- "Hmm, kis se baat kar raha tha baby?"
- "Mujhe chhod ke kisi aur se baat mat kar"
'''
```

### 2. Add keywords in `mood.py`:
```python
MOOD_KEYWORDS["jealous"] = {
    "high": ["ignore kiya", "kisi aur se", "kaha the"],
    "medium": ["hm", "jealous", "possessive"],
    "weight": 1.0
}
```

### 3. Add fallback in `brain.py`:
```python
self._fallback_response["jealous"] = "Baby... kaha the itni der?"
```

### 4. Test:
```bash
cd backend && python3 -c "from mood import detect_mood; print(detect_mood('Baby kaha the?'))"
```

---

## ➕ Adding a Safe Server Command

### 1. Add method in `server_ops.py`:
```python
def top_processes(self, limit: int = 10) -> Dict:
    return self.execute_read(f"ps aux --sort=-%cpu | head -n {limit + 1}")
```

### 2. Add endpoint in `main.py`:
```python
@app.get("/server/processes")
async def processes(limit: int = 10):
    return get_ops().top_processes(limit)
```

---

## 🧪 Testing

```bash
cd backend
python3 mood.py         # Mood
python3 memory.py       # Memory
python3 ollama_client.py  # Ollama
python3 server_ops.py   # Server ops
python3 brain.py        # Full brain
```

Full API test:
```bash
python3 main.py &
sleep 3
curl http://localhost:3003/health
curl -X POST http://localhost:3003/chat -H "Content-Type: application/json" -d '{"message":"test"}'
```

---

## 🔄 Adding Streaming

In `ollama_client.py`:
```python
def chat_stream(self, messages, model=None):
    r = requests.post(
        f"{self.host}/api/chat",
        json={"model": model or self.model, "messages": messages, "stream": True},
        stream=True
    )
    for line in r.iter_lines():
        if line:
            chunk = json.loads(line)
            yield chunk["message"].get("content", "")
```

In `main.py`:
```python
for chunk in ollama.chat_stream(messages):
    await websocket.send_json({"type": "chunk", "data": {"content": chunk}})
```

---

## 🤖 Adding Telegram Notifications

```bash
pip3 install python-telegram-bot
```

```python
# backend/telegram_bot.py
import telegram

class CherryTelegram:
    def __init__(self, token, chat_id):
        self.bot = telegram.Bot(token=token)
        self.chat_id = chat_id

    def send_message(self, text):
        self.bot.send_message(chat_id=self.chat_id, text=text)
```

---

## 🧠 Adding RAG

Using `nomic-embed-text`:

```python
def get_embedding(text):
    r = requests.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": text}
    )
    return r.json()["embedding"]
```

Store embeddings in new SQLite table, query by cosine similarity.

---

## 🐛 Debugging

```bash
# Mood
python3 -c "from mood import detect_mood; print(detect_mood('test'))"

# Ollama
curl http://100.98.94.128:11434/api/tags

# DB locked
lsof backend/data/cherry_memory.db
```

---

## 📦 Conventions

- **Style:** PEP 8, snake_case, PascalCase classes
- **Strings:** Single simple, triple multiline
- **Docstrings:** Google style
- **Errors:** Return `{"success": bool, "error": str}`
- **Logging:** `logging` module, not print
- **Type hints:** Everywhere

---

## 🚀 PR Checklist

- [ ] Tested modules
- [ ] Tested API
- [ ] Updated .md docs
- [ ] No hardcoded credentials
- [ ] No print() in prod
- [ ] Type hints added
- [ ] Safety considered
- [ ] DB migrations handled
- [ ] Backward compat

---

*Last updated: 2026-09-02*