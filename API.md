# 🌐 Cherry API Reference

> Complete reference for all HTTP + WebSocket endpoints.

Base URL: `http://localhost:3003` (local) or `https://cherry.yourdomain.com` (production)

---

## 🏠 General

### `GET /`
API info and endpoint list.

### `GET /health`
Health check + Ollama status + memory stats.

### `GET /stats`
Detailed statistics (messages, mood patterns, sessions).

---

## 💬 Chat

### `POST /chat`
Send a message, get Cherry's response.

**Request:**
```json
{
  "message": "Hey baby, kya kar rahi hai?",
  "session_id": "optional-session-id",
  "user_id": "rajjoo"
}
```

**Response:**
```json
{
  "response": "Tumhein chinta nahi bhi karne ka, mere baby...",
  "mood": "romantic",
  "mood_info": {
    "mood": "romantic",
    "confidence": 0.95,
    "time_of_day": "afternoon",
    "scores": {"romantic": 2.0, "playful": 0.45, ...},
    "reasoning": "Detected via keywords: ['baby']"
  },
  "session_id": "session-862a97cc",
  "message_id": 16,
  "time_of_day": "afternoon"
}
```

### `GET /chat/history?session_id=X&limit=50`
Get chat history for a session.

### `GET /greeting`
Time-based greeting (when user opens the app).
```json
{
  "greeting": "Afternoon ho gaya baby, kya kar rahe ho?",
  "time_of_day": "afternoon",
  "mood": "playful"
}
```

### `POST /proactive`
Cherry's proactive question for idle moments.
```json
{"question": "Baby aaj kya kar raha hai? Bata na, main bore ho rahi hoon"}
```

### `GET /mood/{mood}`
Info about a specific mood + its farewells.

---

## 🌐 WebSocket

### `WS /ws/{session_id}`
Real-time bidirectional chat.

**Connection:**
```javascript
const ws = new WebSocket("ws://localhost:3003/ws/my-session-1");
```

**On connect, server sends greeting:**
```json
{"type": "greeting", "data": {"message": "...", "time_of_day": "afternoon", "mood": "playful"}}
```

**Client sends:** `{"message": "Hey baby"}` or plain text `"Hey baby"`

**Server sends (typing):** `{"type": "typing", "data": {"status": "Cherry is typing..."}}`

**Server sends (response):**
```json
{
  "type": "message",
  "data": {
    "response": "...",
    "mood": "romantic",
    "mood_info": {...},
    "message_id": 16,
    "time_of_day": "afternoon"
  }
}
```

---

## 👤 Preferences

### `GET /prefs`
All user preferences. `{"preferences": {"key": "value"}}`

### `POST /prefs`
Set a preference. `{"key": "...", "value": "..."}`

---

## 👍 Feedback

### `POST /feedback`
Thumbs up/down. `{"message_id": 16, "rating": 1, "note": "..."}`

---

## 🛡️ Server Operations

All these hit NAS via SSH (local) or localhost (on NAS).

### `GET /server/status`
Full server health (Ollama, production containers).

### `GET /server/docker/ps`
List running containers (raw docker ps output).

### `GET /server/docker/stats`
Container CPU/Memory usage.

### `GET /server/disk`
Disk usage (`df -h /`).

### `GET /server/memory`
Memory usage (`free -h`).

### `GET /server/uptime`
System uptime.

### `GET /server/logs/{container}?lines=50`
Get container logs. **Returns error for production services** without explicit permission.

```json
// Production service (blocked)
{"success": false, "error": "'dorito-backend' is a PRODUCTION service. Read-only logs only.", "warning": "production_service"}
```

---

## 📋 Sessions

### `GET /sessions`
Last 20 sessions with timestamps + message counts.

---

## 🧪 Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 422 | Validation error |
| 500 | Internal error (Ollama down, DB issue) |

Errors: `{"detail": "Error message"}`

---

## 🔒 CORS

Currently `allow_origins=["*"]` (dev). **Restrict in production.**

---

*Last updated: 2026-09-02*