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

    print("✅ Cherry ready!")
    yield

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
    user_id: str = "rajjoo"


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
    brain = get_brain()
    if req.session_id:
        brain.session_id = req.session_id
    else:
        brain.start_session()
    result = brain.think(req.message)
    return {
        "response": result["response"],
        "mood": result["mood"],
        "mood_info": result["mood_info"],
        "session_id": result["session_id"],
        "message_id": result["message_id"],
        "time_of_day": result["time_of_day"],
        "llm_provider": result.get("llm_provider", "unknown"),
        "facts_extracted": result.get("facts_extracted", [])
    }


@app.get("/chat/history")
async def chat_history(session_id: str, limit: int = 50):
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
async def greeting():
    brain = get_brain()
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
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    brain = get_brain()
    brain.session_id = session_id
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
            except json.JSONDecodeError:
                user_message = data

            if not user_message.strip():
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
        print(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("CHERRY_PORT", "3003"))
    print(f"\n🌸 Cherry starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
