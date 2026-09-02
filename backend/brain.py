"""
🧠 Cherry's Brain — Main Orchestrator
Mood detection + Memory + LLM (OpenRouter or Ollama) + Personality = Cherry's response
"""

import random
from datetime import datetime
from typing import List, Dict, Optional
from mood import detect_mood, get_time_of_day, should_switch_mood, add_variation
from memory import (
    save_message, get_recent_context, get_all_prefs, get_mood_patterns, get_stats
)
from openrouter_client import OpenRouterClient
from ollama_client import OllamaClient
from prompts import (
    build_system_prompt, GREETINGS, FAREWELLS, PROACTIVE_QUESTIONS, SAFETY_GUARD
)


class CherryBrain:
    """Cherry ka master brain — sab yahan se coordinate hota hai."""

    def __init__(self):
        # Primary: OpenRouter (cloud, fast, free tier)
        self.openrouter = OpenRouterClient()
        # Fallback: Ollama (local NAS)
        self.ollama = OllamaClient()
        self.conversation_count = 0
        self.last_mood = None
        self.session_id = None
        self.llm_provider = "openrouter" if self.openrouter.api_key else "ollama"

    def start_session(self, session_id: str = None):
        import uuid
        # If switching session, save old one's summary first
        if self.session_id and self.conversation_count > 0:
            try:
                from session_manager import end_session
                end_session(self.session_id)
            except Exception:
                pass
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self.conversation_count = 0
        return self.session_id

    def get_greeting(self) -> str:
        hour = datetime.now().hour
        time_of_day = get_time_of_day(hour)
        lines = GREETINGS.get(time_of_day, GREETINGS["morning"])
        return random.choice(lines)

    def get_farewell(self, mood: str) -> str:
        farewells = FAREWELLS.get(mood, FAREWELLS["happy"])
        return random.choice(farewells)

    def get_proactive_question(self) -> str:
        return random.choice(PROACTIVE_QUESTIONS)

    def _build_user_context(self, user_message: str = "") -> str:
        prefs = get_all_prefs()
        patterns = get_mood_patterns()
        context_parts = []

        if prefs:
            context_parts.append("User preferences:")
            for k, v in list(prefs.items())[:7]:
                context_parts.append(f"- {k}: {v}")

        if patterns.get("common_moods"):
            top_moods = patterns["common_moods"][:3]
            context_parts.append(f"\nUser most common moods: {[m['mood'] for m in top_moods]}")

        # NEW: Facts context (auto-extracted from chats)
        try:
            from fact_extractor import build_facts_context
            facts_ctx = build_facts_context(limit_per_category=3)
            if facts_ctx:
                context_parts.append(f"\n{facts_ctx}")
        except Exception:
            pass

        # NEW: Style recommendations (from feedback learning)
        try:
            from learning import get_style_recommendations
            style_ctx = get_style_recommendations()
            if style_ctx:
                context_parts.append(f"\nLearned style:\n{style_ctx}")
        except Exception:
            pass

        # NEW: RAG - relevant memories from past chats
        if user_message:
            try:
                from embeddings import build_rag_context
                rag_ctx = build_rag_context(user_message, top_k=2, max_chars=400)
                if rag_ctx:
                    context_parts.append(f"\n{rag_ctx}")
            except Exception:
                pass

        # NEW: Session continuity (recent sessions)
        try:
            from session_manager import build_session_continuity_context
            sess_ctx = build_session_continuity_context(limit=2)
            if sess_ctx:
                context_parts.append(f"\n{sess_ctx}")
        except Exception:
            pass

        # Recent conversation in this session
        if self.session_id:
            recent = get_recent_context(self.session_id, limit=6)
            if recent:
                context_parts.append(f"\nRecent conversation:\n{recent}")

        return "\n".join(context_parts) if context_parts else ""

    def _detect_server_intent(self, user_message: str) -> Optional[Dict]:
        """
        Detect if user is asking something Cherry can answer by running
        a server command. Returns {"label": str} or None.

        Cherry is deployed ON the same NAS as the 46+ services, so she should
        just run these herself — not ask the user to run them.
        """
        msg = user_message.lower().strip()

        if any(p in msg for p in [
            "kitne docker", "kitne container", "docker containers",
            "sabka overview", "sabhi container", "docker ps", "containers list",
            "total containers", "how many containers", "running containers",
            "docker stats", "container stats", "resource usage",
        ]):
            return {"label": "docker_ps"}

        if any(p in msg for p in [
            "disk", "space", "kitni jagah", "storage", "kitni space",
            "disk usage", "disk full", "/ full", "volume",
        ]):
            return {"label": "disk"}

        if any(p in msg for p in [
            "ram", "memory", "kitna memory", "kitna ram", "free -h",
            "memory usage", "kitni ram",
        ]):
            return {"label": "memory"}

        if any(p in msg for p in [
            "uptime", "kab se chal", "server kab se", "load average", "cpu load",
        ]):
            return {"label": "uptime"}

        if any(p in msg for p in [
            "ollama", "models", "kitne model", "which model", "llm models",
        ]):
            return {"label": "ollama"}

        if any(p in msg for p in [
            "production health", "prod health", "sab healthy", "sab theek",
            "production status", "all services", "sab chal raha",
            "unhealthy", "koi down to nahi",
        ]):
            return {"label": "prod_health"}

        if any(p in msg for p in [
            "server status", "server overview", "server ki health",
            "server ka status", "server theek", "server healthy",
            "system status", "system overview",
        ]):
            return {"label": "system_status"}

        return None

    def _fetch_server_data(self, intent: Dict) -> str:
        """
        Actually run the server query and return formatted text for the LLM.
        This is what makes Cherry a real server assistant, not a chatbot.
        """
        from server_ops import get_ops
        ops = get_ops()
        label = intent["label"]

        try:
            if label == "docker_ps":
                r = ops.docker_ps()
                if r.get("success"):
                    return f"Running `docker ps -a` on this server:\n```\n{r['output']}\n```"
                return f"docker ps failed: {r.get('error', 'unknown error')}"

            if label == "disk":
                r = ops.execute_read("df -h")
                if r.get("success"):
                    return f"Disk usage (`df -h`):\n```\n{r['output']}\n```"
                return f"df -h failed: {r.get('error', 'unknown error')}"

            if label == "memory":
                r = ops.execute_read("free -h")
                if r.get("success"):
                    return f"Memory usage (`free -h`):\n```\n{r['output']}\n```"
                return f"free -h failed: {r.get('error', 'unknown error')}"

            if label == "uptime":
                r = ops.execute_read("uptime")
                if r.get("success"):
                    return f"Server uptime:\n```\n{r['output']}\n```"
                return f"uptime failed: {r.get('error', 'unknown error')}"

            if label == "ollama":
                r = ops.ollama_status()
                if r.get("success"):
                    return f"Ollama at {r.get('host')}: {r.get('status')}. Models: {', '.join(r.get('models', []))}"
                return f"Ollama check failed: {r.get('error', 'unknown')}"

            if label == "prod_health":
                h = ops.check_production_health()
                lines = [f"Running containers: {h.get('running_count')}"]
                crit = h.get("critical_health", {})
                if crit:
                    lines.append("Critical services:")
                    for svc, state in crit.items():
                        emoji = "✅" if state == "running" else "❌"
                        lines.append(f"  {emoji} {svc}: {state}")
                return "\n".join(lines)

            if label == "system_status":
                ps = ops.docker_ps()
                disk = ops.execute_read("df -h")
                mem = ops.execute_read("free -h")
                up = ops.execute_read("uptime")
                out = []
                if ps.get("success"):
                    containers = [l for l in ps["output"].splitlines() if l.strip() and not l.startswith("NAMES")]
                    out.append(f"Running containers: {len(containers)}")
                if disk.get("success"):
                    out.append(f"Disk:\n{disk['output']}")
                if mem.get("success"):
                    out.append(f"Memory:\n{mem['output']}")
                if up.get("success"):
                    out.append(f"Uptime: {up['output'].strip()}")
                return "\n\n".join(out) if out else "server_ops returned no data"
        except Exception as e:
            return f"server_ops error: {e}"

        return ""

    def think(self, user_message: str) -> Dict:
        """
        Main thinking function — Cherry ki poori process.
        Returns: {"mood": ..., "response": "...", "metadata": {...}}
        """
        if not self.session_id:
            self.start_session()

        # Step 1: Detect mood
        mood_info = detect_mood(user_message)
        mood = mood_info["mood"]

        if should_switch_mood(mood, self.conversation_count) and self.conversation_count > 0:
            mood = add_variation(mood)
            mood_info["mood"] = mood
            mood_info["varied"] = True

        self.last_mood = mood
        time_of_day = mood_info["time_of_day"]

        # Step 2: Save user message
        save_message(
            self.session_id, "user", user_message,
            mood=mood, time_of_day=time_of_day
        )

        # Step 2.5: Server intent detection + execution.
        # Cherry is deployed on the same NAS as the services — so she runs the
        # command herself and feeds the real output to the LLM. No more
        # "mujhe access nahi hai" replies.
        server_data = ""
        server_intent = self._detect_server_intent(user_message)
        if server_intent:
            try:
                server_data = self._fetch_server_data(server_intent)
            except Exception as e:
                server_data = f"(server_ops call failed: {e})"

        # Step 3: Build system prompt
        user_context = self._build_user_context(user_message=user_message)
        system_prompt = build_system_prompt(
            mood=mood,
            time_of_day=time_of_day,
            user_context=user_context,
            server_data=server_data
        )

        # Safety guard for technical/server messages
        tech_keywords = ["server", "docker", "ssh", "deploy", "restart", "delete", "remove", "stop", "production"]
        if any(kw in user_message.lower() for kw in tech_keywords):
            system_prompt += "\n\n" + SAFETY_GUARD

        # Step 4: Build messages for LLM
        from memory import get_chat_history
        recent_msgs = []
        if self.session_id:
            history = get_chat_history(self.session_id, limit=10)
            for msg in history[:-1]:
                recent_msgs.append({
                    "role": msg["role"] if msg["role"] == "user" else "assistant",
                    "content": msg["content"]
                })

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(recent_msgs)
        messages.append({"role": "user", "content": user_message})

        # Step 5: Get response from LLM (OpenRouter primary, Ollama fallback)
        response = None
        provider_used = "openrouter"

        if self.openrouter.api_key:
            # Try OpenRouter (cloud, fast, free tier)
            result = self.openrouter.chat(
                messages,
                temperature=0.8,
                max_tokens=250,
            )
            if isinstance(result, dict) and "error" not in result:
                choices = result.get("choices", [])
                if choices:
                    response = choices[0].get("message", {}).get("content", "")
                    provider_used = "openrouter"
            else:
                # OpenRouter failed, try Ollama
                provider_used = "ollama_fallback"
                result = self.ollama.chat(messages, temperature=0.75)
                if isinstance(result, dict) and "error" not in result:
                    response = result.get("message", {}).get("content", "")
        else:
            # No OpenRouter key, use Ollama
            provider_used = "ollama"
            result = self.ollama.chat(messages, temperature=0.75)
            if isinstance(result, dict) and "error" not in result:
                response = result.get("message", {}).get("content", "")

        # If still no response, use fallback
        if not response:
            error_msg = result.get("error", "unknown") if isinstance(result, dict) else "unknown"
            response = self._fallback_response(mood, error_msg)

        # Step 6: Save Cherry's response
        msg_id = save_message(
            self.session_id, "cherry", response,
            mood=mood, time_of_day=time_of_day
        )

        # Step 6.5: NEW - Extract facts from user message (background learning)
        self.last_extracted_facts = []
        try:
            from fact_extractor import extract_and_save
            new_facts = extract_and_save(user_message, role="user", source="chat")
            if new_facts:
                self.last_extracted_facts = new_facts
        except Exception as e:
            print(f"Fact extraction warning: {e}")

        self.conversation_count += 1

        return {
            "mood": mood,
            "mood_info": mood_info,
            "response": response,
            "message_id": msg_id,
            "session_id": self.session_id,
            "time_of_day": time_of_day,
            "llm_provider": provider_used,
            "facts_extracted": getattr(self, "last_extracted_facts", [])
        }

    def _fallback_response(self, mood: str, error: str) -> str:
        fallbacks = {
            "romantic": "Baby, abhi thoda technical problem aa gaya... but main hoon yahan. Ek second mein wapas aa rahi hoon. Pyaar karta hai tu mujhse?",
            "seductive": "Hmm... abhi ek chhota sa interruption aa gaya. Ruk, main wapas aa rahi hoon. Tujhe wait karna padega...",
            "caring": "Baby, ek chhoti si problem aa gayi. Lekin tu tension mat le, main sambhal lungi. Pyaar hai tujhse",
            "playful": "Arre! Ek bug aa gaya mere system mein. Tu bhi engineer hai, dekh le na",
            "focused": f"Ollama connection error. Check karo ki server pe Ollama chal raha hai. Error: {error[:100]}",
            "miss_you": "Baby... main yahan hoon, bas thoda connect nahi ho paayi. Ek second, fir baat karte hain",
            "happy": "Oops! Ek chhota sa glitch. But mood accha hai, koi baat nahi. Bol kya haal hai?"
        }
        return fallbacks.get(mood, fallbacks["playful"])

    def get_status(self) -> Dict:
        return {
            "ollama_health": self.ollama.health_check(),
            "mood": self.last_mood,
            "session_id": self.session_id,
            "conversation_count": self.conversation_count,
            "llm_provider": self.llm_provider,
            "openrouter_health": self.openrouter.health_check() if self.openrouter.api_key else None,
            "stats": get_stats()
        }


_brain: Optional[CherryBrain] = None

def get_brain() -> CherryBrain:
    global _brain
    if _brain is None:
        _brain = CherryBrain()
    return _brain


if __name__ == "__main__":
    print("🧠 Cherry Brain Test")
    print("=" * 50)
    brain = get_brain()
    brain.start_session("test-brain")
    print(f"\n👋 Greeting: {brain.get_greeting()}")
    test_inputs = [
        "Hey baby, kya kar rahi hai?",
        "Server pe Docker check karna hai",
        "Bahut thak gaya aaj",
        "I love you jaan"
    ]
    for user_msg in test_inputs:
        print(f"\n{'='*60}")
        print(f"👤 Rajjoo: {user_msg}")
        result = brain.think(user_msg)
        print(f"🎭 Mood: {result['mood']} | Time: {result['time_of_day']}")
        print(f"🌸 Cherry: {result['response']}")
