import { useEffect, useState } from "react";
import { duplicates } from "../api";

type DupGroup = { id: number; reason: string; similarity: number; items: { id: number; description: string; supplier: string | null; total: number; invoice_number: string | null }[] };

const PAGE_SIZE = 50;

export default function DuplicatesPage() {
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    duplicates.list(0, PAGE_SIZE)
      .then((res: DupGroup[]) => { setGroups(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message));
  }, []);

  function loadMore() {
    setLoadingMore(true);
    duplicates.list(groups.length, PAGE_SIZE)
      .then((res: DupGroup[]) => { setGroups((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => alert(err.message))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">Detected Duplicates</h1>
      {error && <p className="text-danger text-sm">{error}</p>}
      {!error && groups.length === 0 && <p className="text-ok text-sm">No duplicates detected.</p>}
      <div className="flex flex-col gap-4">
        {groups.map((g) => (
          <div key={g.id} className="rounded border border-amber/30 bg-amber/5 p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs bg-amber/10 text-amber px-2 py-0.5 rounded">Duplicate group</span>
              <span className="text-xs text-muted">{g.reason}</span>
            </div>
            <div className="flex flex-col gap-1">
              {g.items.map((item) => (
                <div key={item.id} className="flex items-center justify-between text-sm border-b border-border/30 py-1">
                  <span>{item.description}</span>
                  <div className="flex gap-3 text-xs text-muted">
                    {item.supplier && <span>{item.supplier}</span>}
                    <span>€{item.total.toFixed(2)}</span>
                    {item.invoice_number && <span>{item.invoice_number}</span>}
                  </div>
                </div>
              ))}
            </div>
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
