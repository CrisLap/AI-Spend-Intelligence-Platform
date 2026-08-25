import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { classification as clsApi } from "../api";
import TableScroll from "../components/TableScroll";
import Card from "../components/Card";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function Classification() {
  const { t } = useTranslation(["classification", "categories"]);
  useDocumentTitle(t("title"));
  const inputId = useId();
  const [input, setInput] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [error, setError] = useState("");
  const [classifying, setClassifying] = useState(false);

  async function handle() {
    if (classifying) return;
    const descs = input.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!descs.length) return;
    setError("");
    setClassifying(true);
    try {
      const res = await clsApi.classify(descs);
      setResults(res.results);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setClassifying(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <h1 className="text-page-title font-bold">{t("title")}</h1>
      <p className="text-xs text-muted">{t("description")}</p>
      <label htmlFor={inputId} className="sr-only">{t("title")}</label>
      <textarea id={inputId} value={input} onChange={(e) => setInput(e.target.value)} rows={6} placeholder={t("placeholder")} className="rounded-2xl border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
      <button onClick={handle} disabled={classifying} className="self-start rounded-full bg-teal px-4 py-1.5 text-xs font-semibold text-surface disabled:opacity-50">
        {classifying ? t("classifying") : t("classify")}
      </button>
      {error && <p className="text-xs text-danger">{error}</p>}
      {results && (
        <Card padding="none" className="overflow-hidden">
          <TableScroll>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
                <th className="p-3">{t("table.description")}</th><th className="p-3">{t("table.category")}</th><th className="p-3">{t("table.unspsc")}</th><th className="p-3">{t("table.confidence")}</th><th className="p-3">{t("table.method")}</th>
              </tr></thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-b border-border/60">
                    <td className="p-3">{r.description}</td>
                    <td className="p-3"><span className="text-xs bg-teal/10 text-teal px-2 py-0.5 rounded-full">{t(r.category, { ns: "categories", defaultValue: r.category })}</span></td>
                    <td className="p-3 text-xs text-muted">{r.unspsc || "-"}</td>
                    <td className="p-3">{(r.confidence * 100).toFixed(0)}%</td>
                    <td className="p-3 text-xs text-muted">{r.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </Card>
      )}
    </div>
  );
}
