import { useState } from "react";
import { search } from "../api";

export default function SemanticSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [error, setError] = useState("");

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setError("");
    try {
      const res = await search.semantic(query);
      setResults(res.results);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <h1 className="text-xl font-bold">Semantic Search</h1>
      <p className="text-xs text-muted">Search across all documents and spend items using natural language.</p>
      <form onSubmit={handle} className="flex gap-2">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. Find all HP toner invoices" className="flex-1 rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
        <button type="submit" className="rounded bg-teal px-4 py-2 text-xs font-semibold text-surface">Search</button>
      </form>
      {error && <p className="text-xs text-danger">{error}</p>}
      {results && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted">{results.length} results</p>
          {results.map((r, i) => (
            <div key={i} className="rounded border border-border bg-panel p-3">
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
