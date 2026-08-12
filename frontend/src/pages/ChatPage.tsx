import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { assistant } from "../api";

type Msg = {
  role: string;
  content: string;
  sources?: { text: string; score: number; source: string }[];
  suggestion?: { agent_type: string; goal: string };
};

const AGENT_TYPE_LABEL: Record<string, string> = {
  cost_saving: "Cost Saving",
  forecast: "Forecast",
  contract_risk: "Contract Risk",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: "Hello! Ask me anything about your company spend." }]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      // A single entry point that classifies intent server-side: a spend
      // question is answered here directly, a cost-saving/forecast/risk
      // goal comes back as a suggestion this page hands off to the
      // dedicated Cost Saving Agent page instead of duplicating its
      // (multi-step, SSE-driven) UI inline in the chat thread.
      const res = await assistant.send(q, sessionId);
      if (res.intent === "cost_saving" && res.suggestion) {
        setMessages((m) => [...m, { role: "assistant", content: "", suggestion: res.suggestion }]);
      } else if (res.chat) {
        setSessionId(res.chat.session_id);
        setMessages((m) => [...m, { role: "assistant", content: res.chat.reply, sources: res.chat.sources }]);
      }
    } catch (err: any) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${err.message}` }]);
    }
    setLoading(false);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-3xl">
      <h1 className="text-xl font-bold mb-4">AI Chat</h1>
      <div className="flex-1 overflow-auto rounded border border-border bg-panel p-4 flex flex-col gap-3 mb-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
            {m.suggestion ? (
              <div className="max-w-[80%] rounded border border-teal/40 bg-teal/10 px-3 py-2 text-sm text-parchment">
                <p>
                  Questo sembra un obiettivo per il{" "}
                  <span className="font-semibold">{AGENT_TYPE_LABEL[m.suggestion.agent_type] ?? m.suggestion.agent_type}</span> Agent,
                  non una domanda sui dati. Vuoi eseguirlo?
                </p>
                <button
                  type="button"
                  onClick={() => navigate("/cost-saving", { state: { agentType: m.suggestion!.agent_type, goal: m.suggestion!.goal } })}
                  className="mt-2 rounded bg-teal px-3 py-1 text-xs font-semibold text-surface"
                >
                  Apri nel Cost Saving Agent
                </button>
              </div>
            ) : (
              <div className={`max-w-[80%] rounded px-3 py-2 text-sm ${m.role === "user" ? "bg-teal/20 text-parchment" : "bg-panel-2 text-parchment"}`}>
                <p>{m.content}</p>
              </div>
            )}
            {m.sources && m.sources.length > 0 && (
              <div className="mt-1 flex flex-col gap-0.5 text-xs text-muted">
                {m.sources.slice(0, 3).map((s, j) => (
                  <span key={j}>📄 {s.source} (score {s.score})</span>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handle} className="flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question about your documents..." disabled={loading}
          className="flex-1 rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        <button type="submit" disabled={loading} className="rounded bg-teal px-4 py-2 text-xs font-semibold text-surface disabled:opacity-50">
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
