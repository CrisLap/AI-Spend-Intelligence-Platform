import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { Bot, Check, Copy, Plus, RotateCcw, Trash2, User as UserIcon } from "lucide-react";
import { assistant, chat } from "../api";
import { getErrorMessage } from "../lib/errorMessage";
import AgentStepTimeline, { type AgentStep } from "../components/AgentStepTimeline";
import Markdown from "../components/Markdown";
import Card from "../components/Card";
import ConfirmDialog from "../components/ConfirmDialog";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Msg = {
  role: string;
  content: string;
  sources?: { text: string; score: number; source: string; document_id?: number | null }[];
  suggestion?: { agent_type: string; goal: string };
};

type SessionSummary = { id: number; preview: string | null; summary: string | null; created_at: string; updated_at: string };

function groupLabel(iso: string, t: (key: string, opts?: any) => string): string {
  const date = new Date(iso);
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86400000);
  if (diffDays <= 0) return t("history.today");
  if (diffDays === 1) return t("history.yesterday");
  return t("history.daysAgo", { count: diffDays });
}

export default function ChatPage() {
  const { t } = useTranslation("chat");
  useDocumentTitle(t("title"));
  const greeting: Msg = { role: "assistant", content: t("greeting") };
  const [messages, setMessages] = useState<Msg[]>([greeting]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [sessionPendingDelete, setSessionPendingDelete] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, liveSteps]);

  const loadSessions = useCallback(() => {
    chat.listSessions().then(setSessions).catch(() => {});
  }, []);
  useEffect(loadSessions, [loadSessions]);

  async function sendMessage(q: string) {
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
          loadSessions();
        }
      }
    } catch (err: any) {
      setMessages((m) => [...m, { role: "assistant", content: t("error", { message: getErrorMessage(err, t) }) }]);
    }
    setLiveSteps([]);
    setLoading(false);
  }

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const q = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    await sendMessage(q);
  }

  function handleRegenerate() {
    if (loading) return;
    const lastUserIndex = [...messages].map((m) => m.role).lastIndexOf("user");
    if (lastUserIndex === -1) return;
    const q = messages[lastUserIndex].content;
    setMessages((m) => m.slice(0, lastUserIndex + 1));
    sendMessage(q);
  }

  function handleCopy(index: number, content: string) {
    navigator.clipboard.writeText(content).then(() => {
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex((i) => (i === index ? null : i)), 1500);
    });
  }

  function handleNewChat() {
    setSessionId(undefined);
    setMessages([greeting]);
  }

  async function handleSelectSession(id: number) {
    if (loading || id === sessionId) return;
    try {
      const msgs = await chat.getMessages(id);
      setMessages(
        msgs.map((m: any) => ({
          role: m.role,
          content: m.content,
          sources: m.sources_json ? JSON.parse(m.sources_json) : undefined,
        }))
      );
      setSessionId(id);
    } catch {
      // leave current conversation untouched if the fetch fails
    }
  }

  async function confirmDeleteSession() {
    if (sessionPendingDelete == null) return;
    const id = sessionPendingDelete;
    setSessionPendingDelete(null);
    try {
      await chat.deleteSession(id);
      setSessions((s) => s.filter((sess) => sess.id !== id));
      if (id === sessionId) handleNewChat();
    } catch {
      // session list stays as-is; user can retry
    }
  }

  const groupedSessions: { label: string; items: SessionSummary[] }[] = [];
  for (const s of sessions) {
    const label = groupLabel(s.updated_at, t);
    const lastGroup = groupedSessions[groupedSessions.length - 1];
    if (lastGroup && lastGroup.label === label) lastGroup.items.push(s);
    else groupedSessions.push({ label, items: [s] });
  }

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-8rem)]">
      <Card className="flex flex-col flex-1 min-w-0">
        <h1 className="text-page-title font-bold mb-4">{t("title")}</h1>
        <div className="flex-1 overflow-auto flex flex-col gap-3 mb-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-2 ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
              <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${m.role === "user" ? "bg-teal/20 text-teal" : "bg-panel-2 text-teal"}`}>
                {m.role === "user" ? <UserIcon size={14} aria-hidden="true" /> : <Bot size={14} aria-hidden="true" />}
              </div>
              <div className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"} max-w-[80%]`}>
                {m.suggestion ? (
                  <div className="rounded-2xl border border-teal/40 bg-teal/10 px-3 py-2 text-sm text-parchment">
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
                      className="mt-2 rounded-full bg-teal px-3 py-1 text-xs font-semibold text-surface"
                    >
                      {t("handoff.openButton")}
                    </button>
                  </div>
                ) : (
                  <div className={`w-full rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "bg-teal text-surface" : "bg-panel-2 text-parchment"}`}>
                    {m.role === "assistant" ? <Markdown>{m.content}</Markdown> : <p>{m.content}</p>}
                  </div>
                )}
                {m.role === "assistant" && !m.suggestion && m.content && (
                  <div className="mt-1 flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => handleCopy(i, m.content)}
                      aria-label={t("actions.copy")}
                      title={copiedIndex === i ? t("actions.copied") : t("actions.copy")}
                      className="rounded p-1 text-muted hover:text-parchment transition-colors"
                    >
                      {copiedIndex === i ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
                    </button>
                    {i === messages.length - 1 && (
                      <button
                        type="button"
                        onClick={handleRegenerate}
                        disabled={loading}
                        aria-label={t("actions.regenerate")}
                        title={t("actions.regenerate")}
                        className="rounded p-1 text-muted hover:text-parchment transition-colors disabled:opacity-50"
                      >
                        <RotateCcw size={13} aria-hidden="true" />
                      </button>
                    )}
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
            </div>
          ))}
          {loading && (
            <div className="flex gap-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-panel-2 text-teal">
                <Bot size={14} aria-hidden="true" />
              </div>
              <div className="max-w-[80%] w-full rounded-2xl px-3 py-2 text-sm bg-panel-2 text-parchment">
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
            className="flex-1 rounded-full border border-border bg-panel-2 px-4 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
          <button type="submit" disabled={loading} className="rounded-full bg-teal px-4 py-2 text-xs font-semibold text-surface disabled:opacity-50">
            {loading ? "..." : t("send")}
          </button>
        </form>
      </Card>

      <Card className="flex flex-col w-full lg:w-72 shrink-0 overflow-hidden">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-parchment">{t("history.title")}</h2>
          <button
            onClick={handleNewChat}
            className="flex items-center gap-1 rounded-full bg-teal/15 px-3 py-1 text-xs font-semibold text-teal hover:bg-teal/25"
          >
            <Plus size={13} aria-hidden="true" /> {t("history.newChat")}
          </button>
        </div>
        <div className="flex-1 overflow-auto flex flex-col gap-3">
          {sessions.length === 0 && <p className="text-xs text-muted">{t("history.empty")}</p>}
          {groupedSessions.map((group) => (
            <div key={group.label}>
              <p className="text-[10px] uppercase tracking-wide text-muted mb-1">{group.label}</p>
              <div className="flex flex-col gap-1">
                {group.items.map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs cursor-pointer transition-colors ${
                      s.id === sessionId ? "bg-teal/15 text-teal" : "text-muted hover:bg-panel-2 hover:text-parchment"
                    }`}
                    onClick={() => handleSelectSession(s.id)}
                  >
                    <span className="flex-1 truncate">{s.preview || s.summary || `#${s.id}`}</span>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setSessionPendingDelete(s.id); }}
                      aria-label={t("history.delete")}
                      title={t("history.delete")}
                      className="opacity-0 group-hover:opacity-100 text-muted hover:text-danger transition-opacity"
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <ConfirmDialog
        open={sessionPendingDelete != null}
        title={t("history.deleteConfirmTitle")}
        message={t("history.deleteConfirmMessage")}
        confirmLabel={t("history.deleteConfirmButton")}
        cancelLabel={t("history.deleteCancelButton")}
        onConfirm={confirmDeleteSession}
        onCancel={() => setSessionPendingDelete(null)}
      />
    </div>
  );
}
