"""
💾 Cherry's Memory System
Chat history, user preferences, learning — sab SQLite mein.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional


# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "cherry_memory.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db():
    """SQLite connection with WAL mode for performance."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Database tables create karta hai."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            mood TEXT,
            time_of_day TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mood_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mood TEXT NOT NULL,
            time_of_day TEXT,
            user_message_preview TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            rating INTEGER,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message_count INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS server_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            description TEXT,
            result TEXT,
            success INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            remind_at TIMESTAMP NOT NULL,
            completed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 🧠 NEW: Long-term facts (extracted from chats)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT,
            mentions INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, key)
        )
    """)

    # 🔍 NEW: Embeddings metadata (vectors stored separately)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            content_id INTEGER,
            content_text TEXT NOT NULL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 📝 NEW: Session summaries (cross-session memory)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_summaries (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            key_topics TEXT,
            mood_summary TEXT,
            message_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 🎯 NEW: Learned response patterns (from feedback)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_value TEXT NOT NULL,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pattern_type, pattern_value)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# 💬 MESSAGE OPERATIONS
# ============================================================
def save_message(session_id: str, role: str, content: str, mood: str = None,
                 time_of_day: str = None, metadata: Dict = None) -> int:
    """Ek message save karta hai."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages (session_id, role, content, mood, time_of_day, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, role, content, mood, time_of_day,
          json.dumps(metadata) if metadata else None))
    msg_id = cur.lastrowid
    cur.execute("""
        INSERT INTO sessions (session_id, message_count) VALUES (?, 1)
        ON CONFLICT(session_id) DO UPDATE SET
            last_active = CURRENT_TIMESTAMP,
            message_count = message_count + 1
    """, (session_id,))
    if role == "user" and mood:
        cur.execute("""
            INSERT INTO mood_history (mood, time_of_day, user_message_preview)
            VALUES (?, ?, ?)
        """, (mood, time_of_day, content[:100]))
    conn.commit()
    conn.close()
    return msg_id


def get_chat_history(session_id: str, limit: int = 20) -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?", (session_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_recent_context(session_id: str, limit: int = 10) -> str:
    history = get_chat_history(session_id, limit)
    if not history:
        return ""
    lines = []
    for msg in history:
        role = "Rajjoo" if msg["role"] == "user" else "Cherry"
        lines.append(f"{role}: {msg['content'][:200]}")
    return "\n".join(lines)


def get_all_sessions() -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions ORDER BY last_active DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# 👤 USER PROFILE
# ============================================================
def set_user_pref(key: str, value: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_profile (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (key, value))
    conn.commit()
    conn.close()


def get_user_pref(key: str, default: str = None) -> Optional[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM user_profile WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def get_all_prefs() -> Dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_profile")
    rows = cur.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ============================================================
# 🧠 MOOD PATTERNS
# ============================================================
def get_mood_patterns() -> Dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT mood, COUNT(*) as count FROM mood_history WHERE created_at > datetime('now', '-30 days') GROUP BY mood ORDER BY count DESC")
    common_moods = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT time_of_day, mood, COUNT(*) as count FROM mood_history WHERE created_at > datetime('now', '-30 days') GROUP BY time_of_day, mood ORDER BY time_of_day, count DESC")
    mood_by_time = {}
    for r in cur.fetchall():
        tod = r["time_of_day"]
        if tod not in mood_by_time:
            mood_by_time[tod] = []
        mood_by_time[tod].append({"mood": r["mood"], "count": r["count"]})
    conn.close()
    return {"common_moods": common_moods, "mood_by_time_of_day": mood_by_time}


# ============================================================
# 👍 FEEDBACK & SERVER TASKS
# ============================================================
def save_feedback(message_id: int, rating: int, note: str = None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO feedback (message_id, rating, note) VALUES (?, ?, ?)", (message_id, rating, note))
    conn.commit()
    conn.close()


def log_server_task(task_type: str, description: str, result: str, success: bool):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO server_tasks (task_type, description, result, success) VALUES (?, ?, ?, ?)", (task_type, description, result, int(success)))
    conn.commit()
    conn.close()


# ============================================================
# ⏰ REMINDERS
# ============================================================
def add_reminder(message: str, remind_at: datetime):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO reminders (message, remind_at) VALUES (?, ?)", (message, remind_at.isoformat()))
    conn.commit()
    conn.close()


def get_pending_reminders() -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE completed = 0 AND remind_at <= datetime('now') ORDER BY remind_at ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_reminder(reminder_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# ============================================================
# 📊 STATS
# ============================================================
def get_stats() -> Dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM messages WHERE role='user'")
    user_msgs = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM messages WHERE role='cherry'")
    cherry_msgs = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM sessions")
    sessions_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM server_tasks")
    tasks_count = cur.fetchone()["c"]
    conn.close()
    return {
        "total_user_messages": user_msgs,
        "total_cherry_messages": cherry_msgs,
        "total_sessions": sessions_count,
        "total_server_tasks": tasks_count
    }


init_db()


# ============================================================
# 🧠 FACTS — Long-term extracted knowledge
# ============================================================
def save_fact(category: str, key: str, value: str, source: str = None, confidence: float = 1.0):
    """Ek fact save/update karta hai. Same (category, key) pe update hoga."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO facts (category, key, value, source, confidence, mentions)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(category, key) DO UPDATE SET
            value = excluded.value,
            confidence = MAX(confidence, excluded.confidence),
            source = COALESCE(excluded.source, facts.source),
            mentions = mentions + 1,
            updated_at = CURRENT_TIMESTAMP
    """, (category, key, value, source, confidence))
    conn.commit()
    conn.close()


def get_facts(category: str = None, limit: int = 100) -> List[Dict]:
    """All facts ya category ke hisaab se."""
    conn = get_db()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT * FROM facts WHERE category = ? ORDER BY mentions DESC, updated_at DESC LIMIT ?", (category, limit))
    else:
        cur.execute("SELECT * FROM facts ORDER BY mentions DESC, updated_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_fact(category: str, key: str) -> Optional[Dict]:
    """Specific fact fetch karta hai."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM facts WHERE category = ? AND key = ?", (category, key))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_fact(fact_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    conn.commit()
    conn.close()


# ============================================================
# 🔍 EMBEDDINGS METADATA — RAG layer
# ============================================================
def save_embedding(content_type: str, content_text: str, content_id: int = None, source: str = None) -> int:
    """Embedding metadata save karta hai. Actual vectors embeddings.py mein hain."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO embeddings (content_type, content_id, content_text, source)
        VALUES (?, ?, ?, ?)
    """, (content_type, content_id, content_text, source))
    emb_id = cur.lastrowid
    conn.commit()
    conn.close()
    return emb_id


def get_recent_embeddings(content_type: str = None, limit: int = 50) -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    if content_type:
        cur.execute("SELECT * FROM embeddings WHERE content_type = ? ORDER BY created_at DESC LIMIT ?", (content_type, limit))
    else:
        cur.execute("SELECT * FROM embeddings ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# 📝 SESSION SUMMARIES — Cross-session continuity
# ============================================================
def save_session_summary(session_id: str, summary: str, key_topics: str = None, mood_summary: str = None, message_count: int = 0):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO session_summaries (session_id, summary, key_topics, mood_summary, message_count)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            summary = excluded.summary,
            key_topics = excluded.key_topics,
            mood_summary = excluded.mood_summary,
            message_count = excluded.message_count
    """, (session_id, summary, key_topics, mood_summary, message_count))
    conn.commit()
    conn.close()


def get_session_summary(session_id: str) -> Optional[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_summaries WHERE session_id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_session_summaries(limit: int = 10) -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_summaries ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# 🎯 LEARNED PATTERNS — Feedback-driven learning
# ============================================================
def record_pattern_outcome(pattern_type: str, pattern_value: str, success: bool):
    """Track karta hai ki ek pattern successful tha ya nahi."""
    conn = get_db()
    cur = conn.cursor()
    if success:
        cur.execute("""
            INSERT INTO learned_patterns (pattern_type, pattern_value, success_count)
            VALUES (?, ?, 1)
            ON CONFLICT(pattern_type, pattern_value) DO UPDATE SET
                success_count = success_count + 1,
                last_used = CURRENT_TIMESTAMP
        """, (pattern_type, pattern_value))
    else:
        cur.execute("""
            INSERT INTO learned_patterns (pattern_type, pattern_value, fail_count)
            VALUES (?, ?, 1)
            ON CONFLICT(pattern_type, pattern_value) DO UPDATE SET
                fail_count = fail_count + 1,
                last_used = CURRENT_TIMESTAMP
        """, (pattern_type, pattern_value))
    conn.commit()
    conn.close()


def get_pattern_score(pattern_type: str, pattern_value: str) -> float:
    """Pattern ka success rate. 0.5 = neutral, > 0.5 = good."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT success_count, fail_count FROM learned_patterns WHERE pattern_type = ? AND pattern_value = ?", (pattern_type, pattern_value))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0.5
    total = row["success_count"] + row["fail_count"]
    if total == 0:
        return 0.5
    return row["success_count"] / total


def get_top_patterns(pattern_type: str, limit: int = 10, min_score: float = 0.6) -> List[Dict]:
    """Best performing patterns."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT *, CAST(success_count AS REAL) / (success_count + fail_count + 0.001) as score
        FROM learned_patterns
        WHERE pattern_type = ?
        AND (success_count + fail_count) >= 3
        ORDER BY score DESC
        LIMIT ?
    """, (pattern_type, limit))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        total = d["success_count"] + d["fail_count"]
        if total > 0 and (d["success_count"] / total) >= min_score:
            result.append(d)
    return result


def get_stats_v2() -> Dict:
    """Enhanced stats for personal assistant."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM facts")
    facts_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM embeddings")
    emb_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM session_summaries")
    summaries_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM learned_patterns")
    patterns_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM messages WHERE role='user'")
    user_msgs = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM messages WHERE role='cherry'")
    cherry_msgs = cur.fetchone()["c"]
    conn.close()
    return {
        "facts_count": facts_count,
        "embeddings_count": emb_count,
        "session_summaries_count": summaries_count,
        "learned_patterns_count": patterns_count,
        "total_user_messages": user_msgs,
        "total_cherry_messages": cherry_msgs,
    }


if __name__ == "__main__":
    print("💾 Cherry Memory System v2 (Personal Assistant)")
    print("=" * 50)
    print(f"Database: {DB_PATH}")
    print(f"Stats v2: {get_stats_v2()}")
    print("✅ All tables initialized (facts, embeddings, summaries, patterns)")

