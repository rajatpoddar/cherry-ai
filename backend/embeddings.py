"""
Embeddings + RAG layer.
Uses Ollama nomic-embed-text for vector generation, simple JSON store for now.
"""
import os
import json
import math
import requests
from pathlib import Path
from typing import List, Dict, Optional
from memory import save_embedding, get_facts


VECTORS_PATH = Path(__file__).parent.parent / "data" / "vectors.json"
VECTORS_PATH.parent.mkdir(parents=True, exist_ok=True)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = os.getenv("CHERRY_EMBED_MODEL", "nomic-embed-text")


def generate_embedding(text: str, model: str = None) -> Optional[List[float]]:
    """Generate embedding vector via Ollama."""
    use_model = model or EMBED_MODEL
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": use_model, "prompt": text},
            timeout=30
        )
        r.raise_for_status()
        return r.json().get("embedding")
    except Exception:
        return None


def _load_vectors() -> Dict:
    if not VECTORS_PATH.exists():
        return {}
    try:
        return json.loads(VECTORS_PATH.read_text())
    except Exception:
        return {}


def _save_vectors(data: Dict):
    VECTORS_PATH.write_text(json.dumps(data))


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def store(content_type: str, content_text: str, content_id: int = None, source: str = None) -> Optional[int]:
    """Embed content and store vector + metadata."""
    if not content_text or len(content_text.strip()) < 3:
        return None
    text = content_text[:500]
    vector = generate_embedding(text)
    if not vector:
        return None
    emb_id = save_embedding(content_type, text, content_id, source)
    vectors = _load_vectors()
    vectors[str(emb_id)] = {
        "vector": vector,
        "type": content_type,
        "text": text,
        "source": source
    }
    _save_vectors(vectors)
    return emb_id


def search(query: str, top_k: int = 5, content_type: str = None, min_score: float = 0.5) -> List[Dict]:
    """Semantic search over stored memories."""
    query_vec = generate_embedding(query)
    if not query_vec:
        return []
    vectors = _load_vectors()
    scored = []
    for emb_id, data in vectors.items():
        if content_type and data.get("type") != content_type:
            continue
        score = _cosine_sim(query_vec, data["vector"])
        if score >= min_score:
            scored.append({
                "id": emb_id,
                "score": score,
                "type": data.get("type"),
                "text": data.get("text"),
                "source": data.get("source")
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def build_rag_context(query: str, top_k: int = 3, max_chars: int = 800) -> str:
    """Build RAG context string for system prompt."""
    results = search(query, top_k=top_k)
    if not results:
        return ""
    lines = ["[RELEVANT MEMORIES]"]
    chars_used = 0
    for r in results:
        text = r["text"][:200]
        line = f"- ({r['type']}, score={r['score']:.2f}) {text}"
        if chars_used + len(line) > max_chars:
            break
        lines.append(line)
        chars_used += len(line)
    return "\n".join(lines) if len(lines) > 1 else ""


def index_recent_chats(session_id: str = None, limit: int = 20) -> int:
    """Embed recent chat messages into RAG store."""
    from memory import get_chat_history
    history = get_chat_history(session_id, limit) if session_id else []
    indexed = 0
    for msg in history:
        if msg.get("role") == "user" and msg.get("id"):
            text = msg.get("content", "")
            if text:
                store("chat", text, msg["id"], session_id)
                indexed += 1
    return indexed


def index_all_facts() -> int:
    """Embed all facts into RAG store."""
    facts = get_facts(limit=200)
    indexed = 0
    for f in facts:
        text = f"{f['category']}: {f['key']} = {f['value']}"
        store("fact", text, f["id"], "facts")
        indexed += 1
    return indexed


def vector_count() -> int:
    """Total stored vectors count."""
    return len(_load_vectors())


if __name__ == "__main__":
    print("Embeddings + RAG Test")
    print("=" * 50)
    print(f"Ollama: {OLLAMA_HOST}")
    print(f"Model: {EMBED_MODEL}")
    test = generate_embedding("Hello baby, kya kar rahi hai?")
    print(f"\nGenerated embedding: {len(test) if test else 0} dimensions")
    if test:
        store("test", "Rajjoo loves paan and gaming", 1, "test")
        store("test", "Cherry is Rajjoo's AI girlfriend", 2, "test")
        store("test", "Docker containers run on NAS", 3, "test")
        results = search("food preferences", top_k=3)
        print(f"\nSearch 'food preferences':")
        for r in results:
            print(f"  - [{r['score']:.3f}] {r['text']}")