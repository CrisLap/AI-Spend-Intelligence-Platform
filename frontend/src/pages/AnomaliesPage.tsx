import { useEffect, useState } from "react";
import { anomalies } from "../api";

type Anom = { id: number; description: string; unit_price: number; category: string; supplier: string | null; zscore: number; reason: string; };

const PAGE_SIZE = 50;

export default function AnomaliesPage() {
  const [list, setList] = useState<Anom[]>([]);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    anomalies.list(0, PAGE_SIZE)
      .then((res: Anom[]) => { setList(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message));
  }, []);

  function loadMore() {
    setLoadingMore(true);
    anomalies.list(list.length, PAGE_SIZE)
      .then((res: Anom[]) => { setList((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => alert(err.message))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">Detected Anomalies</h1>
      <p className="text-xs text-muted">Spend items that deviate significantly from their category average.</p>
      {error && <p className="text-danger text-sm">{error}</p>}
      {!error && list.length === 0 && <p className="text-ok text-sm">No anomalies detected.</p>}
      <div className="flex flex-col gap-2">
        {list.map((a) => (
          <div key={a.id} className="rounded border border-danger/30 bg-danger/5 p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">{a.description}</p>
              <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded">z-score: {a.zscore}</span>
            </div>
            <div className="flex gap-3 mt-1 text-xs text-muted">
              <span>Supplier: {a.supplier || "N/A"}</span>
              <span>Price: €{a.unit_price.toFixed(2)}</span>
              <span>Category: {a.category || "N/A"}</span>
            </div>
            <p className="text-xs text-muted mt-1">{a.reason}</p>
          </div>
        ))}
      </div>
      {hasMore && (
        <button onClick={loadMore} disabled={loadingMore} className="self-center rounded border border-border px-4 py-1.5 text-xs text-muted hover:text-parchment disabled:opacity-50">
          {loadingMore ? "Loading..." : "Load more"}
        </button>
      )}
    </div>
  );
}
