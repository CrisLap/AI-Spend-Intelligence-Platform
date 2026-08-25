import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, Upload, X } from "lucide-react";
import { documents } from "../api";
import { useToast } from "../context/ToastContext";
import ConfirmDialog from "../components/ConfirmDialog";
import { SkeletonTable } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import TableScroll from "../components/TableScroll";
import Card from "../components/Card";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Doc = { id: number; original_name: string; doc_type: string; status: string; created_at: string; };
type SortBy = "name" | "status" | "date";
type SortDir = "asc" | "desc";

const PAGE_SIZE = 50;
const ALLOWED_EXTENSIONS = [".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg"];
const MAX_UPLOAD_MB = 50;
const SEARCH_DEBOUNCE_MS = 400;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Documents() {
  const { t } = useTranslation(["documents", "common"]);
  useDocumentTitle(t("documents:title"));
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get("status") || "";
  const sortBy = (searchParams.get("sortBy") as SortBy) || "date";
  const sortDir = (searchParams.get("sortDir") as SortDir) || "desc";
  const urlSearch = searchParams.get("q") || "";

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [list, setList] = useState<Doc[]>([]);
  const [stage, setStage] = useState<"idle" | "uploading" | "processing">("idle");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Doc | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    documents.list(0, PAGE_SIZE, { search: urlSearch, status: status || undefined, sortBy, sortDir })
      .then((res: Doc[]) => { setList(res); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => setError(err.message))
      .finally(() => setLoading(false));
  }
  useEffect(load, [urlSearch, status, sortBy, sortDir]);

  // Debounce the search box: update the URL (and thus trigger a reload)
  // only after the user pauses typing, not on every keystroke.
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

  function toggleSort(column: SortBy) {
    if (sortBy === column) {
      updateParam("sortDir", sortDir === "asc" ? "desc" : "asc");
    } else {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("sortBy", column);
        next.set("sortDir", "asc");
        return next;
      });
    }
  }

  function loadMore() {
    setLoadingMore(true);
    documents.list(list.length, PAGE_SIZE, { search: urlSearch, status: status || undefined, sortBy, sortDir })
      .then((res: Doc[]) => { setList((prev) => [...prev, ...res]); setHasMore(res.length === PAGE_SIZE); })
      .catch((err: any) => showToast(err.message, "error"))
      .finally(() => setLoadingMore(false));
  }

  function validateFile(file: File): string | null {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) return t("documents:dropzone.invalidFileType");
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return t("documents:dropzone.fileTooLarge", { maxMb: MAX_UPLOAD_MB });
    return null;
  }

  function pickFile(file: File | undefined | null) {
    if (!file) return;
    const err = validateFile(file);
    if (err) { setFileError(err); setSelectedFile(null); return; }
    setFileError("");
    setSelectedFile(file);
  }

  async function handleUpload() {
    if (!selectedFile) return;
    setStage("uploading");
    try {
      const doc = await documents.upload(selectedFile);
      setStage("processing");
      await documents.process(doc.id);
      load();
      setSelectedFile(null);
    } catch (err: any) { showToast(err.message, "error"); }
    finally { setStage("idle"); if (fileRef.current) fileRef.current.value = ""; }
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    documents.delete(id).then(load).catch((err: any) => showToast(err.message, "error"));
  }

  const uploading = stage !== "idle";

  function SortHeader({ column, labelKey }: { column: SortBy; labelKey: string }) {
    const active = sortBy === column;
    return (
      <th className="p-3">
        <button
          type="button"
          onClick={() => toggleSort(column)}
          aria-label={t("documents:sortAria", { column: t(labelKey) })}
          className={`flex items-center gap-1 uppercase tracking-wide ${active ? "text-teal" : ""}`}
        >
          {t(labelKey)}
          {active && (sortDir === "asc" ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />)}
        </button>
      </th>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-page-title font-bold">{t("documents:title")}</h1>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          pickFile(e.dataTransfer.files?.[0]);
        }}
        className={`rounded-2xl border-2 border-dashed bg-panel backdrop-blur-md p-4 flex flex-col gap-3 transition-colors ${dragActive ? "border-teal bg-teal/5" : "border-border"}`}
      >
        {!selectedFile ? (
          <label className="flex flex-col items-center gap-1 py-4 cursor-pointer text-center">
            <Upload size={22} className="text-muted" aria-hidden="true" />
            <span className="text-sm text-parchment">{t("documents:dropzone.hint")}</span>
            <span className="text-xs text-teal">{t("documents:dropzone.orClick")}</span>
            <span className="text-xs text-muted mt-1">{t("documents:dropzone.allowedTypes", { maxMb: MAX_UPLOAD_MB })}</span>
            <input
              ref={fileRef}
              type="file"
              accept={ALLOWED_EXTENSIONS.join(",")}
              className="sr-only"
              onChange={(e) => pickFile(e.target.files?.[0])}
            />
          </label>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm text-parchment truncate">{selectedFile.name}</span>
              <span className="text-xs text-muted shrink-0">{formatBytes(selectedFile.size)}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!uploading && (
                <button
                  type="button"
                  onClick={() => { setSelectedFile(null); if (fileRef.current) fileRef.current.value = ""; }}
                  aria-label={t("documents:dropzone.remove")}
                  className="text-muted hover:text-danger"
                >
                  <X size={16} aria-hidden="true" />
                </button>
              )}
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="rounded-full bg-teal px-4 py-1.5 text-xs font-semibold text-surface disabled:opacity-50"
              >
                {uploading ? t(`documents:stage${stage === "uploading" ? "Uploading" : "Processing"}`) : t("documents:uploadAndAnalyze")}
              </button>
            </div>
          </div>
        )}
        {uploading && (
          <div className="h-1 w-full overflow-hidden rounded bg-panel-2">
            <div className="h-full w-1/3 rounded bg-teal animate-[indeterminate_1.2s_ease-in-out_infinite]" />
          </div>
        )}
        {fileError && <p className="text-xs text-danger">{fileError}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder={t("common:search")}
          aria-label={t("common:search")}
          className="flex-1 min-w-[180px] rounded-full border border-border bg-panel-2 px-3 py-1.5 text-sm text-parchment placeholder:text-muted focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
        />
        <select
          value={status}
          onChange={(e) => updateParam("status", e.target.value)}
          className="rounded-full border border-border bg-panel-2 px-2 py-1.5 text-sm text-parchment focus:outline-none focus:border-teal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal"
        >
          <option value="">{t("documents:statusOptions.all")}</option>
          <option value="uploaded">{t("documents:statusOptions.uploaded")}</option>
          <option value="processing">{t("documents:statusOptions.processing")}</option>
          <option value="parsed">{t("documents:statusOptions.parsed")}</option>
          <option value="failed">{t("documents:statusOptions.failed")}</option>
          <option value="classified">{t("documents:statusOptions.classified")}</option>
        </select>
      </div>

      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonTable cols={5} />
      ) : (
        <Card padding="none" className="overflow-hidden">
          <TableScroll>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
                <SortHeader column="name" labelKey="documents:table.name" />
                <th className="p-3">{t("documents:table.type")}</th>
                <SortHeader column="status" labelKey="documents:table.status" />
                <SortHeader column="date" labelKey="documents:table.date" />
                <th className="p-3"></th>
              </tr></thead>
              <tbody>
                {list.map((d) => (
                  <tr key={d.id} className="border-b border-border/60 hover:bg-panel-2/50 cursor-pointer" onClick={() => navigate(`/documents/${d.id}`)}>
                    <td className="p-3">{d.original_name}</td>
                    <td className="p-3 text-muted">{d.doc_type}</td>
                    <td className="p-3"><span className={`text-xs px-2 py-0.5 rounded-full ${d.status === "classified" ? "bg-ok/10 text-ok" : d.status === "failed" ? "bg-danger/10 text-danger" : "bg-amber/10 text-amber"}`}>{d.status}</span></td>
                    <td className="p-3 text-muted text-xs">{new Date(d.created_at).toLocaleDateString()}</td>
                    <td className="p-3 text-right">
                      <button onClick={(e) => { e.stopPropagation(); setDeleteTarget(d); }} className="text-xs text-danger hover:underline">{t("documents:delete")}</button>
                    </td>
                  </tr>
                ))}
                {list.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted text-sm">{t("documents:empty")}</td></tr>}
              </tbody>
            </table>
          </TableScroll>
        </Card>
      )}
      {hasMore && (
        <button onClick={loadMore} disabled={loadingMore} className="self-center rounded-full border border-border px-4 py-1.5 text-xs text-muted hover:text-parchment disabled:opacity-50">
          {loadingMore ? t("common:loading") : t("common:loadMore")}
        </button>
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("documents:deleteDialog.title")}
        message={deleteTarget ? t("documents:deleteDialog.message", { name: deleteTarget.original_name }) : ""}
        confirmLabel={t("documents:deleteDialog.confirm")}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
