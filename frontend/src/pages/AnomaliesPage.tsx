import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { anomalies } from "../api";
import { useToast } from "../context/ToastContext";
import { SkeletonCard } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Anom = { id: number; description: string; unit_price: number; category: string; supplier: string | null; zscore: number; reason: string; };

const PAGE_SIZE = 50;

export default function AnomaliesPage() {
  const { t } = useTranslation(["anomalies", "common"]);
  useDocumentTitle(t("title"));
  const [list, setList] = useState<Anom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    anomalies.list(0, PAGE_SIZE)
      .then((res: Anom[]) => { setList(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, []);

  function loadMore() {
    setLoadingMore(true);
    anomalies.list(list.length, PAGE_SIZE)
      .then((res: Anom[]) => { setList((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => showToast(err.message, "error"))
      .finally(() => setLoadingMore(false));
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">{t("title")}</h1>
      <p className="text-xs text-muted">{t("description")}</p>
      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonCard />
      ) : (
        <>
          {!error && list.length === 0 && <p className="text-ok text-sm">{t("empty")}</p>}
          <div className="flex flex-col gap-2">
            {list.map((a) => (
              <div key={a.id} className="rounded border border-danger/30 bg-danger/5 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium">{a.description}</p>
                  <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded">{t("zscore", { value: a.zscore })}</span>
                </div>
                <div className="flex gap-3 mt-1 text-xs text-muted">
                  <span>{t("supplier")} {a.supplier || t("notAvailable")}</span>
                  <span>{t("price")} €{a.unit_price.toFixed(2)}</span>
                  <span>{t("category")} {a.category || t("notAvailable")}</span>
                </div>
                <p className="text-xs text-muted mt-1">{a.reason}</p>
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
