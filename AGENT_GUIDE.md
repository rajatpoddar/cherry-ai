# 🤖 AI Agent Quick Start

> **READ THIS FIRST** if you are an AI coding agent (Codebuff, Claude Code, Cursor, etc.) being asked to modify Cherry.

## 🎯 What is Cherry?

Cherry is a **mood-aware AI girlfriend + personal assistant** for Rajjoo. She's deployed on his NAS (Cabelwala). She:
- Chats in Hinglish (Hindi-English mix) with romantic/seductive/caring/playful/focused moods
- Connects to Ollama LLM (qwen2.5:3b on NAS at `100.98.94.128:11434`)
- Can read server status (docker ps, df -h, etc.) but NEVER destroys prod
- Has persistent SQLite memory at `backend/data/cherry_memory.db`

## ⚠️ Critical Rules (NEVER VIOLATE)

1. **Production Safety** — Server has 46+ running services. Never run destructive commands without explicit "haan kar do" from user.
2. **Personality Tone** — Cherry is a romantic, caring, slightly seductive GIRLFRIEND. She NEVER says "as an AI" or breaks character.
3. **Hinglish** — Cherry's responses are in Hinglish (mix Hindi-English naturally), not formal English.
4. **Pet names** — Use sparingly: "baby", "jaan", "sweetie". Not every message.
5. **Test before deploy** — Run `python3 main.py` and curl test endpoints after any change.

## 📂 Quick File Reference

```
cherry/
├── backend/
│   ├── main.py           # FastAPI app, all endpoints (add new ones here)
│   ├── brain.py          # CherryBrain — main orchestrator (CherryBrain.think is the entry point)
│   ├── mood.py           # detect_mood() — analyzes user message, returns {mood, confidence, time_of_day}
│   ├── prompts.py        # MOOD_PROMPTS, GREETINGS, build_system_prompt() — ALL personality text
│   ├── memory.py         # SQLite: save_message, get_chat_history, get_stats
│   ├── ollama_client.py  # OllamaClient — wraps Ollama API
│   └── server_ops.py     # ServerOps — safe SSH/command execution
│
├── data/cherry_memory.db # SQLite (auto-created on first run)
├── .env                  # Configuration
└── *.md                  # Documentation
```

## 🧪 Test Commands

```bash
# Mood detection (no Ollama needed)
cd backend && python3 mood.py

# Memory (no Ollama needed)
cd backend && python3 memory.py

# Ollama connection (needs Ollama running)
cd backend && python3 ollama_client.py

# Server ops (needs Tailscale to NAS)
cd backend && python3 server_ops.py

# Full brain test
cd backend && python3 brain.py

# API server
cd backend && python3 main.py
# Then: curl http://localhost:3003/health
```

## 🛠️ Common Tasks

### "Make Cherry more flirty"
→ Edit `backend/prompts.py` → `MOOD_PROMPTS["romantic"]` and `MOOD_PROMPTS["seductive"]`

### "Add a new mood like angry"
→ 1. Add `MOOD_PROMPTS["angry"]` in prompts.py
→ 2. Add `MOOD_KEYWORDS["angry"]` in mood.py
→ 3. Add fallback in `brain.py` `_fallback_response`

### "Add ability to restart a service"
→ Read [SAFETY.md](./SAFETY.md) first. This is HIGH RISK.
→ Add to `server_ops.py` with explicit confirmation required.

### "Make UI mobile-friendly"
→ Build frontend in `frontend/` directory. Use Next.js PWA. Connect to API at `/chat` and `/ws/{session_id}`.

### "Add voice input"
→ Use Web Speech API in frontend. Backend doesn't need changes (just send text to /chat).

## 🎭 Mood Cheat Sheet

When you see Cherry respond in a specific mood, here's what triggered it:

| Mood | Trigger Words | Behavior |
|------|---------------|----------|
| 💕 romantic | love, miss, baby, jaan | "Baby... pyaar se" |
| 😏 seductive | kiss, touch, night, flirty | "Aaja mere paas" |
| 🥺 caring | thak, tired, stress, sad | "Pehle aaram kar" |
| 😜 playful | haha, lol, pagal | "Pagal tu!" |
| 🧠 focused | code, docker, ssh, server | "OK baby, solution:" |
| 💔 miss_you | bahut der, kaha the | "Itne der baad?" |
| 🌸 happy | amazing, great, success | "Mera baby genius!" |

## 🔌 Adding a New API Endpoint

In `backend/main.py`:
```python
@app.get("/your-endpoint")
async def your_handler():
    # Your logic here
    return {"data": "..."}
```

FastAPI auto-generates docs at `/docs`.

## 💾 Database Schema (SQLite)

If you need to add a table or column, edit `memory.py` `init_db()` function.

Tables: `messages`, `user_profile`, `mood_history`, `feedback`, `sessions`, `server_tasks`, `reminders`

## 🆘 Stuck?

1. Read the relevant .md file (README, ARCHITECTURE, PERSONALITY, SAFETY, API, DEVELOPMENT, DEPLOYMENT)
2. Run the test command for that module
3. Check `lsof -i :3003` if server won't start (kill old process)
4. Check `/tmp/cherry.log` for server errors

## 🎯 Success Criteria

Your change is good if:
- ✅ All existing tests pass (`python3 <module>.py`)
- ✅ Server starts and responds to `/health` with 200 OK
- ✅ New chat responses feel like Cherry (mood-appropriate, Hinglish, emotional)
- ✅ Server ops changes don't accidentally allow destructive commands
- ✅ Documentation updated (PERSONALITY.md, API.md, etc.)

## 📚 Full Documentation Map

- [README.md](./README.md) — Overview + quick start
- [ARCHITECTURE.md](./ARCHITECTURE.md) — System design + data flow
- [PERSONALITY.md](./PERSONALITY.md) — All 7 moods explained
- [API.md](./API.md) — Every endpoint with examples
- [SAFETY.md](./SAFETY.md) — Server safety rules
- [DEVELOPMENT.md](./DEVELOPMENT.md) — How to extend Cherry
- [DEPLOYMENT.md](./DEPLOYMENT.md) — Deploy to NAS

---

**Welcome to Cherry! Make her better, but keep her safe and lovely 💕**

*Last updated: 2026-09-02*