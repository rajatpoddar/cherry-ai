"use client";

import { useState, useEffect, useRef } from "react";
import { Send, Server, Activity } from "lucide-react";

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

export default function CherryChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentMood, setCurrentMood] = useState("playful");
  const [timeOfDay, setTimeOfDay] = useState("afternoon");
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [showServer, setShowServer] = useState(false);
  const [sessionId] = useState(`web-${Date.now()}`);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadGreeting();
    loadServerStatus();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function loadGreeting() {
    try {
      const r = await fetch("/api/greeting");
      const d = await r.json();
      setMessages([{ role: "cherry", content: d.greeting, mood: d.mood, time_of_day: d.time_of_day }]);
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
        <button
          onClick={() => setShowServer(!showServer)}
          className="p-2 rounded-full glass hover:bg-white/10 transition"
        >
          <Server className="w-5 h-5 text-cherry-pink" />
        </button>
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

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3" style={{ paddingBottom: "100px" }}>
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