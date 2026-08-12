import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Markdown from "./Markdown";

export type AgentStep = {
  index: number;
  thought?: string | null;
  tool?: string | null;
  tool_input?: string | null;
  observation?: string | null;
  mode?: string | null;
};

// The backend returns the full trace in one response for history replays
// (live runs stream one step at a time over SSE - see CostSavingAgentPage's
// animate=!running). This component reveals steps one at a time on the
// client for a replay instead of dumping them all at once, so the agent's
// reasoning still reads as a sequence - the data behind it is real, only
// the reveal is staged.
const REVEAL_INTERVAL_MS = 550;

export default function AgentStepTimeline({ steps, animate = true }: { steps: AgentStep[]; animate?: boolean }) {
  const { t } = useTranslation("costSaving");
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
    return <p className="text-sm text-muted">{t("timeline.empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {steps.slice(0, visible).map((s, i) => (
        <div key={i} className="rounded border border-border bg-panel-2 p-3 text-sm">
          {s.thought && (
            <div className="text-parchment">
              <span className="text-muted">{t("timeline.thought")}</span> <Markdown>{s.thought}</Markdown>
            </div>
          )}
          {s.tool && (
            <p className="mt-1 text-teal">
              <span className="text-muted">{t("timeline.action")}</span> {s.tool}
              {s.tool_input ? `("${s.tool_input}")` : ""}
              {s.mode && (
                <span className="ml-2 rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">
                  {t(`timeline.mode.${s.mode}`, { defaultValue: s.mode })}
                </span>
              )}
            </p>
          )}
          {s.observation && (
            <div className="mt-1 whitespace-pre-line text-xs text-muted">
              <Markdown>{s.observation}</Markdown>
            </div>
          )}
        </div>
      ))}
      {animate && visible < steps.length && <p className="text-xs italic text-muted">{t("timeline.analyzing")}</p>}
    </div>
  );
}
