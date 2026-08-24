import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";
import { analytics } from "../api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { SkeletonBlock } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Dash = {
  total_spend: number; total_items: number; total_documents: number;
  anomaly_count: number; duplicate_count: number;
  spend_by_category: { category: string; total: number; count: number; percentage: number }[];
  spend_by_month: { month: string; total: number; count: number }[];
  top_suppliers: { supplier: string; total: number; count: number }[];
  top_categories: { category: string; total: number; percentage: number }[];
};

const COLORS = ["#2dd4bf", "#f59e0b", "#ef4444", "#22c55e", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];
const PIE_SLICE_LIMIT = 6;

export default function Dashboard() {
  const { t } = useTranslation("dashboard");
  useDocumentTitle(t("title"));
  const [data, setData] = useState<Dash | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    analytics.dashboard().then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }
  useEffect(load, []);

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <SkeletonBlock className="h-7 w-40" />
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => <SkeletonBlock key={i} className="h-20" />)}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SkeletonBlock className="h-72" />
          <SkeletonBlock className="h-72" />
        </div>
      </div>
    );
  }
  if (!data) return <InlineError message={t("loadingError")} onRetry={load} />;

  if (data.total_documents === 0) {
    return (
      <div className="flex flex-col gap-6">
        <h1 className="text-xl font-bold">{t("title")}</h1>
        <div className="flex flex-col items-center justify-center gap-3 rounded border border-dashed border-border bg-panel p-12 text-center">
          <Upload size={28} className="text-muted" aria-hidden="true" />
          <p className="text-sm font-semibold text-parchment">{t("emptyState.title")}</p>
          <p className="text-xs text-muted max-w-sm">{t("emptyState.description")}</p>
          <Link to="/documents" className="mt-2 rounded bg-teal px-4 py-1.5 text-xs font-semibold text-surface hover:opacity-90">
            {t("emptyState.cta")}
          </Link>
        </div>
      </div>
    );
  }

  const topCategorySlices = data.spend_by_category.slice(0, PIE_SLICE_LIMIT);
  const restCategorySlices = data.spend_by_category.slice(PIE_SLICE_LIMIT);
  const pieData = restCategorySlices.length
    ? [...topCategorySlices, {
        category: t("other"),
        total: restCategorySlices.reduce((sum, c) => sum + c.total, 0),
        count: restCategorySlices.reduce((sum, c) => sum + c.count, 0),
        percentage: Math.round(restCategorySlices.reduce((sum, c) => sum + c.percentage, 0) * 10) / 10,
      }]
    : topCategorySlices;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold">{t("title")}</h1>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: t("kpi.totalSpend"), value: `€${data.total_spend.toLocaleString()}`, color: "text-teal", to: "/documents" },
          { label: t("kpi.items"), value: data.total_items, color: "text-parchment", to: "/documents" },
          { label: t("kpi.documents"), value: data.total_documents, color: "text-parchment", to: "/documents" },
          { label: t("kpi.anomalies"), value: data.anomaly_count, color: data.anomaly_count > 0 ? "text-danger" : "text-ok", to: "/anomalies" },
          { label: t("kpi.duplicates"), value: data.duplicate_count, color: data.duplicate_count > 0 ? "text-amber" : "text-ok", to: "/duplicates" },
        ].map((k) => (
          <Link key={k.label} to={k.to} className="rounded border border-border bg-panel p-4 transition-colors hover:border-teal">
            <p className="text-xs text-muted uppercase tracking-wide">{k.label}</p>
            <p className={`text-2xl font-bold mt-1 ${k.color}`}>{typeof k.value === "number" ? k.value.toLocaleString() : k.value}</p>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">{t("spendByCategory")}</h2>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={pieData} dataKey="total" nameKey="category" cx="50%" cy="50%" outerRadius={90} label={({ category, percentage }) => `${category} ${percentage}%`}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">{t("monthlySpend")}</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.spend_by_month}>
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#6b6b80" }} />
              <YAxis tick={{ fontSize: 11, fill: "#6b6b80" }} />
              <Tooltip />
              <Bar dataKey="total" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">{t("topSuppliers")}</h2>
          <div className="flex flex-col gap-2">
            {data.top_suppliers.map((s) => (
              <Link key={s.supplier} to={`/search?q=${encodeURIComponent(s.supplier)}`} className="flex items-center justify-between text-sm border-b border-border/60 py-1.5 hover:text-teal">
                <span>{s.supplier}</span>
                <span className="text-teal">€{s.total.toLocaleString()}</span>
              </Link>
            ))}
          </div>
        </div>
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">{t("topCategories")}</h2>
          <div className="flex flex-col gap-2">
            {data.top_categories.map((c) => (
              <Link key={c.category} to={`/search?q=${encodeURIComponent(c.category)}`} className="flex items-center justify-between text-sm border-b border-border/60 py-1.5 hover:text-teal">
                <span>{c.category}</span>
                <span className="text-amber">{c.percentage}%</span>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
