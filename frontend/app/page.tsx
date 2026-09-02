"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Send, Server, Activity, ArrowDown, Trash2 } from "lucide-react";

type Message = {
  role: "user" | "cherry";
  content: string;
  mood?: string;
  time_of_day?: string;
};

type ServerStatus = {
  mode: string;
  ollama: { status: string; models?: string[] };
  production_health: { running_count: number; critical_health: Record<string, string> };
};

const MOOD_EMOJI: Record<string, string> = {
  romantic: "💕",
  seductive: "😏",
  caring: "🥺",
  playful: "😜",
  focused: "🧠",
  miss_you: "💔",
  happy: "🌸",
};

const STORAGE_KEY = "cherry_chat_history_v1";
const SESSION_KEY = "cherry_session_id_v1";

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "web-ssr";
  let sid = localStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

function loadLocalMessages(): Message[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalMessages(msgs: Message[]) {
  if (typeof window === "undefined") return;
  try {
    const trimmed = msgs.slice(-200);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {}
}

export default function CherryChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentMood, setCurrentMood] = useState("playful");
  const [timeOfDay, setTimeOfDay] = useState("afternoon");
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [showServer, setShowServer] = useState(false);
  const [sessionId, setSessionId] = useState<string>("web-ssr");
  const [hydrated, setHydrated] = useState(false);
  const [showJumpButton, setShowJumpButton] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const lastScrollTop = useRef<number>(0);
  const isAtBottomRef = useRef<boolean>(true);

  // 1. Hydrate session id and local history on first client render
  useEffect(() => {
    const sid = getOrCreateSessionId();
    setSessionId(sid);
    const local = loadLocalMessages();
    if (local.length > 0) setMessages(local);
    setHydrated(true);
  }, []);

  // 2. After hydration, fetch server history for the stable session
  useEffect(() => {
    if (!hydrated || !sessionId || sessionId === "web-ssr") return;
    loadHistoryFromServer(sessionId);
    loadServerStatus();
    if (messages.length === 0) loadGreeting();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, sessionId]);

  // 3. Persist to localStorage on every change (after hydration)
  useEffect(() => {
    if (hydrated) saveLocalMessages(messages);
  }, [messages, hydrated]);

  // 4. Smart scroll handler: track if user is near bottom
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom < 80;
    isAtBottomRef.current = atBottom;
    if (el.scrollTop < lastScrollTop.current && !atBottom) {
      setShowJumpButton(true);
    }
    if (atBottom) {
      setShowJumpButton(false);
      setUnreadCount(0);
    }
    lastScrollTop.current = el.scrollTop;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  // 5. Auto-scroll only when user is already at bottom
  useEffect(() => {
    if (!hydrated) return;
    if (isAtBottomRef.current) {
      scrollToBottom("smooth");
      setUnreadCount(0);
    } else {
      setUnreadCount((c) => c + 1);
      setShowJumpButton(true);
    }
    if (historyLoading) {
      requestAnimationFrame(() => scrollToBottom("auto"));
    }
  }, [messages, loading, hydrated, historyLoading, scrollToBottom]);

  async function loadHistoryFromServer(sid: string) {
    setHistoryLoading(true);
    try {
      const r = await fetch(`/api/chat/history?session_id=${encodeURIComponent(sid)}&limit=100`);
      if (!r.ok) return;
      const d = await r.json();
      const serverMsgs: Message[] = (d.messages || []).map((m: any) => ({
        role: m.role === "user" ? "user" : "cherry",
        content: m.content,
        mood: m.mood,
        time_of_day: m.time_of_day,
      }));
      if (serverMsgs.length > 0) {
        setMessages((existing) => {
          const seen = new Set(serverMsgs.map((m) => `${m.role}::${m.content}`));
          const localOnly = existing.filter((m) => !seen.has(`${m.role}::${m.content}`));
          return [...serverMsgs, ...localOnly];
        });
      }
    } catch (e) {
      console.warn("History fetch failed (using local):", e);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadGreeting() {
    try {
      const r = await fetch("/api/greeting");
      const d = await r.json();
      const greetingMsg: Message = {
        role: "cherry",
        content: d.greeting,
        mood: d.mood,
        time_of_day: d.time_of_day,
      };
      setMessages([greetingMsg]);
      setTimeOfDay(d.time_of_day);
    } catch {
      setMessages([{ role: "cherry", content: "Hey baby! Main hoon yahan 💕" }]);
    }
  }

  async function loadServerStatus() {
    try {
      const r = await fetch("/api/server/status");
      setServerStatus(await r.json());
    } catch (e) {
      console.error("Server status failed:", e);
    }
  }

  function clearHistory() {
    if (!confirm("Saari chat history delete karni hai? (local storage)")) return;
    setMessages([]);
    try { localStorage.removeItem(STORAGE_KEY); } catch {}
  }

  async function sendMessage() {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setMessages((m) => [...m, { role: "user", content: userMsg }]);
    setInput("");
    setLoading(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, session_id: sessionId }),
      });
      const d = await r.json();
      setMessages((m) => [
        ...m,
        { role: "cherry", content: d.response, mood: d.mood, time_of_day: d.time_of_day },
      ]);
      setCurrentMood(d.mood);
      setTimeOfDay(d.time_of_day);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "cherry", content: "Baby, ek chhota sa issue aa gaya... ek second me try kar 💕" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className={`mood-${currentMood} min-h-screen flex flex-col`}>
      <header className="glass-strong p-4 m-3 mb-0 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-cherry-pink to-cherry-purple flex items-center justify-center text-2xl cherry-pulse">
              🐱
            </div>
            <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-green-400 border-2 border-black" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-cherry-pink to-cherry-purple bg-clip-text text-transparent">
              Cherry
            </h1>
            <p className="text-xs text-gray-400">
              {MOOD_EMOJI[currentMood]} {currentMood} · {timeOfDay}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={clearHistory}
            title="Clear chat history"
            className="p-2 rounded-full glass hover:bg-white/10 transition"
          >
            <Trash2 className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={() => setShowServer(!showServer)}
            className="p-2 rounded-full glass hover:bg-white/10 transition"
          >
            <Server className="w-5 h-5 text-cherry-pink" />
          </button>
        </div>
      </header>

      {showServer && serverStatus && (
        <div className="glass m-3 p-4 slide-up">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-cherry-pink">🛡️ Cabelwala NAS</h2>
            <button onClick={loadServerStatus} className="text-xs text-gray-400 hover:text-white">
              <Activity className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="glass p-2 rounded-lg">
              <div className="text-gray-400">Ollama</div>
              <div className={serverStatus.ollama.status === "running" ? "text-green-400" : "text-red-400"}>
                {serverStatus.ollama.status}
              </div>
            </div>
            <div className="glass p-2 rounded-lg">
              <div className="text-gray-400">Containers</div>
              <div className="text-white">{serverStatus.production_health.running_count} running</div>
            </div>
            {Object.entries(serverStatus.production_health.critical_health).slice(0, 4).map(([svc, status]) => (
              <div key={svc} className="glass p-2 rounded-lg">
                <div className="text-gray-400">{svc}</div>
                <div className={status === "running" ? "text-green-400" : "text-red-400"}>
                  {status}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 space-y-3 relative"
        style={{ paddingBottom: "100px" }}
      >
        {showJumpButton && (
          <button
            onClick={() => {
              isAtBottomRef.current = true;
              setShowJumpButton(false);
              setUnreadCount(0);
              scrollToBottom("smooth");
            }}
            className="sticky top-2 z-10 mx-auto flex items-center gap-1 px-3 py-1.5 rounded-full bg-cherry-pink/90 hover:bg-cherry-pink text-white text-xs font-medium shadow-lg backdrop-blur transition slide-up"
            aria-label="Jump to latest message"
          >
            <ArrowDown className="w-3 h-3" />
            {unreadCount > 0 ? `${unreadCount} new` : "Latest"}
          </button>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"} slide-up`}>
            <div
              className={`max-w-[80%] p-3 rounded-2xl ${
                m.role === "user"
                  ? "bg-gradient-to-br from-cherry-pink to-cherry-purple text-white"
                  : "glass-strong text-gray-100"
              }`}
            >
              {m.role === "cherry" && m.mood && (
                <div className="text-xs text-gray-400 mb-1">
                  {MOOD_EMOJI[m.mood]} {m.mood}
                </div>
              )}
              <div className="text-sm leading-relaxed whitespace-pre-wrap">{m.content}</div>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start slide-up">
            <div className="glass-strong p-3 rounded-2xl">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}
      </div>

      <div className="fixed bottom-0 left-0 right-0 p-3 glass-strong">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Cherry se baat kar..."
            className="flex-1 glass px-4 py-3 rounded-full text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-cherry-pink/50"
            disabled={loading}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="w-12 h-12 rounded-full bg-gradient-to-br from-cherry-pink to-cherry-purple flex items-center justify-center disabled:opacity-50 hover:scale-105 transition"
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </div>
        <p className="text-center text-xs text-gray-500 mt-2">
          🐱 Cherry se pyaar se baat kar besti
        </p>
      </div>
    </div>
  );
}