"""Quick end-to-end test for personal assistant features."""
import sys
from brain import get_brain
from learning import record_feedback_with_learning, get_style_recommendations
from memory import get_facts, get_stats_v2
from session_manager import sync_from_agents, summarize_session

print("=" * 60)
print("CHERRY PERSONAL ASSISTANT - END TO END TEST")
print("=" * 60)

# 1. .agents sync
print("\n[1] .agents sync:")
result = sync_from_agents()
print(f"   {result}")

# 2. Brain init
brain = get_brain()
brain.start_session("test-pa-1")

# 3. Chat with auto fact extraction
print("\n[2] Chat: 'mujhe paan pasand hai aur main daily gym jaata hu'")
result = brain.think("mujhe paan pasand hai aur main daily gym jaata hu")
print(f"   Response: {result['response'][:100]}...")
print(f"   Mood: {result['mood']}")
print(f"   LLM: {result['llm_provider']}")
print(f"   Facts extracted this turn: {len(result.get('facts_extracted', []))}")
for f in result.get('facts_extracted', []):
    print(f"     - [{f['category']}] {f['value']}")

# 4. Second chat
print("\n[3] Chat: 'mera dost Rahul software engineer hai'")
result2 = brain.think("mera dost Rahul software engineer hai")
print(f"   Response: {result2['response'][:100]}...")
print(f"   Facts extracted: {len(result2.get('facts_extracted', []))}")

# 5. Feedback learning
print("\n[4] Feedback (thumbs up):")
fb = record_feedback_with_learning(
    message_id=result['message_id'],
    rating=1,
    user_message="mujhe paan pasand hai",
    cherry_response=result['response']
)
print(f"   Patterns recorded: {fb['patterns_recorded']}")

# 6. Stats
print("\n[5] Final stats:")
stats = get_stats_v2()
print(f"   {stats}")

# 7. All facts
print("\n[6] All stored facts:")
facts = get_facts(limit=10)
for f in facts[:7]:
    print(f"   [{f['category']}] {f['value'][:80]} (mentions={f['mentions']})")

# 8. Style recommendations
print("\n[7] Learned style recommendations:")
print(f"   {get_style_recommendations() or '(no patterns learned yet)'}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)