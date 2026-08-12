import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { assistant } from "../api";
import { getErrorMessage } from "../lib/errorMessage";
import AgentStepTimeline, { type AgentStep } from "../components/AgentStepTimeline";
import Markdown from "../components/Markdown";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Msg = {
  role: string;
  content: string;
  sources?: { text: string; score: number; source: string; document_id?: number | null }[];
  suggestion?: { agent_type: string; goal: string };
};

export default function ChatPage() {
  const { t } = useTranslation("chat");
  useDocumentTitle(t("title"));
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: t("greeting") }]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, liveSteps]);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    setLiveSteps([]);
    // Accumulated outside React state so the SSE loop's local view of "every
    // step gathered so far" doesn't depend on a stale closure over
    // liveSteps - same pattern as CostSavingAgentPage.tsx::handleAnalyze.
    const collectedSteps: AgentStep[] = [];
    try {
      for await (const evt of assistant.sendStream(q, sessionId)) {
        if (evt.event === "step") {
          collectedSteps.push(evt.data);
          setLiveSteps([...collectedSteps]);
        } else if (evt.event === "suggestion") {
          setMessages((m) => [...m, { role: "assistant", content: "", suggestion: evt.data }]);
        } else if (evt.event === "done") {
          setSessionId(evt.data.session_id);
          setMessages((m) => [...m, { role: "assistant", content: evt.data.reply, sources: evt.data.sources }]);
        }
      }
    } catch (err: any) {
      setMessages((m) => [...m, { role: "assistant", content: t("error", { message: getErrorMessage(err, t) }) }]);
    }
    setLiveSteps([]);
    setLoading(false);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-3xl">
      <h1 className="text-xl font-bold mb-4">{t("title")}</h1>
      <div className="flex-1 overflow-auto rounded border border-border bg-panel p-4 flex flex-col gap-3 mb-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
            {m.suggestion ? (
              <div className="max-w-[80%] rounded border border-teal/40 bg-teal/10 px-3 py-2 text-sm text-parchment">
                <p>
                  <Trans
                    t={t}
                    i18nKey="handoff.message"
                    values={{ agent: t(`agentTypeLabel.${m.suggestion.agent_type}`, { defaultValue: m.suggestion.agent_type }) }}
                    components={{ b: <span className="font-semibold" /> }}
                  />
                </p>
                <button
                  type="button"
                  onClick={() => navigate("/cost-saving", { state: { agentType: m.suggestion!.agent_type, goal: m.suggestion!.goal } })}
                  className="mt-2 rounded bg-teal px-3 py-1 text-xs font-semibold text-surface"
                >
                  {t("handoff.openButton")}
                </button>
              </div>
            ) : (
              <div className={`max-w-[80%] rounded px-3 py-2 text-sm ${m.role === "user" ? "bg-teal/20 text-parchment" : "bg-panel-2 text-parchment"}`}>
                {m.role === "assistant" ? <Markdown>{m.content}</Markdown> : <p>{m.content}</p>}
              </div>
            )}
            {m.sources && m.sources.length > 0 && (
              <div className="mt-1 flex flex-col gap-0.5 text-xs text-muted">
                {m.sources.slice(0, 3).map((s, j) =>
                  s.document_id != null ? (
                    <button
                      key={j}
                      onClick={() => navigate(`/documents/${s.document_id}`)}
                      className="w-fit text-left hover:text-teal hover:underline"
                    >
                      📄 {s.source} (score {s.score})
                    </button>
                  ) : (
                    <span key={j}>📄 {s.source} (score {s.score})</span>
                  )
                )}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex flex-col items-start">
            <div className="max-w-[80%] w-full rounded px-3 py-2 text-sm bg-panel-2 text-parchment">
              {liveSteps.length > 0 ? (
                <AgentStepTimeline steps={liveSteps} animate={false} />
              ) : (
                <span className="italic text-muted">{t("thinking")}</span>
              )}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handle} className="flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("placeholder")} disabled={loading}
          aria-label={t("placeholder")}
          className="flex-1 rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        <button type="submit" disabled={loading} className="rounded bg-teal px-4 py-2 text-xs font-semibold text-surface disabled:opacity-50">
          {loading ? "..." : t("send")}
        </button>
      </form>
    </div>
  );
}
