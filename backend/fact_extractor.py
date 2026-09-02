"""
🔍 Fact Extractor — Cherry ka "yaad rakhne wala" system
Chat messages se automatically facts extract karke save karta hai.
"""
import re
from typing import List, Dict
from memory import save_fact, get_facts


# ============================================================
# 🎯 PATTERNS — Hindi/English dono mein detect karta hai
# ============================================================
PREFERENCE_PATTERNS = [
    (r"(?:mujhe|mere|my)\s+(.+?)\s+(?:pasand|like|love|pyaara|ach[ai])\s+(?:hai|hain|lagt[ai])", "preference", "like"),
    (r"(?:I|i)\s+(?:love|like|prefer)\s+(.+?)(?:\.|!|$|,)", "preference", "like"),
    (r"(?:mujhe|mere)\s+(.+?)\s+(?:pasand\s+nahi|nahi\s+pasand|hate|dislike|bura)\s+(?:hai|hain|lagt[ai])", "preference", "dislike"),
    (r"(?:I|i)\s+(?:hate|dislike|don'?t\s+like)\s+(.+?)(?:\.|!|$|,)", "preference", "dislike"),
]

PROJECT_PATTERNS = [
    (r"(?:main|me)\s+(.+?)\s+(?:bana|build|develop|kaam)\s+(?:raha|kar)\s*(?:hu|raha|rahi|hain|hun)", "project", "active"),
    (r"(?:working|building|developing)\s+on\s+(.+?)(?:\.|!|$|,)", "project", "active"),
    (r"(?:mera|my)\s+(.+?)\s+(?:repo|project|app|site|product)\s+(?:hai|hain)", "project", "owns"),
    (r"(\S+)\s+(?:container|service)\s+(?:pe|on|chal\s*raha|is\s+running)", "project", "service"),
]

PERSON_PATTERNS = [
    (r"(?:mera|my)\s+(?:friend|dost|bhai|bahen|wife|girlfriend|baby|partner)\s+(?:ka\s+naam|name)?\s*(?:hai|hain)?\s*(\w+)", "person", "relation"),
]

DATE_PATTERNS = [
    (r"(?:mera|my)\s+birthday\s+(?:hai|hain|is)\s+(.+?)(?:\.|!|$|,)", "personal", "birthday"),
    (r"(?:anniversary|engagement)\s+(?:hai|hain|is)\s+(.+?)(?:\.|!|$|,)", "personal", "anniversary"),
]

HABIT_PATTERNS = [
    (r"(?:main|me)\s+(?:roz|daily|har\s+din|hamesha)\s+(.+?)(?:\.|!|$|,)", "habit", "daily"),
]

LOCATION_PATTERNS = [
    (r"(?:main|me)\s+(.+?)\s+(?:mein|in)\s+(?:rehta|rehti|rahta|rahti|live|hu|hain)", "location", "lives"),
]

TECH_PATTERNS = [
    (r"(?:main|me)\s+(.+?)\s+(?:use\s+karta|use|using)\s*(?:hu|raha|rahi|hain)?", "tech", "uses"),
    (r"(?:using|i\s+use|main\s+use)\s+(.+?)(?:\.|!|$|,)", "tech", "uses"),
]


ALL_PATTERNS = (
    PREFERENCE_PATTERNS +
    PROJECT_PATTERNS +
    PERSON_PATTERNS +
    DATE_PATTERNS +
    HABIT_PATTERNS +
    LOCATION_PATTERNS +
    TECH_PATTERNS
)


SKIP_WORDS = {"hai", "hain", "hi", "bhi", "ye", "wo", "tha", "thi", "ka", "ki", "ke", "ko", "se", "me", "mein"}


def extract_facts(message: str, role: str = "user") -> List[Dict]:
    """Ek message se facts extract karta hai (no DB write)."""
    if role != "user":
        return []

    facts = []
    message_lower = message.lower().strip()

    for pattern, category, key_template in ALL_PATTERNS:
        matches = re.finditer(pattern, message_lower, re.IGNORECASE)
        for match in matches:
            groups = [g for g in match.groups() if g]
            if not groups:
                continue
            value = groups[0].strip()
            value = re.sub(r'\s+', ' ', value).strip('.,!?;:')

            if len(value) < 2 or len(value) > 200:
                continue
            if value.lower() in SKIP_WORDS:
                continue

            key = f"{key_template}:{value[:50]}"
            confidence = 0.85 if any(w in message_lower for w in ["mujhe", "mera", "my", "i "]) else 0.7

            facts.append({
                "category": category,
                "key": key,
                "value": value,
                "confidence": confidence,
                "raw": match.group(0)
            })

    return facts


def extract_and_save(message: str, role: str = "user", source: str = None) -> List[Dict]:
    """Extract + DB persist in one call."""
    facts = extract_facts(message, role)
    for f in facts:
        save_fact(
            category=f["category"],
            key=f["key"],
            value=f["value"],
            source=source or "chat",
            confidence=f["confidence"]
        )
    return facts


def build_facts_context(limit_per_category: int = 4) -> str:
    """System prompt ke liye compact facts context."""
    categories = ["preference", "project", "person", "personal", "habit", "location", "tech"]
    parts = []

    for cat in categories:
        facts = get_facts(category=cat, limit=limit_per_category)
        if facts:
            lines = [f"- {f['key'].split(':', 1)[-1]}: {f['value']}" for f in facts]
            parts.append(f"[{cat.upper()}]\n" + "\n".join(lines))

    return "\n\n".join(parts) if parts else ""


if __name__ == "__main__":
    test_messages = [
        "mujhe paan bahut pasand hai",
        "mera dorito-backend project chal raha hai",
        "mera dost Rahul hai",
        "main daily gym jaata hu",
        "I love building AI products",
        "mera birthday 15 August hai",
        "main react use karta hu",
    ]

    print("🔍 Fact Extractor Test")
    print("=" * 50)
    for msg in test_messages:
        facts = extract_facts(msg)
        print(f"\n📝 '{msg}'")
        print(f"   → {len(facts)} fact(s):")
        for f in facts:
            print(f"   - [{f['category']}] {f['key']} = {f['value']}")