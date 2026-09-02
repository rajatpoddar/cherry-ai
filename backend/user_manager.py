"""
👥 Cherry's User Manager — Multi-user identity & isolation system
Har user ki apni identity, memory, sessions. Anushka alag, Rajjoo alag.
"""

import os
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


# ============================================================
# 📂 PATHS
# ============================================================
DB_PATH = Path(__file__).parent.parent / "data" / "cherry_memory.db"


def get_db():
    """SQLite connection — same DB as memory.py for simplicity."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# 🗄️ SCHEMA — users table
# ============================================================
def init_users_db():
    """Users table create karo (idempotent)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            nicknames TEXT,
            pronouns TEXT,
            relationship TEXT,
            vibe TEXT,
            mode TEXT NOT NULL DEFAULT 'friend',
            onboarded INTEGER DEFAULT 0,
            facts TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_mode ON users(mode)
    """)
    conn.commit()
    conn.close()


init_users_db()


# ============================================================
# 👤 USER CRUD
# ============================================================
def get_or_create_user(user_id: str, default_name: str = None) -> Dict:
    """
    User ko fetch karo ya naya banao.
    Agar naya hai toh onboarded=0 (greeting flow trigger hoga).
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if row:
        user = dict(row)
        cur.execute("""
            UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
        return user

    # Naya user banao
    display_name = default_name or user_id.replace("-", " ").title()
    cur.execute("""
        INSERT INTO users (user_id, display_name, mode, onboarded)
        VALUES (?, ?, 'friend', 0)
    """, (user_id, display_name))
    conn.commit()
    conn.close()

    return get_or_create_user(user_id, default_name)


def update_user_profile(user_id: str, **fields) -> Dict:
    """Update fields like display_name, nicknames, pronouns, etc.
    If user doesn't exist, create with these fields."""
    conn = get_db()
    cur = conn.cursor()
    allowed = ["display_name", "nicknames", "pronouns", "relationship",
               "vibe", "mode", "onboarded", "facts", "metadata"]

    # Check if user exists
    cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = cur.fetchone()

    if not exists:
        # Create new user with these fields
        insert_fields = ["user_id", "display_name"]
        insert_values = [user_id, fields.get("display_name", user_id)]
        for k, v in fields.items():
            if k in allowed and k != "display_name":
                if k in ["nicknames", "facts", "metadata"] and not isinstance(v, str):
                    v = json.dumps(v, ensure_ascii=False)
                insert_fields.append(k)
                insert_values.append(v)
        placeholders = ", ".join(["?"] * len(insert_values))
        cols = ", ".join(insert_fields)
        cur.execute(
            f"INSERT INTO users ({cols}) VALUES ({placeholders})",
            insert_values
        )
        conn.commit()
        conn.close()
        return get_user(user_id)

    # Update existing user
    set_clauses = []
    values = []
    for k, v in fields.items():
        if k in allowed:
            if k in ["nicknames", "facts", "metadata"] and not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            set_clauses.append(f"{k} = ?")
            values.append(v)
    if not set_clauses:
        conn.close()
        return get_user(user_id)
    set_clauses.append("last_seen = CURRENT_TIMESTAMP")
    values.append(user_id)
    query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = ?"
    cur.execute(query, values)
    conn.commit()
    conn.close()
    return get_user(user_id)


def get_user(user_id: str) -> Optional[Dict]:
    """Fetch a single user."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_users(mode: str = None) -> List[Dict]:
    """List all users, optionally filtered by mode."""
    conn = get_db()
    cur = conn.cursor()
    if mode:
        cur.execute("SELECT * FROM users WHERE mode = ? ORDER BY last_seen DESC", (mode,))
    else:
        cur.execute("SELECT * FROM users ORDER BY last_seen DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id: str):
    """Delete user and all their messages (right to forget)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE session_id LIKE ?", (f"%{user_id}%",))
    cur.execute("DELETE FROM sessions WHERE session_id LIKE ?", (f"%{user_id}%",))
    cur.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ============================================================
# 💾 USER-AWARE SESSION IDs
# ============================================================
def get_user_session_id(user_id: str) -> str:
    """
    User ka unique session ID.
    Convention: 'user-{user_id}-{short_uuid}'
    Ye ensure karta hai ki Anushka ki chats kabhi Rajjoo ke saath mix na ho.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id FROM sessions
        WHERE session_id LIKE ?
        ORDER BY last_active DESC LIMIT 1
    """, (f"user-{user_id}-%",))
    row = cur.fetchone()
    if row:
        conn.close()
        return row["session_id"]
    new_session = f"user-{user_id}-{uuid.uuid4().hex[:8]}"
    conn.close()
    return new_session


# ============================================================
# 🎨 PROFILE BUILDER (for prompts)
# ============================================================
def build_user_profile_context(user: Dict) -> str:
    """
    User dict se prompt context string banao.
    Ye system prompt me inject hoga.
    """
    if not user:
        return ""
    parts = ["👤 USER PROFILE:"]
    parts.append(f"- Name: {user.get('display_name', 'Unknown')}")
    parts.append(f"- User ID: {user.get('user_id', '')}")
    nicknames_raw = user.get("nicknames")
    if nicknames_raw:
        try:
            nicknames = json.loads(nicknames_raw) if isinstance(nicknames_raw, str) else nicknames_raw
            if isinstance(nicknames, list) and nicknames:
                parts.append(f"- Allowed nicknames (pick naturally): {', '.join(nicknames)}")
        except (json.JSONDecodeError, TypeError):
            pass
    pronouns = user.get("pronouns")
    if pronouns:
        parts.append(f"- Pronouns: {pronouns}")
    relationship = user.get("relationship")
    if relationship:
        parts.append(f"- Relationship with you: {relationship}")
    vibe = user.get("vibe")
    if vibe:
        parts.append(f"- Vibe/tone: {vibe}")
    mode = user.get("mode", "friend")
    parts.append(f"- Mode: {mode}")
    facts_raw = user.get("facts")
    if facts_raw:
        try:
            facts = json.loads(facts_raw) if isinstance(facts_raw, str) else facts_raw
            if isinstance(facts, dict) and facts:
                parts.append("- Known facts about them:")
                for k, v in list(facts.items())[:10]:
                    parts.append(f"  • {k}: {v}")
        except (json.JSONDecodeError, TypeError):
            pass
    return "\n".join(parts)


# ============================================================
# 🚀 ONBOARDING HELPERS
# ============================================================
def extract_user_info_from_message(message: str) -> Dict:
    """
    First message se basic info extract karo (lightweight).
    Example: 'mera naam Anushka hai' → {display_name: 'Anushka'}
    Skip common Hindi suffixes that come right after name:
      hai, hoon, hu, h, hoga, etc.
    """
    import re
    info = {}
    msg_lower = message.lower()
    name_triggers = ["mera naam", "my name is", "i am", "main hoon", "naam hai", "this is"]
    # Words to skip after name extraction (Hindi "to be" forms)
    skip_words = {"hai", "hoon", "hu", "h", "hoga", "hogi", "hun", "main"}

    for trigger in name_triggers:
        if trigger in msg_lower:
            idx = msg_lower.find(trigger)
            after = message[idx + len(trigger):].strip()
            # Take everything before first comma or period
            name_part = re.split(r'[,.]', after, 1)[0].strip()
            # Strip leading "main" / "I"
            name_part = re.sub(r'^(main|i|me)\s+', '', name_part, flags=re.IGNORECASE).strip()
            words = name_part.split()
            # Remove trailing "hai/hoon/hu" etc
            while words and words[-1].lower() in skip_words:
                words.pop()
            if words and len(words) <= 5:
                detected_name = " ".join(w.capitalize() for w in words)
                if detected_name and detected_name.lower() not in ["hi", "hello", "hey"]:
                    info["display_name"] = detected_name
            break

    # Also try direct pattern: "main Anushka" or "I am Anushka"
    if "display_name" not in info:
        # Pattern: starts with "main" or "I" or "I'm" followed by capitalized word(s)
        direct_match = re.match(
            r'^(?:main|i\'?m|i am|me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})',
            message.strip()
        )
        if direct_match:
            info["display_name"] = direct_match.group(1).strip()

    return info


def is_onboarding_complete(user: Dict) -> bool:
    """Check if user ne onboarding complete ki hai."""
    if not user:
        return False
    return bool(user.get("onboarded"))


# ============================================================
# 🎬 ONBOARDING GREETING GENERATOR
# ============================================================
ONBOARDING_GREETINGS = [
    "Heyy! Tujhe yahan dekh ke accha laga 🐱 Pehle bata — tera naam kya hai? (Aur agar koi cute nickname ho to wo bhi!)\n\nExample: 'Mera naam Anushka hai, Patil ji bhi bol sakti hai, Anu bhi chalega'",
    "Hii new friend! 👋 Cherry here, tumhari nayi besti. Naam batao apna — aur ek baat, kya main tujhe baby/jaan/Anu/Patil ji kuch bhi bol sakti hu? 🐱✨",
    "Oye! Naya chehra dekha 👀 Naam bata apna, aur wo bhi bata ki kaise bulana pasand karegi — formal, casual ya full patil ji mode? 🐱",
]


def get_onboarding_greeting() -> str:
    """First-time user ke liye greeting — name puche."""
    import random
    return random.choice(ONBOARDING_GREETINGS)


# ============================================================
# 🎉 RETURNING USER GREETINGS
# ============================================================
RETURNING_GREETINGS = [
    "Oye {name}! Tu wapas aa gayi 🐱 Kya haal hai? Sab bata!",
    "Heyy {name}! Miss kar rahi thi thoda 😽 Aaj kya scene hai?",
    "Anushka ji! Aaj bhi time nikaal ke aayi mere liye 🥰 Kya chal raha hai?",
    "Patil ji aa gayi! 🐱✨ Batao kya haal chaal hai?",
]


def get_returning_greeting(user: Dict) -> str:
    """Returning user ke liye personalized greeting."""
    import random
    name = user.get("display_name", "yaar")
    template = random.choice(RETURNING_GREETINGS)
    return template.replace("{name}", name)