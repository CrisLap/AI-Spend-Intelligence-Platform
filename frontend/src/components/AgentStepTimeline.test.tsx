import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AgentStepTimeline, { type AgentStep } from "./AgentStepTimeline";

const steps: AgentStep[] = [
  { index: 0, thought: "Checking spend overview", tool: "spend_overview", tool_input: "overview", observation: "Total spend: €1,000" },
  { index: 1, thought: "Done", tool: null, tool_input: null, observation: null },
];

describe("AgentStepTimeline", () => {
  it("shows a placeholder message when there are no steps", () => {
    render(<AgentStepTimeline steps={[]} />);
    expect(screen.getByText(/Nessun passaggio registrato/)).toBeInTheDocument();
  });

  it("renders every step immediately when animate is false", () => {
    render(<AgentStepTimeline steps={steps} animate={false} />);
    expect(screen.getByText(/Checking spend overview/)).toBeInTheDocument();
    expect(screen.getByText(/Total spend: €1,000/)).toBeInTheDocument();
    expect(screen.getByText(/Done/)).toBeInTheDocument();
  });

  it("renders the tool name and input on an action step", () => {
    render(<AgentStepTimeline steps={steps} animate={false} />);
    expect(screen.getByText(/spend_overview/)).toBeInTheDocument();
    expect(screen.getByText(/"overview"/)).toBeInTheDocument();
  });

  describe("staged reveal (animate=true, the default)", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("reveals steps one at a time instead of all at once", () => {
      render(<AgentStepTimeline steps={steps} />);

      // Nothing revealed yet on the very first render.
      expect(screen.queryByText(/Checking spend overview/)).not.toBeInTheDocument();
      expect(screen.getByText(/Analisi in corso/)).toBeInTheDocument();

      act(() => vi.advanceTimersByTime(550));
      expect(screen.getByText(/Checking spend overview/)).toBeInTheDocument();
      expect(screen.queryByText(/Done/)).not.toBeInTheDocument();

      act(() => vi.advanceTimersByTime(550));
      expect(screen.getByText(/Done/)).toBeInTheDocument();
      expect(screen.queryByText(/Analisi in corso/)).not.toBeInTheDocument();
    });
  });
});
