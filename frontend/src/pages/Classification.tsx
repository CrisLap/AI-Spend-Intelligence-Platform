import { useState } from "react";
import { classification as clsApi } from "../api";

export default function Classification() {
  const [input, setInput] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [error, setError] = useState("");

  async function handle() {
    const descs = input.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!descs.length) return;
    setError("");
    try {
      const res = await clsApi.classify(descs);
      setResults(res.results);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="flex flex-col gap-4 max-w-2xl">
      <h1 className="text-xl font-bold">Spend Classification</h1>
      <p className="text-xs text-muted">Enter one or more descriptions (one per line) to classify them automatically.</p>
      <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={6} placeholder="HP LaserJet Toner&#10;Legal consulting&#10;Flight New York-London" className="rounded border border-border bg-panel-2 px-3 py-2 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal" />
      <button onClick={handle} className="self-start rounded bg-teal px-4 py-1.5 text-xs font-semibold text-surface">Classify</button>
      {error && <p className="text-xs text-danger">{error}</p>}
      {results && (
        <div className="rounded border border-border bg-panel overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
              <th className="p-3">Description</th><th className="p-3">Category</th><th className="p-3">UNSPSC</th><th className="p-3">Confidence</th><th className="p-3">Method</th>
            </tr></thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} className="border-b border-border/60">
                  <td className="p-3">{r.description}</td>
                  <td className="p-3"><span className="text-xs bg-teal/10 text-teal px-2 py-0.5 rounded">{r.category}</span></td>
                  <td className="p-3 text-xs text-muted">{r.unspsc || "-"}</td>
                  <td className="p-3">{(r.confidence * 100).toFixed(0)}%</td>
                  <td className="p-3 text-xs text-muted">{r.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
