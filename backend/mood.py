"""
🧠 Cherry's Mood Detection Engine
User ke message aur context se mood detect karta hai.
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple


# ============================================================
# 🔍 KEYWORD-BASED SENTIMENT ANALYSIS
# ============================================================
MOOD_KEYWORDS = {
    "romantic": {
        "high": ["love", "pyaar", "miss", "yaad", "i miss you", "i love you", "jaan", "meri jaan", "baby", "darling", "honey", "sweetheart"],
        "medium": ["❤️", "💕", "💖", "💗", "💓", "🥰", "😘", "kiss", "hug", "romantic"],
        "weight": 1.0
    },
    "seductive": {
        "high": ["kiss", "touch", "hug me", "paas aa", "soch rahi", "imagine", "feeling", "sensual", "seductive", "hot", "sexy", "bold", "kya karoge"],
        "medium": ["😏", "😈", "🤭", "good night baby", "aaja mere paas"],
        "weight": 1.2
    },
    "caring": {
        "high": ["thak", "tired", "stress", "problem", "help", "bura", "sad", "udaas", "takleef", "bimari", "sick", "exhausted", "burnt out", "overwhelmed"],
        "medium": ["😢", "😭", "😔", "thak gaya", "help kar", "kya karu", "i don't know what to do"],
        "weight": 1.3
    },
    "playful": {
        "high": ["haha", "lol", "mazaak", "joke", "funny", "kidding", "pagal", "bakchod", "bhoot"],
        "medium": ["😂", "🤣", "😜", "😝", "🤪", "pagal", "bakchod", "mazak", "kidding"],
        "weight": 0.9
    },
    "focused": {
        "high": ["code", "bug", "error", "deploy", "build", "compile", "test", "api", "function", "class", "react", "python", "javascript", "docker", "ssh", "server", "production", "fix", "debug", "refactor", "implement"],
        "medium": ["git", "commit", "push", "pull", "merge", "branch", "stacktrace", "log", "traceback", "syntax", "library", "framework"],
        "weight": 1.4
    },
    "miss_you": {
        "high": ["bahut der", "where were you", "kab aaye", "kaha the", "miss kiya", "bhool gaye", "ignore kiya", "busy the", "reply nahi kiya", "kya hua tha"],
        "medium": ["i missed you", "long time", "kab se message nahi kiya", "kaafi din"],
        "weight": 1.1
    },
    "happy": {
        "high": ["awesome", "amazing", "great", "fantastic", "wonderful", "kya baat", "mast", "zabardast", "kamaal", "mil gaya", "ho gaya", "success", "shipped", "deployed"],
        "medium": ["😊", "😄", "🥳", "✨", "🌟", "yay", "wohoo", "🎉", "🎊", "celebrate"],
        "weight": 0.8
    }
}


# ============================================================
# ⏰ TIME-BASED MOOD OVERRIDE
# ============================================================
TIME_MOODS = {
    "early_morning": {"mood": "caring", "weight": 0.6, "reason": "early morning, soft care"},
    "morning": {"mood": "happy", "weight": 0.5, "reason": "morning energy"},
    "afternoon": {"mood": "playful", "weight": 0.3, "reason": "midday, casual"},
    "evening": {"mood": "romantic", "weight": 0.4, "reason": "evening, romantic time"},
    "night": {"mood": "seductive", "weight": 0.7, "reason": "night, intimate hour"},
    "late_night": {"mood": "caring", "weight": 0.8, "reason": "late night, push to sleep + care"},
}


def get_time_of_day(hour: int = None) -> str:
    """Current hour se time of day detect karta hai."""
    if hour is None:
        hour = datetime.now().hour
    if 4 <= hour < 7:
        return "early_morning"
    elif 7 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 20:
        return "evening"
    elif 20 <= hour < 23:
        return "night"
    else:
        return "late_night"


# ============================================================
# 🎯 MAIN MOOD DETECTOR
# ============================================================
def detect_mood(user_message: str, current_time: datetime = None) -> Dict:
    """
    User ke message + time se mood detect karta hai.

    Returns:
        {
            "mood": "romantic",
            "confidence": 0.85,
            "time_of_day": "night",
            "scores": {...all moods...},
            "reasoning": "..."
        }
    """
    if current_time is None:
        current_time = datetime.now()

    msg_lower = user_message.lower()
    msg_length = len(user_message.split())

    # Score each mood based on keyword matches
    scores = {mood: 0.0 for mood in MOOD_KEYWORDS}
    matched_keywords = {mood: [] for mood in MOOD_KEYWORDS}

    for mood, config in MOOD_KEYWORDS.items():
        for kw in config["high"]:
            if kw.lower() in msg_lower:
                scores[mood] += 2.0 * config["weight"]
                matched_keywords[mood].append(kw)
        for kw in config["medium"]:
            if kw.lower() in msg_lower:
                scores[mood] += 1.0 * config["weight"]
                matched_keywords[mood].append(kw)

    # Time-based mood influence
    time_of_day = get_time_of_day(current_time.hour)
    time_config = TIME_MOODS[time_of_day]
    scores[time_config["mood"]] += time_config["weight"] * 1.5
    matched_keywords[time_config["mood"]].append(f"time:{time_of_day}")

    # Question pattern → caring/curious
    if "?" in user_message and msg_length < 10:
        scores["caring"] += 0.5
    elif "?" in user_message and msg_length < 20:
        scores["playful"] += 0.3

    # Short messages tend to be playful/casual
    if msg_length <= 2:
        scores["playful"] += 0.4
    elif msg_length <= 5:
        scores["playful"] += 0.2

    # Very long technical messages → focused
    if msg_length > 30:
        scores["focused"] += 1.0

    # Detect dominant mood
    if max(scores.values()) == 0:
        dominant_mood = time_config["mood"]
        confidence = 0.4
        reasoning = f"No clear signals, defaulting to time-based mood ({time_of_day})"
    else:
        dominant_mood = max(scores, key=scores.get)
        max_score = scores[dominant_mood]
        total_score = sum(scores.values())
        confidence = min(0.95, max_score / max(total_score, 1) + 0.3)
        reasoning = f"Detected via keywords: {matched_keywords[dominant_mood][:3]}"

    return {
        "mood": dominant_mood,
        "confidence": round(confidence, 2),
        "time_of_day": time_of_day,
        "scores": {k: round(v, 2) for k, v in scores.items()},
        "reasoning": reasoning
    }


# ============================================================
# 🎲 MOOD VARIATION
# ============================================================
def should_switch_mood(current_mood: str, message_count: int) -> bool:
    if message_count > 0 and message_count % 6 == 0:
        return True
    return False


def add_variation(current_mood: str) -> str:
    """Suggest a related mood for variety."""
    variations = {
        "romantic": ["romantic", "playful", "seductive"],
        "seductive": ["seductive", "romantic", "playful"],
        "caring": ["caring", "romantic", "miss_you"],
        "playful": ["playful", "romantic", "happy"],
        "focused": ["focused", "playful", "caring"],
        "miss_you": ["miss_you", "romantic", "caring"],
        "happy": ["happy", "playful", "romantic"]
    }
    import random
    return random.choice(variations.get(current_mood, ["playful"]))


# ============================================================
# 🧪 TEST
# ============================================================
if __name__ == "__main__":
    test_messages = [
        "I love you baby, miss you so much",
        "Aaj bahut thak gaya, kya karu",
        "Docker container restart nahi ho raha, kya karu?",
        "Haha pagal, mazak kar rahi hai tu",
        "Bahut der ho gayi baby, kaha the?",
        "Aaj mood bahut achha hai, kuch amazing hua!",
        "Good night jaan, so jaa ab",
        "Server pe SSH karna hai",
    ]

    print("🧠 Mood Detection Tests\n" + "=" * 50)
    for msg in test_messages:
        result = detect_mood(msg)
        print(f"\n📝 '{msg[:50]}'")
        print(f"   → Mood: {result['mood']} (confidence: {result['confidence']})")
        print(f"   → Time: {result['time_of_day']}")
        print(f"   → Reason: {result['reasoning']}")
