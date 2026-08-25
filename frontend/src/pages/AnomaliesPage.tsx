import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { anomalies } from "../api";
import { useToast } from "../context/ToastContext";
import { SkeletonCard } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Anom = {
  id: number; description: string; unit_price: number; category: string;
  supplier: string | null; zscore: number; reason: string; resolved: boolean;
};
type SortBy = "zscore" | "price";

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 400;

export default function AnomaliesPage() {
  const { t } = useTranslation(["anomalies", "common"]);
  useDocumentTitle(t("title"));
  const [searchParams, setSearchParams] = useSearchParams();
  const sortBy = (searchParams.get("sortBy") as SortBy) || "zscore";
  const includeResolved = searchParams.get("includeResolved") === "1";
  const urlSearch = searchParams.get("q") || "";

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [list, setList] = useState<Anom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    anomalies.list(0, PAGE_SIZE, { search: urlSearch, sortBy, includeResolved })
      .then((res: Anom[]) => { setList(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, [urlSearch, sortBy, includeResolved]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== urlSearch) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (searchInput) next.set("q", searchInput); else next.delete("q");
          return next;
        });
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  function updateParam(key: string, value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value); else next.delete(key);
      return next;
    });
  }

  function loadMore() {
    setLoadingMore(true);
    anomalies.list(list.length, PAGE_SIZE, { search: urlSearch, sortBy, includeResolved })
      .then((res: Anom[]) => { setList((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => showToast(err.message, "error"))
      .finally(() => setLoadingMore(false));
  }

  async function toggleResolve(item: Anom) {
    const nextResolved = !item.resolved;
    setPendingIds((prev) => new Set(prev).add(item.id));
    try {
      await anomalies.resolve(item.id, nextResolved);
      showToast(t(nextResolved ? "resolvedToast" : "unresolvedToast"), "success");
      if (!includeResolved && nextResolved) {
        setList((prev) => prev.filter((a) => a.id !== item.id));
      } else {
        setList((prev) => prev.map((a) => (a.id === item.id ? { ...a, resolved: nextResolved } : a)));
      }
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setPendingIds((prev) => { const next = new Set(prev); next.delete(item.id); return next; });
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-page-title font-bold">{t("title")}</h1>
      <p className="text-xs text-muted">{t("description")}</p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder={t("common:search")}
          aria-label={t("common:search")}
          className="flex-1 min-w-[180px] rounded-full border border-border bg-panel-2 px-3 py-1.5 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
        />
        <select
          value={sortBy}
          onChange={(e) => updateParam("sortBy", e.target.value)}
          className="rounded-full border border-border bg-panel-2 px-2 py-1.5 text-sm text-parchment focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
        >
          <option value="zscore">{t("sortBy.zscore")}</option>
          <option value="price">{t("sortBy.price")}</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <input
            type="checkbox"
            checked={includeResolved}
            onChange={(e) => updateParam("includeResolved", e.target.checked ? "1" : "")}
          />
          {t("common:showResolved")}
        </label>
      </div>

      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonCard />
      ) : (
        <>
          {list.length === 0 && <p className="text-ok text-sm">{urlSearch ? t("noResults") : t("empty")}</p>}
          <div className="flex flex-col gap-2">
            {list.map((a) => (
              <div key={a.id} className={`rounded-2xl border p-3 backdrop-blur-md ${a.resolved ? "border-border bg-panel shadow-glass" : "border-danger/30 bg-danger/5"}`}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{a.description}</p>
                  <div className="flex items-center gap-2 shrink-0">
                    {a.resolved && <span className="text-xs bg-ok/10 text-ok px-2 py-0.5 rounded-full">{t("common:resolved")}</span>}
                    <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded-full">{t("zscore", { value: a.zscore })}</span>
                  </div>
                </div>
                <div className="flex gap-3 mt-1 text-xs text-muted">
                  <span>{t("supplier")} {a.supplier || t("notAvailable")}</span>
                  <span>{t("price")} €{a.unit_price.toFixed(2)}</span>
                  <span>{t("category")} {a.category || t("notAvailable")}</span>
                </div>
                <p className="text-xs text-muted mt-1">{a.reason}</p>
                <button
                  onClick={() => toggleResolve(a)}
                  disabled={pendingIds.has(a.id)}
                  className="mt-2 text-xs text-teal hover:underline disabled:opacity-50"
                >
                  {t(a.resolved ? "common:unresolve" : "common:resolve")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
      {hasMore && (
        <button onClick={loadMore} disabled={loadingMore} className="self-center rounded-full border border-border px-4 py-1.5 text-xs text-muted hover:text-parchment disabled:opacity-50">
          {loadingMore ? t("common:loading") : t("common:loadMore")}
        </button>
      )}
    </div>
  );
}
