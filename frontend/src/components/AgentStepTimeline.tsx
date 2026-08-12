import { useEffect, useState } from "react";

export type AgentStep = {
  index: number;
  thought?: string | null;
  tool?: string | null;
  tool_input?: string | null;
  observation?: string | null;
};

// The backend returns the full trace in one response (no streaming exists
// in this project yet - see the Fase 2 roadmap). This component reveals
// steps one at a time on the client instead of dumping them all at once,
// so the agent's reasoning still reads as a sequence - the data behind it
// is real, only the reveal is staged.
const REVEAL_INTERVAL_MS = 550;

export default function AgentStepTimeline({ steps, animate = true }: { steps: AgentStep[]; animate?: boolean }) {
  const [visible, setVisible] = useState(animate ? 0 : steps.length);

  useEffect(() => {
    if (!animate) {
      setVisible(steps.length);
      return;
    }
    setVisible(0);
    if (steps.length === 0) return;
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setVisible(i);
      if (i >= steps.length) clearInterval(id);
    }, REVEAL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [steps, animate]);

  if (steps.length === 0) {
    return <p className="text-sm text-muted">Nessun passaggio registrato.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {steps.slice(0, visible).map((s, i) => (
        <div key={i} className="rounded border border-border bg-panel-2 p-3 text-sm">
          {s.thought && (
            <p className="text-parchment">
              <span className="text-muted">Thought:</span> {s.thought}
            </p>
          )}
          {s.tool && (
            <p className="mt-1 text-teal">
              <span className="text-muted">Action:</span> {s.tool}
              {s.tool_input ? `("${s.tool_input}")` : ""}
            </p>
          )}
          {s.observation && (
            <p className="mt-1 whitespace-pre-line text-xs text-muted">{s.observation}</p>
          )}
        </div>
      ))}
      {animate && visible < steps.length && <p className="text-xs italic text-muted">Analisi in corso...</p>}
    </div>
  );
}
