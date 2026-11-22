import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";
import { analytics } from "../api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { SkeletonBlock } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import Card from "../components/Card";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Dash = {
  total_spend: number; total_items: number; total_documents: number;
  anomaly_count: number; duplicate_count: number;
  spend_by_category: { category: string; total: number; count: number; percentage: number }[];
  spend_by_month: { month: string; total: number; count: number }[];
  top_suppliers: { supplier: string; total: number; count: number }[];
  top_categories: { category: string; total: number; percentage: number }[];
};

const LIST_LIMIT = 6;

const TOOLTIP_STYLE = {
  background: "var(--color-panel)",
  border: "1px solid var(--color-border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--color-parchment)",
};

const AXIS_TICK = { fontSize: 12, fill: "var(--color-muted)", fontFamily: "var(--font-mono)" };

/** Ranked row: label, figure in mono, and a thin bar relative to the largest value. */
function BarRow({ label, value, share, to }: { label: string; value: string; share: number; to: string }) {
  return (
    <Link to={to} className="group -mx-2 flex flex-col gap-1.5 rounded-lg px-2 py-2 transition-colors hover:bg-panel-2/60">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate text-parchment">{label}</span>
        <span className="font-mono tabular-nums text-secondary">{value}</span>
      </div>
      <div className="h-1 rounded-full bg-panel-2">
        <div
          className="h-1 rounded-full bg-teal/70 transition-colors group-hover:bg-teal"
          style={{ width: `${Math.max(share, 2)}%` }}
        />
      </div>
    </Link>
  );
}

export default function Dashboard() {
  const { t, i18n } = useTranslation("dashboard");
  useDocumentTitle(t("title"));
  const [data, setData] = useState<Dash | null>(null);
  const [loading, setLoading] = useState(true);

  // useGrouping: true also groups 4-digit numbers (it-IT defaults to "5340" but
  // "32.000"), so figures in the same column read alike.
  const eur = new Intl.NumberFormat(i18n.resolvedLanguage, { style: "currency", currency: "EUR", maximumFractionDigits: 0, useGrouping: true });
  const num = new Intl.NumberFormat(i18n.resolvedLanguage, { useGrouping: true });

  function load() {
    setLoading(true);
    analytics.dashboard().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-8">
        <SkeletonBlock className="h-8 w-40" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => <SkeletonBlock key={i} className="h-24" />)}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <SkeletonBlock className="h-96 lg:col-span-2" />
          <SkeletonBlock className="h-96" />
        </div>
      </div>
    );
  }
  if (!data) return <InlineError message={t("loadingError")} onRetry={load} />;

  if (data.total_documents === 0) {
    return (
      <div className="flex flex-col gap-8">
        <h1 className="text-page-title font-medium leading-tight tracking-tight">{t("title")}</h1>
        <Card padding="xl" className="flex flex-col items-center justify-center gap-3 border-dashed text-center">
          <Upload size={24} strokeWidth={1.5} className="text-muted" aria-hidden="true" />
          <p className="text-sm font-medium text-parchment">{t("emptyState.title")}</p>
          <p className="max-w-sm text-sm text-muted">{t("emptyState.description")}</p>
          <Link
            to="/documents"
            className="mt-2 inline-flex h-9 items-center rounded-lg bg-teal px-4 text-sm font-medium text-surface transition hover:brightness-110 active:scale-[0.98]"
          >
            {t("emptyState.cta")}
          </Link>
        </Card>
      </div>
    );
  }

  const categoryRows = (() => {
    const top = data.spend_by_category.slice(0, LIST_LIMIT);
    const rest = data.spend_by_category.slice(LIST_LIMIT);
    if (!rest.length) return top;
    return [
      ...top,
      {
        category: t("other"),
        total: rest.reduce((sum, c) => sum + c.total, 0),
        count: rest.reduce((sum, c) => sum + c.count, 0),
        percentage: Math.round(rest.reduce((sum, c) => sum + c.percentage, 0) * 10) / 10,
      },
    ];
  })();
  const maxCategory = Math.max(...categoryRows.map((c) => c.total), 1);
  const maxSupplier = Math.max(...data.top_suppliers.map((s) => s.total), 1);

  // Figures stay neutral; color appears only when it carries a state.
  const kpis = [
    { label: t("kpi.totalSpend"), value: eur.format(data.total_spend), tone: "text-parchment", to: "/documents" },
    { label: t("kpi.items"), value: num.format(data.total_items), tone: "text-parchment", to: "/documents" },
    { label: t("kpi.documents"), value: num.format(data.total_documents), tone: "text-parchment", to: "/documents" },
    { label: t("kpi.anomalies"), value: num.format(data.anomaly_count), tone: data.anomaly_count > 0 ? "text-danger" : "text-parchment", to: "/anomalies" },
    { label: t("kpi.duplicates"), value: num.format(data.duplicate_count), tone: data.duplicate_count > 0 ? "text-amber" : "text-parchment", to: "/duplicates" },
  ];

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-page-title font-medium leading-tight tracking-tight">{t("title")}</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {kpis.map((k) => (
          <Link key={k.label} to={k.to} className="rounded-xl border border-border bg-panel p-5 transition-colors hover:bg-panel-2/60">
            <p className="text-sm text-muted">{k.label}</p>
            <p className={`mt-3 font-mono text-metric font-medium leading-none tabular-nums ${k.tone}`}>{k.value}</p>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card padding="lg" className="flex flex-col lg:col-span-2">
          <h2 className="mb-6 text-sm font-medium text-parchment">{t("monthlySpend")}</h2>
          {/* The card stretches to the height of the suppliers list beside it;
              the chart fills whatever is left instead of leaving dead space. */}
          <div className="min-h-[320px] flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.spend_by_month} margin={{ left: 0, right: 0, top: 4 }}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="month" axisLine={false} tickLine={false} tick={AXIS_TICK} />
                <YAxis axisLine={false} tickLine={false} width={64} tick={AXIS_TICK} tickFormatter={(v) => num.format(Number(v))} />
                <Tooltip cursor={{ fill: "var(--color-panel-2)" }} contentStyle={TOOLTIP_STYLE} formatter={(v) => eur.format(Number(v))} />
                <Bar dataKey="total" fill="var(--color-teal)" radius={[4, 4, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card padding="lg">
          <h2 className="mb-4 text-sm font-medium text-parchment">{t("topSuppliers")}</h2>
          <div className="flex flex-col">
            {data.top_suppliers.map((s) => (
              <BarRow
                key={s.supplier}
                label={s.supplier}
                value={eur.format(s.total)}
                share={(s.total / maxSupplier) * 100}
                to={`/search?q=${encodeURIComponent(s.supplier)}`}
              />
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card padding="lg">
          <h2 className="mb-4 text-sm font-medium text-parchment">{t("spendByCategory")}</h2>
          <div className="flex flex-col">
            {categoryRows.map((c) => (
              <BarRow
                key={c.category}
                label={c.category}
                value={`${eur.format(c.total)} / ${c.percentage}%`}
                share={(c.total / maxCategory) * 100}
                to={`/search?q=${encodeURIComponent(c.category)}`}
              />
            ))}
          </div>
        </Card>
        <Card padding="lg">
          <h2 className="mb-4 text-sm font-medium text-parchment">{t("topCategories")}</h2>
          <div className="flex flex-col">
            {data.top_categories.map((c) => (
              <Link
                key={c.category}
                to={`/search?q=${encodeURIComponent(c.category)}`}
                className="-mx-2 flex items-baseline justify-between gap-3 rounded-lg px-2 py-2 text-sm transition-colors hover:bg-panel-2/60"
              >
                <span className="truncate text-parchment">{c.category}</span>
                <span className="font-mono tabular-nums text-secondary">{c.percentage}%</span>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
