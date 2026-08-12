import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { duplicates } from "../api";
import { useToast } from "../context/ToastContext";
import { SkeletonCard } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type DupGroup = { id: number; reason: string; similarity: number; items: { id: number; description: string; supplier: string | null; total: number; invoice_number: string | null }[] };

const PAGE_SIZE = 50;

export default function DuplicatesPage() {
  const { t } = useTranslation(["duplicates", "common"]);
  useDocumentTitle(t("title"));
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    duplicates.list(0, PAGE_SIZE)
      .then((res: DupGroup[]) => { setGroups(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  function loadMore() {
    setLoadingMore(true);
    duplicates.list(groups.length, PAGE_SIZE)
      .then((res: DupGroup[]) => { setGroups((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => showToast(err.message, "error"))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">{t("title")}</h1>
      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonCard />
      ) : (
        <>
          {!error && groups.length === 0 && <p className="text-ok text-sm">{t("empty")}</p>}
          <div className="flex flex-col gap-4">
            {groups.map((g) => (
              <div key={g.id} className="rounded border border-amber/30 bg-amber/5 p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs bg-amber/10 text-amber px-2 py-0.5 rounded">{t("group")}</span>
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
        </>
      )}
      {hasMore && (
        <button onClick={loadMore} disabled={loadingMore} className="self-center rounded border border-border px-4 py-1.5 text-xs text-muted hover:text-parchment disabled:opacity-50">
          {loadingMore ? t("common:loading") : t("common:loadMore")}
        </button>
      )}
    </div>
  );
}
