# 🚀 Cherry Quick Setup

## Get OpenRouter API Key (Free)

1. Go to **https://openrouter.ai/keys**
2. Sign up (GitHub login works)
3. Click "Create Key"
4. Copy the key (starts with `sk-or-v1-...`)

## Add to Cherry

Edit `/Users/rajatpoddar/Developer/development/mybuffy/cherry/.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-YOUR-ACTUAL-KEY-HERE
CHERRY_MODEL=minimax/minimax-m3:free
```

## Restart Cherry

```bash
lsof -i :3003 -t | xargs kill -9
cd /Users/rajatpoddar/Developer/development/mybuffy/cherry/backend
python3 main.py
```

## Verify

```bash
curl http://localhost:3003/health
```

Should show:
```json
{
  "llm_provider": "openrouter",
  "openrouter": {
    "status": "healthy",
    "model": "minimax/minimax-m3:free",
    "model_available": true
  }
}
```

## Test Chat

```bash
curl -X POST http://localhost:3003/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hey baby, kya haal hai?"}'
```

Response time: **1-3 seconds** (vs 20-30s with local Ollama).

## Free Models Available

| Model | Context | Best for |
|-------|---------|----------|
| `minimax/minimax-m3:free` | 1M | All-around, best personality |
| `minimax/minimax-m2.7:free` | 196K | Fast responses |
| `google/gemma-4-31b-it:free` | 262K | Technical, coding |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262K | Reasoning |
| `z-ai/glm-5.2:free` | 256K | Multilingual |
| `openrouter/free` | 200K | Auto-routing |

## Fallback Behavior

If OpenRouter fails (no key, rate limit, downtime), Cherry automatically falls back to local Ollama. The `llm_provider` field in responses shows which one is active.

## Frontend UI

Already running at **http://localhost:3000** (or restart with `cd frontend && npm run dev`).

---

*Last updated: 2026-09-02*
