"""
Learning module — Cherry ka self-improvement layer.
Feedback + patterns se seekhti hai ki kya kaam karta hai aur kya nahi.
"""
from typing import Dict, List, Optional
from memory import (
    save_feedback, get_top_patterns, get_pattern_score,
    record_pattern_outcome, get_stats_v2, get_chat_history
)


# ============================================================
# FEEDBACK → PATTERNS
# ============================================================
def record_feedback_with_learning(message_id: int, rating: int, user_message: str = None, cherry_response: str = None):
    """
    Feedback record karta hai + response ko patterns mein todta hai.

    rating: 1 = thumbs up (success), -1 = thumbs down (failure)
    """
    # Save feedback
    save_feedback(message_id, rating)

    if not cherry_response:
        return {"patterns_recorded": 0}

    success = rating > 0
    patterns_recorded = []

    # Pattern 1: Response length bucket
    resp_len = len(cherry_response)
    if resp_len < 80:
        length_bucket = "short"
    elif resp_len < 200:
        length_bucket = "medium"
    else:
        length_bucket = "long"
    record_pattern_outcome("response_length", length_bucket, success)
    patterns_recorded.append(f"length:{length_bucket}")

    # Pattern 2: Cat-like features (meow, purr, etc.)
    cat_words = ["meow", "purrr", "rrrr", "🐱", "😽", "besti", "gale"]
    if any(w in cherry_response.lower() for w in cat_words):
        record_pattern_outcome("style", "cat_personality", success)
        patterns_recorded.append("style:cat_personality")

    # Pattern 3: Ends with question
    if cherry_response.strip().endswith("?"):
        record_pattern_outcome("style", "ends_with_question", success)
        patterns_recorded.append("style:ends_with_question")

    # Pattern 4: Has emoji
    if any(ord(c) > 127 for c in cherry_response):
        record_pattern_outcome("style", "has_emoji", success)
        patterns_recorded.append("style:has_emoji")

    # Pattern 5: English-only
    english_words = sum(1 for w in cherry_response.split() if w.isascii() and w.isalpha())
    total_words = len(cherry_response.split())
    if total_words > 0 and english_words / total_words > 0.8:
        record_pattern_outcome("language", "mostly_english", success)
        patterns_recorded.append("language:mostly_english")
    elif total_words > 0:
        record_pattern_outcome("language", "hinglish", success)
        patterns_recorded.append("language:hinglish")

    # Pattern 6: Mood-specific patterns (passed via user_message mood)
    if user_message:
        msg_lower = user_message.lower()
        if any(w in msg_lower for w in ["love", "pyaar", "jaan", "baby", "besti"]):
            record_pattern_outcome("user_intent", "romantic_input", success)
            patterns_recorded.append("user_intent:romantic_input")
        if any(w in msg_lower for w in ["docker", "server", "code", "bug", "error"]):
            record_pattern_outcome("user_intent", "technical_input", success)
            patterns_recorded.append("user_intent:technical_input")

    return {
        "patterns_recorded": len(patterns_recorded),
        "patterns": patterns_recorded,
        "feedback_saved": True
    }


# ============================================================
# RECOMMENDATIONS — System prompt ke liye
# ============================================================
def get_style_recommendations() -> str:
    """Cherry ko best practices bataati hai based on feedback history."""
    parts = []

    # Best length
    top_lengths = get_top_patterns("response_length", limit=3, min_score=0.5)
    if top_lengths:
        best = top_lengths[0]
        parts.append(f"Preferred response length: {best['pattern_value']} (score={best['score']:.2f})")

    # Best style
    top_styles = get_top_patterns("style", limit=5, min_score=0.55)
    if top_styles:
        good_styles = [s["pattern_value"] for s in top_styles[:3]]
        parts.append(f"User loves styles: {', '.join(good_styles)}")

    # Best language
    top_langs = get_top_patterns("language", limit=2, min_score=0.5)
    if top_langs:
        best_lang = top_langs[0]
        parts.append(f"Preferred language: {best_lang['pattern_value']} (score={best_lang['score']:.2f})")

    return "\n".join(parts) if parts else ""


def get_user_intent_recommendation(user_message: str) -> str:
    """User message ke basis pe recommendation."""
    msg_lower = user_message.lower()
    if any(w in msg_lower for w in ["docker", "server", "code", "bug", "deploy", "error"]):
        top = get_top_patterns("user_intent", limit=10)
        for p in top:
            if p["pattern_value"] == "technical_input":
                return f"User often asks technical stuff. Technical responses got score={p['score']:.2f}"
    return ""


def get_learning_stats() -> Dict:
    """Learning system ka overall stats."""
    stats = get_stats_v2()
    stats["top_patterns"] = {
        "length": len(get_top_patterns("response_length", min_score=0.5)),
        "style": len(get_top_patterns("style", min_score=0.5)),
        "language": len(get_top_patterns("language", min_score=0.5)),
        "user_intent": len(get_top_patterns("user_intent", min_score=0.5)),
    }
    return stats


if __name__ == "__main__":
    print("Learning Module Test")
    print("=" * 50)

    # Simulate feedback
    result = record_feedback_with_learning(
        message_id=1,
        rating=1,
        user_message="I love you baby",
        cherry_response="Meow baby, pyaar karti hoon 🐱 Tu kya kar raha hai?"
    )
    print(f"\nPositive feedback recorded: {result}")

    result2 = record_feedback_with_learning(
        message_id=2,
        rating=-1,
        user_message="Docker container restart karo",
        cherry_response="OK."
    )
    print(f"\nNegative feedback recorded: {result2}")

    print(f"\nStyle recommendations:\n{get_style_recommendations()}")
    print(f"\nLearning stats:\n{get_learning_stats()}")