"""
Session Manager - Cross-session memory + .agents sync.
Har session ka summary banata hai aur naye session mein continuity deta hai.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from memory import (
    get_chat_history, save_session_summary, get_session_summary,
    get_all_session_summaries, get_mood_patterns, get_stats_v2
)
from openrouter_client import OpenRouterClient
from ollama_client import OllamaClient


def _call_llm_simple(prompt: str, max_tokens: int = 200) -> Optional[str]:
    """OpenRouter ya Ollama se simple completion."""
    try:
        client = OpenRouterClient()
        if client.api_key:
            result = client.chat(
                messages=[
                    {"role": "system", "content": "You are a helpful summarizer. Follow format strictly."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )
            if isinstance(result, dict) and "choices" in result:
                return result["choices"][0]["message"]["content"]
    except Exception:
        pass
    try:
        client = OllamaClient()
        result = client.chat(
            messages=[
                {"role": "system", "content": "You are a helpful summarizer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        if isinstance(result, dict) and "message" in result:
            return result["message"].get("content", "")
    except Exception:
        pass
    return None


def _parse_summary(text: str, msg_count: int) -> Dict:
    summary = ""
    topics = []
    mood = "neutral"
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line.replace("SUMMARY:", "").strip()
        elif line.startswith("TOPICS:"):
            topics = [t.strip() for t in line.replace("TOPICS:", "").split(",") if t.strip()]
        elif line.startswith("MOOD:"):
            mood = line.replace("MOOD:", "").strip().lower()
    if not summary:
        summary = text[:300]
    return {
        "summary": summary,
        "key_topics": ",".join(topics[:5]),
        "mood_summary": mood,
        "msg_count": msg_count
    }


def _simple_summary(history: List[Dict], msg_count: int) -> Dict:
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    moods = [m.get("mood", "") for m in history if m.get("mood")]
    common_words = ["server", "docker", "code", "project", "baby", "paan",
                    "nas", "deploy", "bug", "feature", "test", "love"]
    topics = []
    for word in common_words:
        if any(word in m.lower() for m in user_msgs):
            topics.append(word)
    summary = f"Session with {msg_count} user messages. "
    if topics:
        summary += f"Discussed: {', '.join(topics[:3])}."
    if moods:
        from collections import Counter
        common_mood = Counter(moods).most_common(1)[0][0]
        summary += f" Overall mood: {common_mood}."
    return {
        "summary": summary,
        "key_topics": ",".join(topics[:5]),
        "mood_summary": moods[0] if moods else "neutral",
        "msg_count": msg_count
    }


def summarize_session(session_id: str, use_llm: bool = True) -> Dict:
    history = get_chat_history(session_id, limit=100)
    if not history:
        return {"summary": "Empty session", "key_topics": [], "mood_summary": "neutral"}
    user_msgs = [m for m in history if m["role"] == "user"]
    cherry_msgs = [m for m in history if m["role"] == "cherry"]
    msg_count = len(user_msgs)
    if msg_count == 0:
        return {"summary": "No user messages", "key_topics": [], "mood_summary": "neutral"}
    convo_lines = []
    for m in history[-20:]:
        role = "User" if m["role"] == "user" else "Cherry"
        convo_lines.append(f"{role}: {m['content'][:150]}")
    convo_text = "\n".join(convo_lines)
    if use_llm:
        prompt = f"""Summarize this conversation between User (Rajjoo) and Cherry (his AI girlfriend) in 2-3 sentences.
Then list 3-5 key topics discussed (comma-separated).
Then describe the overall mood in 1-2 words.

Conversation:
{convo_text}

Format your response EXACTLY like this:
SUMMARY: <2-3 sentence summary>
TOPICS: <topic1>, <topic2>, <topic3>
MOOD: <mood>"""
        summary_text = _call_llm_simple(prompt, max_tokens=200)
        if summary_text and "SUMMARY:" in summary_text:
            return _parse_summary(summary_text, msg_count)
    return _simple_summary(history, msg_count)


def end_session(session_id: str) -> Dict:
    summary = summarize_session(session_id)
    save_session_summary(
        session_id=session_id,
        summary=summary["summary"],
        key_topics=summary.get("key_topics", ""),
        mood_summary=summary.get("mood_summary", "neutral"),
        message_count=summary.get("msg_count", 0)
    )
    return summary


def build_session_continuity_context(limit: int = 3) -> str:
    summaries = get_all_session_summaries(limit=limit)
    if not summaries:
        return ""
    lines = ["[RECENT SESSIONS]"]
    for s in summaries:
        date = s.get("created_at", "")[:10]
        lines.append(
            f"- [{date}] {s.get('summary', '')[:150]} "
            f"(topics: {s.get('key_topics', 'none')}, mood: {s.get('mood_summary', '?')})"
        )
    return "\n".join(lines)


def get_session_recap(session_id: str) -> Optional[Dict]:
    return get_session_summary(session_id)


AGENTS_PATH = Path(__file__).parent.parent.parent / ".agents"


def sync_from_agents(user_id: str = "rajjoo") -> Dict:
    """.agents/ folder se facts load karta hai."""
    if not AGENTS_PATH.exists():
        return {"status": "no_agents_folder", "loaded": 0}
    loaded = {"preferences": 0, "facts": 0, "projects": 0}
    user_profile = AGENTS_PATH / "memory" / "user-profile.md"
    if user_profile.exists():
        content = user_profile.read_text()
        if "Name:" in content:
            name_match = content.split("Name:")[1].split("|")[0].strip()
            if name_match:
                _save_pref("user_name", name_match)
                loaded["preferences"] += 1
        if "Brand:" in content:
            brand_match = content.split("Brand:")[1].split("|")[0].strip()
            if brand_match:
                _save_pref("brand", brand_match)
                loaded["preferences"] += 1
        if "Goal:" in content:
            goal_match = content.split("Goal:")[1].split("|")[0].strip()
            if goal_match:
                _save_pref("goal", goal_match)
                loaded["preferences"] += 1
    prefs_file = AGENTS_PATH / "memory" / "preferences.md"
    if prefs_file.exists():
        loaded["preferences"] += _parse_bullets(prefs_file.read_text(), "preference")
    learnings = AGENTS_PATH / "memory" / "learnings.md"
    if learnings.exists():
        loaded["facts"] += _parse_bullets(learnings.read_text(), "learning", limit=10)
    return {"status": "synced", "loaded": loaded}


def _save_pref(key: str, value: str):
    try:
        from memory import set_user_pref
        set_user_pref(f"agents:{key}", value)
    except Exception:
        pass


def _parse_bullets(content: str, category: str, limit: int = 20) -> int:
    count = 0
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            if 5 < len(text) < 200 and not text.startswith("_"):
                try:
                    from memory import save_fact
                    save_fact(
                        category=category,
                        key=f"agents:{text[:50]}",
                        value=text,
                        source=".agents",
                        confidence=0.9
                    )
                    count += 1
                    if count >= limit:
                        break
                except Exception:
                    pass
    return count


if __name__ == "__main__":
    print("Session Manager Test")
    print("=" * 50)
    result = sync_from_agents()
    print(f"\n.agents sync: {result}")
    ctx = build_session_continuity_context(limit=3)
    print(f"\nSession continuity context:\n{ctx}")