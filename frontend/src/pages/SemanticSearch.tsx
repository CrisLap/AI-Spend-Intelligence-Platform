import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { search } from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function SemanticSearch() {
  const { t } = useTranslation("search");
  useDocumentTitle(t("title"));
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") || "";
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<any[] | null>(null);
  const [error, setError] = useState("");

  async function runSearch(q: string) {
    if (!q.trim()) return;
    setError("");
    try {
      const res = await search.semantic(q);
      setResults(res.results);
    } catch (err: any) {
      setError(err.message);
    }
  }

  // Drill-down from Dashboard's Top Suppliers/Top Categories links here
  // with ?q=<name> - run it automatically instead of making the user
  // retype and resubmit what they just clicked.
  useEffect(() => {
    if (initialQuery) runSearch(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    await runSearch(query);
  }

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <h1 className="text-page-title font-bold">{t("title")}</h1>
      <p className="text-xs text-muted">{t("description")}</p>
      <form onSubmit={handle} className="flex gap-2">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("placeholder")} aria-label={t("title")} className="flex-1 rounded-full border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal" />
        <button type="submit" className="rounded-full bg-teal px-4 py-2 text-xs font-semibold text-surface">{t("search")}</button>
      </form>
      {error && <p className="text-xs text-danger">{error}</p>}
      {results && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted">{t("resultsCount", { count: results.length })}</p>
          {results.map((r, i) => (
            <div key={i} className="rounded-2xl border border-border bg-panel backdrop-blur-md shadow-glass p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm">{r.description}</p>
                <span className="text-xs text-muted">score {r.score}</span>
              </div>
              <div className="flex gap-3 mt-1 text-xs text-muted">
                {r.supplier && <span>{r.supplier}</span>}
                {r.category && <span className="text-teal">{r.category}</span>}
                <span>€{r.total}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
