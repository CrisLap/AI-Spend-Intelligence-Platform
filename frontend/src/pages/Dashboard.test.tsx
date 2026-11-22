import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  analytics: { dashboard: vi.fn() },
}));

// jsdom has no layout, so ResponsiveContainer would render nothing and recharts
// would need ResizeObserver. Stub the chart primitives: BarChart exposes the data
// it receives, and YAxis exposes what its tickFormatter produces for a sample value.
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ data, children }: { data: unknown[]; children: React.ReactNode }) => (
    <div data-testid="bar-chart" data-points={data.length}>{children}</div>
  ),
  YAxis: ({ tickFormatter }: { tickFormatter: (v: number) => string }) => (
    <span data-testid="y-tick">{tickFormatter(32000)}</span>
  ),
  XAxis: () => null,
  Bar: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}));

import { analytics } from "../api";
import i18n from "../i18n";
import Dashboard from "./Dashboard";

type Dash = Awaited<ReturnType<typeof analytics.dashboard>>;

const base = {
  total_spend: 110702.1,
  total_items: 41,
  total_documents: 15,
  anomaly_count: 10,
  duplicate_count: 4,
  spend_by_category: [
    { category: "Consulting", total: 66700, count: 9, percentage: 60.3 },
    { category: "Hardware", total: 14989, count: 5, percentage: 13.5 },
  ],
  spend_by_month: [
    { month: "2026-09", total: 4800, count: 3 },
    { month: "2026-10", total: 32000, count: 7 },
  ],
  top_suppliers: [
    { supplier: "Deloitte Consulting", total: 63500, count: 6 },
    { supplier: "Arredo Ufficio Spa", total: 5340, count: 2 },
  ],
  top_categories: [{ category: "Consulting", total: 66700, percentage: 60.3 }],
};

function mockDashboard(overrides: Partial<typeof base> = {}) {
  vi.mocked(analytics.dashboard).mockResolvedValue({ ...base, ...overrides } as unknown as Dash);
}

function renderDashboard() {
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

/** The figure rendered under a KPI label. */
function kpiValue(label: string) {
  return screen.getByText(label).nextElementSibling as HTMLElement;
}

describe("Dashboard page", () => {
  beforeEach(() => {
    vi.mocked(analytics.dashboard).mockReset();
  });

  it("renders every KPI figure formatted in the active language", async () => {
    mockDashboard();
    renderDashboard();

    expect(await screen.findByText("Total Spend")).toBeInTheDocument();
    expect(kpiValue("Total Spend")).toHaveTextContent("€110,702");
    expect(kpiValue("Items")).toHaveTextContent("41");
    expect(kpiValue("Documents")).toHaveTextContent("15");
    expect(kpiValue("Anomalies")).toHaveTextContent("10");
    expect(kpiValue("Duplicates")).toHaveTextContent("4");
  });

  it("colors anomaly/duplicate figures only when they carry a state", async () => {
    mockDashboard({ anomaly_count: 10, duplicate_count: 0 });
    renderDashboard();
    await screen.findByText("Total Spend");

    expect(kpiValue("Anomalies")).toHaveClass("text-danger");
    expect(kpiValue("Duplicates")).not.toHaveClass("text-amber");
    expect(kpiValue("Total Spend")).toHaveClass("text-parchment");
  });

  it("groups 4-digit figures in Italian too, so 5340 and 32000 read alike", async () => {
    await i18n.changeLanguage("it");
    mockDashboard();
    renderDashboard();

    // Intl's default it-IT skips the separator below 5 digits ("5340"); the page forces it.
    const supplierRow = (await screen.findByText("Arredo Ufficio Spa")).closest("a") as HTMLElement;
    expect(supplierRow.textContent).toMatch(/5\.340/);
    expect(screen.getByTestId("y-tick")).toHaveTextContent("32.000");
  });

  it("passes the monthly series to the main chart", async () => {
    mockDashboard();
    renderDashboard();

    expect(await screen.findByTestId("bar-chart")).toHaveAttribute("data-points", "2");
  });

  it("ranks suppliers as links into search", async () => {
    mockDashboard();
    renderDashboard();

    const row = (await screen.findByText("Deloitte Consulting")).closest("a") as HTMLElement;
    expect(row).toHaveAttribute("href", "/search?q=Deloitte%20Consulting");
    expect(within(row).getByText(/63,500/)).toBeInTheDocument();
  });

  it("folds categories beyond the sixth into one Other row with summed totals", async () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      category: `Cat ${i + 1}`,
      total: 1000 - i * 100, // 1000, 900, ... 300
      count: 1,
      percentage: 10,
    }));
    mockDashboard({ spend_by_category: many });
    renderDashboard();

    const other = (await screen.findByText("Other")).closest("a") as HTMLElement;
    // Cat 7 (400) + Cat 8 (300) = 700, 10% + 10% = 20%
    expect(other.textContent).toContain("700");
    expect(other.textContent).toContain("20%");
    expect(screen.queryByText("Cat 7")).not.toBeInTheDocument();
    expect(screen.getByText("Cat 6")).toBeInTheDocument();
  });

  it("shows the empty state with an upload link when there are no documents", async () => {
    mockDashboard({ total_documents: 0 });
    renderDashboard();

    expect(await screen.findByText("No spend data yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload a document" })).toHaveAttribute("href", "/documents");
    expect(screen.queryByText("Total Spend")).not.toBeInTheDocument();
  });

  it("shows an inline error and reloads on retry", async () => {
    vi.mocked(analytics.dashboard).mockRejectedValueOnce(new Error("boom"));
    renderDashboard();

    expect(await screen.findByText("Loading error")).toBeInTheDocument();

    mockDashboard();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByText("Total Spend")).toBeInTheDocument());
    expect(analytics.dashboard).toHaveBeenCalledTimes(2);
  });
});
