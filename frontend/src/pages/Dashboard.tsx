import { useEffect, useState } from "react";
import { analytics } from "../api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

type Dash = {
  total_spend: number; total_items: number; total_documents: number;
  anomaly_count: number; duplicate_count: number;
  spend_by_category: { category: string; total: number; count: number; percentage: number }[];
  spend_by_month: { month: string; total: number; count: number }[];
  top_suppliers: { supplier: string; total: number; count: number }[];
  top_categories: { category: string; total: number; percentage: number }[];
};

const COLORS = ["#2dd4bf", "#f59e0b", "#ef4444", "#22c55e", "#8b5cf6", "#ec4899", "#06b6d4", "#f97316"];

export default function Dashboard() {
  const [data, setData] = useState<Dash | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analytics.dashboard().then(setData).finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-muted">Loading dashboard...</p>;
  if (!data) return <p className="text-danger">Loading error</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label: "Total Spend", value: `€${data.total_spend.toLocaleString()}`, color: "text-teal" },
          { label: "Items", value: data.total_items, color: "text-parchment" },
          { label: "Documents", value: data.total_documents, color: "text-parchment" },
          { label: "Anomalies", value: data.anomaly_count, color: data.anomaly_count > 0 ? "text-danger" : "text-ok" },
          { label: "Duplicates", value: data.duplicate_count, color: data.duplicate_count > 0 ? "text-amber" : "text-ok" },
        ].map((k) => (
          <div key={k.label} className="rounded border border-border bg-panel p-4">
            <p className="text-xs text-muted uppercase tracking-wide">{k.label}</p>
            <p className={`text-2xl font-bold mt-1 ${k.color}`}>{typeof k.value === "number" ? k.value.toLocaleString() : k.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">Spend by Category</h2>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={data.spend_by_category.slice(0, 6)} dataKey="total" nameKey="category" cx="50%" cy="50%" outerRadius={90} label={({ category, percentage }) => `${category} ${percentage}%`}>
                {data.spend_by_category.slice(0, 6).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">Monthly Spend</h2>
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
          <h2 className="text-sm font-semibold mb-3">Top Suppliers</h2>
          <div className="flex flex-col gap-2">
            {data.top_suppliers.map((s) => (
              <div key={s.supplier} className="flex items-center justify-between text-sm border-b border-border/60 py-1.5">
                <span>{s.supplier}</span>
                <span className="text-teal">€{s.total.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded border border-border bg-panel p-4">
          <h2 className="text-sm font-semibold mb-3">Top Categories</h2>
          <div className="flex flex-col gap-2">
            {data.top_categories.map((c) => (
              <div key={c.category} className="flex items-center justify-between text-sm border-b border-border/60 py-1.5">
                <span>{c.category}</span>
                <span className="text-amber">{c.percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
