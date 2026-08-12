import { useEffect, useState } from "react";
import { costSaving } from "../api";
import AgentStepTimeline, { type AgentStep } from "../components/AgentStepTimeline";
import RecommendationCard, { type Recommendation } from "../components/RecommendationCard";

type AgentRun = {
  id: number;
  goal: string;
  summary: string;
  steps: AgentStep[];
  recommendations: Recommendation[];
  created_at: string;
};

const PRESET_GOALS = [
  "Trova opportunità di risparmio",
  "Analizza le variazioni di spesa per fornitore",
  "Verifica i contratti in scadenza",
];

export default function CostSavingAgentPage() {
  const [goal, setGoal] = useState(PRESET_GOALS[0]);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [history, setHistory] = useState<AgentRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    costSaving.history().then(setHistory).catch(() => {});
  }, []);

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (!goal.trim() || running) return;
    setRunning(true);
    setError(null);
    setRun(null);
    try {
      const res = await costSaving.analyze(goal);
      setRun(res);
      setHistory((h) => [res, ...h].slice(0, 20));
    } catch (err: any) {
      setError(err.message);
    }
    setRunning(false);
  }

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold">Cost Saving Agent</h1>
        <p className="mt-1 text-sm text-muted">
          Un agente AI che analizza la spesa reale (fornitori, anomalie, contratti) e propone opportunità di
          risparmio verificabili, non numeri inventati.
        </p>
      </div>

      <form onSubmit={handleAnalyze} className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          {PRESET_GOALS.map((g) => (
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
            placeholder="Descrivi l'obiettivo..."
            className="flex-1 rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal"
          />
          <button
            type="submit"
            disabled={running}
            className="rounded bg-teal px-4 py-2 text-xs font-semibold text-surface disabled:opacity-50"
          >
            {running ? "Analisi in corso..." : "Analizza"}
          </button>
        </div>
      </form>

      {error && <p className="text-sm text-danger">Errore: {error}</p>}

      {run && (
        <div className="flex flex-col gap-4">
          <div className="rounded border border-border bg-panel p-4">
            <h2 className="mb-3 text-sm font-semibold">Ragionamento dell'agente</h2>
            <AgentStepTimeline steps={run.steps} />
            {run.summary && <p className="mt-3 border-t border-border pt-3 text-sm text-parchment">{run.summary}</p>}
          </div>

          <div>
            <h2 className="mb-3 text-sm font-semibold">
              Raccomandazioni {run.recommendations.length > 0 ? `(${run.recommendations.length})` : ""}
            </h2>
            {run.recommendations.length === 0 ? (
              <p className="text-sm text-muted">Nessuna opportunità di risparmio rilevata nei dati attuali.</p>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {run.recommendations.map((r, i) => (
                  <RecommendationCard key={i} rec={r} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="mb-3 text-sm font-semibold">Cronologia</h2>
          <div className="flex flex-col gap-2">
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => setRun({ ...h, steps: h.steps })}
                className="flex items-center justify-between border-b border-border/60 py-1.5 text-left text-sm hover:text-teal"
              >
                <span>{h.goal}</span>
                <span className="text-xs text-muted">{new Date(h.created_at).toLocaleString()}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
