# 🏗️ Cherry Architecture — Deep Dive

> For AI agents who want to understand how Cherry works under the hood.

## 🎯 Design Principles

1. **Safety First** — Production server has 46+ running services. Every action is gated.
2. **Mood-Aware** — Cherry's behavior changes based on user mood + time of day + context.
3. **Memory-First** — Everything Cherry learns is persisted to SQLite for self-improvement.
4. **Stateless API** — Each request is self-contained, but reads from persistent memory.
5. **Modular** — Each file has one responsibility. Easy to swap out components.

---

## 🧠 Request Flow

When a user sends a message, here's what happens:

```
User Message: "Hey baby, kya kar rahi hai?"
    ↓
[1] FastAPI receives POST /chat
    ↓
[2] CherryBrain.think(message) called
    ↓
[3] mood.py → detect_mood(message)
    - Analyzes keywords
    - Considers time of day
    - Returns: {mood: "romantic", confidence: 0.95, time: "afternoon"}
    ↓
[4] memory.py → save_message(user_msg, mood)
    - Persists to SQLite
    - Updates mood_history for pattern learning
    ↓
[5] prompts.py → build_system_prompt(mood, time, context)
    - Combines CHERRY_CORE + MOOD_PROMPTS[mood] + recent chat history
    - Adds SAFETY_GUARD if technical keywords detected
    ↓
[6] memory.py → get_chat_history(last 10 messages)
    - Builds conversation context
    ↓
[7] ollama_client.py → chat(messages, temperature=0.85)
    - Sends to Ollama at OLLAMA_HOST
    - Receives Cherry's response
    ↓
[8] memory.py → save_message(cherry_msg, mood)
    - Persists Cherry's response
    ↓
[9] Return JSON to client
```

---

## 🗄️ Database Schema

SQLite at `data/cherry_memory.db`. WAL mode for performance.

### Tables:

```sql
-- Chat messages
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mood TEXT,
    time_of_day TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User preferences (key-value)
CREATE TABLE user_profile (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mood pattern history (for learning)
CREATE TABLE mood_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mood TEXT NOT NULL,
    time_of_day TEXT,
    user_message_preview TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Thumbs up/down feedback
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    rating INTEGER,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id)
);

-- Session tracking
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message_count INTEGER DEFAULT 0
);

-- Server task audit log
CREATE TABLE server_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    description TEXT,
    result TEXT,
    success INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reminders
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    remind_at TIMESTAMP NOT NULL,
    completed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🔌 Module Dependencies

```
main.py
  ├── brain.py (CherryBrain)
  │   ├── mood.py (detect_mood, get_time_of_day)
  │   ├── memory.py (save_message, get_chat_history, etc.)
  │   ├── ollama_client.py (OllamaClient)
  │   └── prompts.py (MOOD_PROMPTS, build_system_prompt)
  ├── memory.py (used directly for stats, prefs, feedback)
  ├── server_ops.py (ServerOps - used for /server/* endpoints)
  └── ollama_client.py (used directly for /health)
```

**No circular dependencies.** Each module is testable in isolation.

---

## 🌐 Connection Architecture

### Local Development (laptop):
```
Laptop (Cherry backend)
  ├── Ollama → http://100.98.94.128:11434 (via Tailscale VPN)
  └── SSH → rajat@100.98.94.128 (via Tailscale)
```

### Production (on NAS):
```
NAS (Cherry backend in Docker)
  ├── Ollama → http://localhost:11434 (local socket)
  └── Commands → localhost (no SSH needed)
```

The `CHERRY_LOCAL=1` env var switches behavior.

---

## 🛡️ Safety Layer

Every server command goes through `server_ops.ServerOps.execute_read()`:

```python
def _is_blocked(self, command: str) -> bool:
    # 1. Check word-boundary patterns (format, drop, kill, etc.)
    # 2. Check substring patterns (rm -rf, dd if=, etc.)
    # 3. Return True if ANY match
```

Production service names are protected:
```python
PROD_SERVICES = {"portainer", "ollama", "jellyfin", "nextcloud", ...}
```

If someone tries to run `docker logs dorito-backend`, it returns:
```json
{
  "success": false,
  "error": "'dorito-backend' is a PRODUCTION service. Read-only logs only.",
  "warning": "production_service"
}
```

Even with auto-sudo via SSH, the production check still blocks.

---

## 🧪 Testing Strategy

Each module is independently testable:

```bash
cd backend && python3 mood.py        # Mood detection
cd backend && python3 memory.py      # Memory system
cd backend && python3 ollama_client.py  # Ollama
cd backend && python3 server_ops.py  # Server ops (needs Tailscale)
cd backend && python3 brain.py       # Full integration
```

---

## 🔄 Future Enhancements

1. **Streaming** — Token-by-token via WebSocket
2. **RAG** — Semantic search over chat history with nomic-embed-text
3. **Multi-user** — Add user_id to all tables
4. **Voice** — Whisper.cpp STT + pyttsx3 TTS
5. **Telegram bot** — Cherry can message on Telegram
6. **Cron jobs** — Scheduled reminders, daily check-ins

See [DEVELOPMENT.md](./DEVELOPMENT.md) for how to implement these.

---

*Last updated: 2026-09-02*