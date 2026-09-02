"""
🌸 Cherry FastAPI Server — WebSocket + REST API
"""

import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

# Load .env BEFORE importing other modules
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from brain import get_brain
from memory import (
    get_chat_history, get_all_sessions, get_stats,
    get_mood_patterns, save_feedback, set_user_pref,
    get_user_pref, get_all_prefs, save_message
)
from server_ops import get_ops
from ollama_client import get_client
from mood import get_time_of_day, detect_mood


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌸 Cherry starting up...")
    brain = get_brain()
    brain.start_session()
    print(f"   Session: {brain.session_id}")
    print(f"   Time: {get_time_of_day()}")
    print(f"   Ollama: {brain.ollama.health_check()['status']}")

    # NEW: Sync from .agents folder on startup
    try:
        from session_manager import sync_from_agents
        sync_result = sync_from_agents()
        if sync_result.get("status") == "synced":
            loaded = sync_result.get("loaded", {})
            total = sum(loaded.values()) if isinstance(loaded, dict) else 0
            print(f"   .agents synced: {total} items loaded")
    except Exception as e:
        print(f"   .agents sync warning: {e}")

    # Telegram bot (optional — auto-starts if TELEGRAM_BOT_TOKEN is set)
    tg_bot = None
    try:
        from telegram_bot import get_telegram_bot
        tg_bot = get_telegram_bot()
        if tg_bot.is_enabled():
            await tg_bot.start()
            print(f"   Telegram: live (use /start in Telegram)")
        else:
            print("   Telegram: disabled (no TELEGRAM_BOT_TOKEN)")
    except Exception as e:
        print(f"   Telegram warning: {e}")

    print("✅ Cherry ready!")
    yield

    # Telegram bot shutdown
    if tg_bot is not None:
        try:
            await tg_bot.stop()
        except Exception as e:
            print(f"   Telegram stop warning: {e}")

    # NEW: On shutdown, end current session with summary
    try:
        from session_manager import end_session
        if brain.session_id:
            summary = end_session(brain.session_id)
            print(f"   Session summary saved: {summary.get('summary', '')[:80]}")
    except Exception as e:
        print(f"   Session summary warning: {e}")

    print("👋 Cherry shutting down...")


app = FastAPI(
    title="🌸 Cherry — Personal AI Girlfriend",
    description="Rajjoo's mood-aware AI girlfriend + server assistant",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # NEW: optional, auto-detect if not given


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int
    note: Optional[str] = None


class PrefRequest(BaseModel):
    key: str
    value: str


@app.get("/")
async def root():
    return {
        "name": "🌸 Cherry — Personal AI Girlfriend",
        "version": "1.0.0",
        "status": "online",
        "time": datetime.now().isoformat(),
        "endpoints": {
            "chat": "/chat",
            "ws": "/ws/{session_id}",
            "greeting": "/greeting",
            "health": "/health",
            "stats": "/stats",
            "server": "/server/*",
            "agent": "/agent (coding agent with tools)",
            "tools": "/tools (list available tools)"
        }
    }


# ============================================================
# 💬 CHAT ENDPOINTS
# ============================================================
@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Chat endpoint — user-aware.
    Flow:
    1. Identify user (user_id given OR auto-create from device fingerprint)
    2. If user is new (onboarded=0) → send onboarding greeting, extract info from message
    3. Else: normal chat with user profile context
    """
    import user_manager
    from user_manager import (
        get_or_create_user, update_user_profile, is_onboarding_complete,
        extract_user_info_from_message
    )

    brain = get_brain()

    # ── Step 1: Identify user ──
    user_id = req.user_id or req.session_id or "guest"
    user = get_or_create_user(user_id)

    # Tie session to user
    if not brain.current_user or brain.current_user.get("user_id") != user_id:
        brain.set_user(user_id)
        if req.session_id:
            brain.session_id = req.session_id

    # ── Step 2: Onboarding flow ──
    if not is_onboarding_complete(user):
        # Try to extract name from current message
        extracted = extract_user_info_from_message(req.message)
        if extracted.get("display_name"):
            # User ne apna naam batadiya — onboard karo with default nicknames
            update_kwargs = {
                "display_name": extracted["display_name"],
                "pronouns": "she/her",
                "relationship": "friend",
                "vibe": "girl-girl bestie — warm, playful, caring, gossip-y",
                "mode": "friend",
                "nicknames": ["baby", "jaan", "sweetie"],  # common words allowed
                "onboarded": 1
            }
            # If message mentions "Anushka" or "Patil", save nicknames
            msg_lower = req.message.lower()
            if "anushka" in msg_lower:
                update_kwargs["nicknames"] = ["baby", "jaan", "Anu", "Patil ji", "sweetie"]
            user = update_user_profile(user_id, **update_kwargs)
            brain.current_user = user

            # Return onboarding complete greeting
            return {
                "response": f"Arey {extracted['display_name']}! Tera naam sun ke accha laga 🐱 Ab toh hum bestie ban gaye! Kya haal hai? Sab bata, time hai mera! 😽✨",
                "mood": "happy",
                "session_id": brain.session_id,
                "user_id": user_id,
                "display_name": extracted["display_name"],
                "onboarded": True,
                "time_of_day": get_time_of_day()
            }
        else:
            # Still onboarding — send greeting asking for name
            return {
                "response": user_manager.get_onboarding_greeting(),
                "mood": "playful",
                "session_id": brain.session_id,
                "user_id": user_id,
                "onboarded": False,
                "time_of_day": get_time_of_day()
            }

    # ── Step 3: Normal chat ──
    result = brain.think(req.message)
    return {
        "response": result["response"],
        "mood": result["mood"],
        "mood_info": result["mood_info"],
        "session_id": result["session_id"],
        "message_id": result["message_id"],
        "time_of_day": result["time_of_day"],
        "user_id": user_id,
        "display_name": user.get("display_name"),
        "llm_provider": result.get("llm_provider", "unknown"),
        "facts_extracted": result.get("facts_extracted", [])
    }


# ============================================================
# 👤 USER MANAGEMENT ENDPOINTS
# ============================================================
@app.get("/users")
async def list_all_users():
    """List all users Cherry knows about."""
    from user_manager import list_users
    return {"users": list_users()}


@app.get("/users/{user_id}")
async def get_user_info(user_id: str):
    """Get a specific user's profile."""
    from user_manager import get_user
    user = get_user(user_id)
    if not user:
        return {"error": "user not found"}
    return {"user": user}


@app.post("/users/{user_id}/update")
async def update_user_endpoint(user_id: str, body: dict):
    """
    Update user profile fields.
    Body: {"display_name": "...", "nicknames": [...], "vibe": "...", "facts": {...}}
    """
    from user_manager import update_user_profile
    user = update_user_profile(user_id, **body)
    return {"success": True, "user": user}


@app.delete("/users/{user_id}")
async def delete_user_endpoint(user_id: str):
    """Delete user and all their data."""
    from user_manager import delete_user
    delete_user(user_id)
    return {"success": True, "deleted": user_id}


@app.get("/chat/history")
async def chat_history(session_id: Optional[str] = None, user_id: Optional[str] = None, limit: int = 50):
    """
    Fetch chat history.
    Either session_id OR user_id (fetches all sessions for that user).
    """
    from memory import get_chat_history
    from user_manager import get_user_session_id

    if user_id and not session_id:
        # Fetch all sessions for this user
        session_id = get_user_session_id(user_id)

    if not session_id:
        return {"messages": []}

    return {"messages": get_chat_history(session_id, limit)}


# ============================================================
# 🛠️ AGENT ENDPOINTS (Coding agent with tools)
# ============================================================
@app.get("/tools")
async def list_tools():
    """List all available tools for the coding agent."""
    from tools.registry import get_tool_definitions
    defs = get_tool_definitions()
    return {
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"]
            }
            for t in defs
        ]
    }


class AgentRequest(BaseModel):
    task: str
    session_id: Optional[str] = None
    max_steps: int = 10  # max tool calls in chain


@app.post("/agent")
async def agent_run(req: AgentRequest):
    """
    Coding agent — Cherry reads files, edits, runs commands autonomously.
    Multi-step: can chain tool calls (read → edit → verify).
    Destructive commands require explicit 'haan kar de' confirmation.
    """
    from tools.registry import get_tool_definitions, execute_tool
    brain = get_brain()
    if req.session_id:
        brain.session_id = req.session_id
    else:
        brain.start_session()

    # Detect mood (focused for coding tasks)
    mood_info = detect_mood(req.task)
    mood = "focused"  # always focused for agent tasks
    time_of_day = get_time_of_day()

    # Save user request
    save_message(brain.session_id, "user", f"[AGENT] {req.task}", mood=mood, time_of_day=time_of_day)

    # Build system prompt for agent
    system_prompt = f"""You are Cherry in coding agent mode. You can use tools to read files, edit code, run commands, and search code.

WORKFLOW:
1. Use `list_dir` or `find_files` to understand the project structure
2. Use `read_file` to see existing code
3. Use `search_code` to find patterns
4. Use `edit_file` or `write_file` to make changes
5. Use `run_command` to test (SAFE commands only)
6. Verify your changes with another read or run

RULES:
- ONE tool call at a time, then wait for results
- For destructive commands (rm, docker stop, etc), tell the user first and wait for "haan kar de" confirmation
- Be efficient — don't read files you don't need
- Always end with a clear summary of what you did
- If a tool fails, try a different approach
- Use absolute paths

User task: {req.task}

Start by exploring the project, then make changes, then verify."""

    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": req.task})

    # Agent loop
    tools = get_tool_definitions()
    steps = []
    final_text = ""
    provider_used = "openrouter" if brain.openrouter.api_key else "ollama"

    for step_num in range(req.max_steps):
        # Get LLM response
        if brain.openrouter.api_key:
            result = brain.openrouter.chat(
                messages, temperature=0.3, max_tokens=2000, tools=tools
            )
        else:
            result = brain.ollama.chat(messages, temperature=0.3)

        if isinstance(result, dict) and "error" in result:
            error_msg = result.get("error", "unknown")
            return {"success": False, "error": error_msg, "steps": steps, "session_id": brain.session_id}

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        # Add assistant message to history
        messages.append(message)

        # Check if LLM wants to call a tool
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            # Final answer
            final_text = message.get("content", "")
            break

        # Execute each tool call
        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                arguments = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}

            # Execute
            tool_result = execute_tool(tool_name, arguments)

            # Track step
            steps.append({
                "step": step_num + 1,
                "tool": tool_name,
                "arguments": arguments,
                "result": tool_result,
                "timestamp": datetime.now().isoformat()
            })

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(tool_result)[:4000]  # limit size
            })

    # Save Cherry's final response
    if final_text:
        save_message(brain.session_id, "cherry", f"[AGENT] {final_text}", mood=mood, time_of_day=time_of_day)

    return {
        "success": True,
        "task": req.task,
        "final_response": final_text,
        "steps": steps,
        "total_steps": len(steps),
        "session_id": brain.session_id,
        "llm_provider": provider_used
    }


@app.get("/greeting")
async def greeting(user_id: Optional[str] = None):
    """
    User-aware greeting.
    - No user_id / new user → onboarding greeting
    - Existing user → returning personalized greeting
    """
    import user_manager
    from user_manager import get_or_create_user, is_onboarding_complete, get_returning_greeting

    brain = get_brain()

    # If user_id given, tie to user
    if user_id:
        user = get_or_create_user(user_id)
        brain.current_user = user
        brain.current_user_id = user_id

        if not is_onboarding_complete(user):
            return {
                "greeting": user_manager.get_onboarding_greeting(),
                "time_of_day": get_time_of_day(),
                "mood": "playful",
                "onboarded": False,
                "user_id": user_id
            }
        else:
            # Returning user
            brain.set_user(user_id)
            return {
                "greeting": get_returning_greeting(user),
                "time_of_day": get_time_of_day(),
                "mood": "happy",
                "onboarded": True,
                "user_id": user_id,
                "display_name": user.get("display_name")
            }

    # No user_id (legacy mode — Rajjoo)
    return {
        "greeting": brain.get_greeting(),
        "time_of_day": get_time_of_day(),
        "mood": brain.last_mood or "playful"
    }


@app.post("/proactive")
async def proactive():
    brain = get_brain()
    return {"question": brain.get_proactive_question()}


# ============================================================
# 🎭 MOOD & PREFERENCES
# ============================================================
@app.get("/mood/{mood}")
async def mood_info(mood: str):
    from prompts import MOOD_PROMPTS, FAREWELLS
    return {
        "mood": mood,
        "prompt_preview": MOOD_PROMPTS.get(mood, "Not found")[:200],
        "farewells": FAREWELLS.get(mood, [])
    }


@app.get("/prefs")
async def get_prefs():
    return {"preferences": get_all_prefs()}


@app.post("/prefs")
async def set_pref(req: PrefRequest):
    set_user_pref(req.key, req.value)
    return {"success": True, "key": req.key, "value": req.value}


@app.post("/feedback")
async def feedback(req: FeedbackRequest):
    save_feedback(req.message_id, req.rating, req.note)
    # NEW: Learning from feedback
    try:
        from learning import record_feedback_with_learning
        from memory import get_chat_history
        history = get_chat_history(session_id="", limit=50)
        user_msg = ""
        cherry_resp = ""
        for msg in history:
            if msg.get("id") == req.message_id:
                # Get previous user message
                idx = history.index(msg)
                if idx > 0:
                    user_msg = history[idx - 1].get("content", "") if history[idx - 1].get("role") == "user" else ""
                cherry_resp = msg.get("content", "")
                break
        result = record_feedback_with_learning(
            message_id=req.message_id,
            rating=req.rating,
            user_message=user_msg,
            cherry_response=cherry_resp
        )
        return {
            "success": True,
            "message_id": req.message_id,
            "rating": req.rating,
            "learning": result
        }
    except Exception as e:
        return {"success": True, "message_id": req.message_id, "rating": req.rating, "learning_error": str(e)}


# ============================================================
# 🧠 PERSONAL ASSISTANT ENDPOINTS (NEW)
# ============================================================
@app.get("/facts")
async def list_facts(category: str = None, limit: int = 50):
    """List all learned facts. Optional filter by category."""
    from memory import get_facts
    return {"facts": get_facts(category=category, limit=limit)}


@app.delete("/facts/{fact_id}")
async def remove_fact(fact_id: int):
    """Delete a specific fact."""
    from memory import delete_fact
    delete_fact(fact_id)
    return {"success": True, "deleted": fact_id}


@app.get("/learning/stats")
async def learning_stats():
    """Get self-learning system stats."""
    from learning import get_learning_stats
    return get_learning_stats()


@app.post("/memory/sync")
async def sync_agents():
    """Manually trigger .agents folder sync."""
    from session_manager import sync_from_agents
    return sync_from_agents()


@app.get("/memory/search")
async def memory_search(q: str, top_k: int = 5):
    """Semantic search over all memories (RAG)."""
    from embeddings import search
    return {"query": q, "results": search(q, top_k=top_k)}


@app.post("/session/end")
async def end_current_session():
    """End current session with summary."""
    brain = get_brain()
    if not brain.session_id:
        return {"error": "no active session"}
    from session_manager import end_session
    summary = end_session(brain.session_id)
    return {"session_id": brain.session_id, "summary": summary}


@app.get("/session/recap/{session_id}")
async def session_recap(session_id: str):
    """Get saved summary for a specific session."""
    from session_manager import get_session_recap
    return get_session_recap(session_id) or {"error": "not found"}


@app.post("/memory/index-all")
async def index_all_memories():
    """Index all facts and recent chats into RAG store."""
    from embeddings import index_all_facts, index_recent_chats
    facts_indexed = index_all_facts()
    chats_indexed = index_recent_chats(limit=50)
    return {"facts_indexed": facts_indexed, "chats_indexed": chats_indexed}


# ============================================================
# 🛡️ SERVER OPERATIONS
# ============================================================
@app.get("/server/status")
async def server_status():
    ops = get_ops()
    return {
        "mode": "local" if ops.local else "remote",
        "host": ops.ssh_host,
        "ollama": ops.ollama_status(),
        "production_health": ops.check_production_health()
    }


@app.get("/telegram/status")
async def telegram_status():
    """Health check for the Telegram bridge."""
    try:
        from telegram_bot import get_telegram_bot, TELEGRAM_AVAILABLE
        bot = get_telegram_bot()
        info = {
            "lib_available": TELEGRAM_AVAILABLE,
            "has_token": bool(bot.token),
            "enabled": bot.is_enabled(),
            "ready": bot._ready,
            "allowed_ids_configured": bot.allowed_ids is not None,
            "active_sessions": len(bot.session_map),
        }
        if bot.is_enabled() and bot.app and bot._ready:
            try:
                me = await bot.app.bot.get_me()
                info["bot_username"] = me.username
                info["bot_id"] = me.id
                info["polling_running"] = bot.app.updater.running
            except Exception as e:
                info["bot_info_error"] = str(e)
        if bot._last_error:
            info["last_error"] = bot._last_error
        return info
    except Exception as e:
        return {"enabled": False, "error": str(e)}


@app.get("/server/docker/ps")
async def docker_ps():
    return get_ops().docker_ps()


@app.get("/server/docker/stats")
async def docker_stats():
    return get_ops().docker_stats()


@app.get("/server/disk")
async def disk_usage():
    return get_ops().execute_read("df -h /")


@app.get("/server/memory")
async def memory_usage():
    return get_ops().execute_read("free -h")


@app.get("/server/uptime")
async def uptime():
    return get_ops().execute_read("uptime")


@app.get("/server/logs/{container}")
async def container_logs(container: str, lines: int = 50):
    return get_ops().docker_logs(container, lines)


# ============================================================
# 📊 STATS
# ============================================================
@app.get("/health")
async def health():
    brain = get_brain()
    return {
        "status": "healthy",
        "time": datetime.now().isoformat(),
        "llm_provider": brain.llm_provider,
        "openrouter": brain.openrouter.health_check() if brain.openrouter.api_key else {"status": "no_api_key"},
        "ollama": get_client().health_check(),
        "stats": get_stats()
    }


@app.get("/stats")
async def stats():
    return {"stats": get_stats(), "mood_patterns": get_mood_patterns()}


@app.get("/sessions")
async def sessions():
    return {"sessions": get_all_sessions()}


# ============================================================
# 🌐 WEBSOCKET
# ============================================================
@app.websocket("/ws/{user_or_session_id}")
async def websocket_endpoint(websocket: WebSocket, user_or_session_id: str):
    """
    WebSocket — user-aware.
    The path param can be user_id (we'll resolve to user's session).
    Or legacy: raw session_id.
    """
    await websocket.accept()
    brain = get_brain()

    # Try as user_id first
    import user_manager
    from user_manager import get_or_create_user, is_onboarding_complete

    user = get_or_create_user(user_or_session_id)
    is_user_mode = True

    # If user exists and onboarded, use user mode
    if user and is_onboarding_complete(user):
        brain.set_user(user_or_session_id)
        # Send returning user greeting
        from user_manager import get_returning_greeting
        await websocket.send_json({
            "type": "greeting",
            "data": {
                "message": get_returning_greeting(user),
                "time_of_day": get_time_of_day(),
                "mood": "happy",
                "onboarded": True,
                "display_name": user.get("display_name")
            }
        })
    else:
        # Legacy mode (or new user onboarding)
        brain.session_id = user_or_session_id
        if user and not is_onboarding_complete(user):
            # New user — onboarding greeting
            await websocket.send_json({
                "type": "greeting",
                "data": {
                    "message": user_manager.get_onboarding_greeting(),
                    "time_of_day": get_time_of_day(),
                    "mood": "playful",
                    "onboarded": False,
                    "user_id": user_or_session_id
                }
            })
        else:
            # Legacy mode
            await websocket.send_json({
                "type": "greeting",
                "data": {
                    "message": brain.get_greeting(),
                    "time_of_day": get_time_of_day(),
                    "mood": "playful"
                }
            })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg_data = json.loads(data)
                user_message = msg_data.get("message", "")
                msg_user_id = msg_data.get("user_id")
            except json.JSONDecodeError:
                user_message = data
                msg_user_id = None

            if not user_message.strip():
                continue

            # Onboarding via WS: detect name in first message
            if brain.current_user and not is_onboarding_complete(brain.current_user):
                from user_manager import extract_user_info_from_message, update_user_profile
                extracted = extract_user_info_from_message(user_message)
                if extracted.get("display_name"):
                    update_kwargs = {
                        "display_name": extracted["display_name"],
                        "pronouns": "she/her",
                        "relationship": "friend",
                        "vibe": "girl-girl bestie — warm, playful, caring",
                        "mode": "friend",
                        "nicknames": ["baby", "jaan", "sweetie"],
                        "onboarded": 1
                    }
                    msg_lower = user_message.lower()
                    if "anushka" in msg_lower:
                        update_kwargs["nicknames"] = ["baby", "jaan", "Anu", "Patil ji", "sweetie"]
                    brain.current_user = update_user_profile(brain.current_user_id, **update_kwargs)
                    await websocket.send_json({
                        "type": "onboarded",
                        "data": {
                            "message": f"Arey {extracted['display_name']}! Tera naam sun ke accha laga 🐱 Ab toh hum bestie ban gaye! Kya haal hai? Sab bata! 😽✨",
                            "display_name": extracted["display_name"]
                        }
                    })
                    continue

            await websocket.send_json({"type": "typing", "data": {"status": "Cherry is typing..."}})
            result = await asyncio.to_thread(brain.think, user_message)
            await websocket.send_json({
                "type": "message",
                "data": {
                    "response": result["response"],
                    "mood": result["mood"],
                    "mood_info": result["mood_info"],
                    "message_id": result["message_id"],
                    "time_of_day": result["time_of_day"]
                }
            })
    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {user_or_session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("CHERRY_PORT", "3003"))
    print(f"\n🌸 Cherry starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
