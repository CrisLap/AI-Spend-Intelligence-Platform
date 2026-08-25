import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { duplicates } from "../api";
import { useToast } from "../context/ToastContext";
import { SkeletonCard } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type DupGroup = {
  id: number; reason: string; similarity: number; resolved: boolean;
  items: { id: number; description: string; supplier: string | null; total: number; invoice_number: string | null }[];
};

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 400;

export default function DuplicatesPage() {
  const { t } = useTranslation(["duplicates", "common"]);
  useDocumentTitle(t("title"));
  const [searchParams, setSearchParams] = useSearchParams();
  const includeResolved = searchParams.get("includeResolved") === "1";
  const urlSearch = searchParams.get("q") || "";

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [groups, setGroups] = useState<DupGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set());
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    duplicates.list(0, PAGE_SIZE, { search: urlSearch, includeResolved })
      .then((res: DupGroup[]) => { setGroups(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, [urlSearch, includeResolved]);

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

  function loadMore() {
    setLoadingMore(true);
    duplicates.list(groups.length, PAGE_SIZE, { search: urlSearch, includeResolved })
      .then((res: DupGroup[]) => { setGroups((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => showToast(err.message, "error"))
      .finally(() => setLoadingMore(false));
  }

  async function toggleResolve(group: DupGroup) {
    const nextResolved = !group.resolved;
    setPendingIds((prev) => new Set(prev).add(group.id));
    try {
      await duplicates.resolve(group.id, nextResolved);
      showToast(t(nextResolved ? "resolvedToast" : "unresolvedToast"), "success");
      if (!includeResolved && nextResolved) {
        setGroups((prev) => prev.filter((g) => g.id !== group.id));
      } else {
        setGroups((prev) => prev.map((g) => (g.id === group.id ? { ...g, resolved: nextResolved } : g)));
      }
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setPendingIds((prev) => { const next = new Set(prev); next.delete(group.id); return next; });
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-page-title font-bold">{t("title")}</h1>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder={t("common:search")}
          aria-label={t("common:search")}
          className="flex-1 min-w-[180px] rounded-full border border-border bg-panel-2 px-3 py-1.5 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
        />
        <label className="flex items-center gap-1.5 text-xs text-muted">
          <input
            type="checkbox"
            checked={includeResolved}
            onChange={(e) => setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              if (e.target.checked) next.set("includeResolved", "1"); else next.delete("includeResolved");
              return next;
            })}
          />
          {t("common:showResolved")}
        </label>
      </div>

      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonCard />
      ) : (
        <>
          {!error && groups.length === 0 && <p className="text-ok text-sm">{urlSearch ? t("noResults") : t("empty")}</p>}
          <div className="flex flex-col gap-4">
            {groups.map((g) => (
              <div key={g.id} className={`rounded-2xl border p-3 backdrop-blur-md ${g.resolved ? "border-border bg-panel shadow-glass" : "border-amber/30 bg-amber/5"}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs bg-amber/10 text-amber px-2 py-0.5 rounded-full">{t("group")}</span>
                  <span className="text-xs text-muted">{g.reason}</span>
                  {g.resolved && <span className="text-xs bg-ok/10 text-ok px-2 py-0.5 rounded-full">{t("common:resolved")}</span>}
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
                <button
                  onClick={() => toggleResolve(g)}
                  disabled={pendingIds.has(g.id)}
                  className="mt-2 text-xs text-teal hover:underline disabled:opacity-50"
                >
                  {t(g.resolved ? "common:unresolve" : "common:resolve")}
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
