import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { costSaving } from "../api";
import AgentStepTimeline, { type AgentStep } from "../components/AgentStepTimeline";
import RecommendationCard, { type Recommendation } from "../components/RecommendationCard";
import Markdown from "../components/Markdown";
import Card from "../components/Card";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type AgentRun = {
  id: number;
  agent_type: string;
  goal: string;
  summary: string;
  steps: AgentStep[];
  recommendations: Recommendation[];
  created_at: string;
};

const AGENT_TYPE_ORDER = ["cost_saving", "forecast", "contract_risk"];

export default function CostSavingAgentPage() {
  const { t } = useTranslation("costSaving");
  useDocumentTitle(t("title"));

  const AGENT_TYPES: Record<string, { label: string; description: string; presetGoals: string[] }> =
    Object.fromEntries(
      AGENT_TYPE_ORDER.map((type) => [
        type,
        {
          label: t(`agentTypes.${type}.label`),
          description: t(`agentTypes.${type}.description`),
          presetGoals: t(`agentTypes.${type}.presetGoals`, { returnObjects: true }) as string[],
        },
      ])
    );

  // Handed off from the Chat page when the intent router (POST /assistant)
  // decides a message is a goal for one of these agents rather than a
  // spend question - prefills the type/goal so the user only has to
  // press "Analyze", instead of retyping what they already asked.
  const location = useLocation();
  const handoff = location.state as { agentType?: string; goal?: string } | null;
  const initialAgentType = handoff?.agentType && AGENT_TYPES[handoff.agentType] ? handoff.agentType : "cost_saving";

  const [agentType, setAgentType] = useState(initialAgentType);
  const [goal, setGoal] = useState(handoff?.goal || AGENT_TYPES[initialAgentType].presetGoals[0]);
  const [running, setRunning] = useState(false);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [history, setHistory] = useState<AgentRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [historyTypeFilter, setHistoryTypeFilter] = useState("");
  const [historySearch, setHistorySearch] = useState("");

  // Independent of the `agentType` tabs above (which pick what a NEW
  // analysis uses) - this refetches the history list scoped to a type,
  // reusing the agent_type param the backend already supported.
  useEffect(() => {
    costSaving.history(0, 20, historyTypeFilter || undefined).then(setHistory).catch(() => {});
  }, [historyTypeFilter]);

  const filteredHistory = historySearch.trim()
    ? history.filter((h) => h.goal.toLowerCase().includes(historySearch.trim().toLowerCase()))
    : history;

  function handleAgentTypeChange(type: string) {
    setAgentType(type);
    setGoal(AGENT_TYPES[type].presetGoals[0]);
    setRun(null);
    setError(null);
  }

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!goal.trim() || running) return;
    setRunning(true);
    setError(null);
    setRun(null);
    setLiveSteps([]);
    // Accumulated outside React state so the "done" handler below always
    // sees every step gathered so far, not a stale closure over liveSteps.
    const collectedSteps: AgentStep[] = [];
    try {
      for await (const evt of costSaving.analyzeStream(goal, agentType)) {
        if (evt.event === "step") {
          collectedSteps.push(evt.data);
          setLiveSteps([...collectedSteps]);
        } else if (evt.event === "done") {
          const completed: AgentRun = {
            id: evt.data.id,
            agent_type: evt.data.agent_type,
            goal: evt.data.goal,
            summary: evt.data.summary,
            steps: collectedSteps,
            recommendations: evt.data.recommendations,
            created_at: evt.data.created_at,
          };
          setRun(completed);
          setHistory((h) => [completed, ...h].slice(0, 20));
        }
      }
    } catch (err: any) {
      setError(err.message);
    }
    setRunning(false);
  }

  const displaySteps = run ? run.steps : liveSteps;
  const config = AGENT_TYPES[agentType];

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold">{t("title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("subtitle")}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {AGENT_TYPE_ORDER.map((type) => (
          <button
            type="button"
            key={type}
            onClick={() => handleAgentTypeChange(type)}
            disabled={running}
            className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
              agentType === type ? "border-teal bg-teal/10 text-teal" : "border-border text-muted hover:text-parchment"
            }`}
          >
            {AGENT_TYPES[type].label}
          </button>
        ))}
      </div>
      <p className="-mt-4 text-sm text-muted">{config.description}</p>

      <form onSubmit={handleAnalyze} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          {config.presetGoals.map((g) => (
            <button
              type="button"
              key={g}
              onClick={() => setGoal(g)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                goal === g ? "border-teal text-teal" : "border-border text-muted hover:text-parchment"
              }`}
            >
              {g}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            disabled={running}
            placeholder={t("goalPlaceholder")}
            aria-label={t("goalPlaceholder")}
            className="flex-1 rounded-full border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal"
          />
          <button
            type="submit"
            disabled={running}
            className="rounded-full bg-teal px-4 py-2 text-xs font-semibold text-surface disabled:opacity-50"
          >
            {running ? t("analyzing") : t("analyze")}
          </button>
        </div>
      </form>

      {error && <p className="text-sm text-danger">{t("error", { message: error })}</p>}

      {(running || run) && (
        <div className="flex flex-col gap-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold">{t("reasoning")}</h2>
            {/* Live runs already arrive one step at a time over SSE, so no
                extra client-side staging is needed (animate=false); a run
                loaded from history replays with the staged reveal instead. */}
            <AgentStepTimeline steps={displaySteps} animate={!running} />
            {run?.summary && (
              <div className="mt-3 border-t border-border pt-3 text-sm text-parchment">
                <Markdown>{run.summary}</Markdown>
              </div>
            )}
          </Card>

          {run && (
            <div>
              <h2 className="mb-3 text-sm font-semibold">
                {run.recommendations.length > 0 ? t("recommendationsCount", { count: run.recommendations.length }) : t("recommendations")}
              </h2>
              {run.recommendations.length === 0 ? (
                <p className="text-sm text-muted">{t("noRecommendations")}</p>
              ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {run.recommendations.map((r, i) => (
                    <RecommendationCard key={i} rec={r} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">{t("history")}</h2>
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setHistoryTypeFilter("")}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${historyTypeFilter === "" ? "border-teal text-teal" : "border-border text-muted hover:text-parchment"}`}
            >
              {t("historyFilter.all")}
            </button>
            {AGENT_TYPE_ORDER.map((type) => (
              <button
                type="button"
                key={type}
                onClick={() => setHistoryTypeFilter(type)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${historyTypeFilter === type ? "border-teal text-teal" : "border-border text-muted hover:text-parchment"}`}
              >
                {AGENT_TYPES[type].label}
              </button>
            ))}
            <input
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              placeholder={t("historyFilter.searchPlaceholder")}
              aria-label={t("historyFilter.searchPlaceholder")}
              className="ml-auto min-w-[160px] rounded-full border border-border bg-panel-2 px-3 py-1 text-xs text-parchment placeholder:text-muted focus:outline-none focus:border-teal"
            />
          </div>
          <div className="flex flex-col gap-2">
            {filteredHistory.map((h) => (
              <button
                key={h.id}
                onClick={() => {
                  setAgentType(h.agent_type);
                  setRun({ ...h, steps: h.steps });
                }}
                className="flex items-center justify-between border-b border-border/60 py-1.5 text-left text-sm hover:text-teal"
              >
                <span className="flex items-center gap-2">
                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                    {AGENT_TYPES[h.agent_type]?.label ?? h.agent_type}
                  </span>
                  {h.goal}
                </span>
                <span className="text-xs text-muted">{new Date(h.created_at).toLocaleString()}</span>
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
