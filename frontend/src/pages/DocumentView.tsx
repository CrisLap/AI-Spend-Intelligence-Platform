import { Fragment, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { documents, classification, feedback } from "../api";
import { useToast } from "../context/ToastContext";
import { SkeletonTable } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import TableScroll from "../components/TableScroll";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type Item = {
  id: number; description: string; quantity: number; unit_price: number; total: number; supplier: string | null;
  category_unspsc: string | null; category_label: string | null; confidence: number | null;
  is_anomaly: boolean; anomaly_reason: string | null;
};
type Doc = { id: number; original_name: string; status: string; doc_type: string; line_items: Item[]; };

// Kept in sync with UNSPSC_TAXONOMY / UNSPSC_CODES in backend/app/services/classifier.py.
// These are the canonical wire-format values sent to the API - only their
// displayed label is translated, via the categories.json namespace (shared
// with Classification.tsx, which shows the same taxonomy on results rows).
const CATEGORIES = [
  "Office Equipment & Supplies", "Computer Equipment & Accessories", "Networking Equipment",
  "Software & Digital Licenses", "Building & Facility Maintenance", "Professional & Consulting Services",
  "Travel & Transportation", "Raw Materials & Components", "Utilities & Energy", "Medical & Healthcare",
  "Marketing & Advertising", "Furniture & Furnishings", "HR & Personnel Services",
];

export default function DocumentView() {
  const { t } = useTranslation(["documentView", "categories", "common"]);
  const { id } = useParams();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<Doc | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");
  const [pendingCategory, setPendingCategory] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [feedbackForId, setFeedbackForId] = useState<number | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [feedbackSentId, setFeedbackSentId] = useState<number | null>(null);
  const { showToast } = useToast();
  useDocumentTitle(doc?.original_name || t("common:loading"));

  function load() {
    setError("");
    documents.get(Number(id)).then((d) => { setDoc(d); setItems(d.line_items); }).catch((err: any) => setError(err.message));
  }
  useEffect(load, [id]);

  if (error) return <InlineError message={error} onRetry={load} />;
  if (!doc) return <SkeletonTable cols={10} />;

  async function saveCategory(item: Item) {
    const newCategory = pendingCategory[item.id];
    if (!newCategory || newCategory === item.category_label) return;
    setSavingId(item.id);
    try {
      const updated = await classification.updateItem(item.id, { category_label: newCategory });
      setItems((prev) => prev.map((it) => (it.id === item.id ? { ...it, ...updated } : it)));
      setPendingCategory((prev) => { const next = { ...prev }; delete next[item.id]; return next; });
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setSavingId(null);
    }
  }

  async function submitFeedback(item: Item) {
    if (!feedbackComment.trim()) return;
    try {
      await feedback.create({
        document_id: doc!.id,
        line_item_id: item.id,
        original_category: item.category_label || undefined,
        corrected_category: pendingCategory[item.id] || item.category_label || "",
        comment: feedbackComment.trim(),
      });
      setFeedbackSentId(item.id);
      setFeedbackForId(null);
      setFeedbackComment("");
    } catch (err: any) {
      showToast(err.message, "error");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate("/documents")} className="text-xs text-muted hover:text-parchment">{t("back")}</button>
        <h1 className="text-xl font-bold">{doc.original_name}</h1>
        <span className={`text-xs px-2 py-0.5 rounded ${doc.status === "classified" ? "bg-ok/10 text-ok" : "bg-amber/10 text-amber"}`}>{doc.status}</span>
      </div>
      <div className="rounded border border-border bg-panel overflow-hidden">
        <TableScroll>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
            <th className="p-3">{t("table.description")}</th><th className="p-3">{t("table.qty")}</th><th className="p-3">{t("table.price")}</th><th className="p-3">{t("table.total")}</th><th className="p-3">{t("table.supplier")}</th><th className="p-3">{t("table.category")}</th><th className="p-3">{t("table.unspsc")}</th><th className="p-3">{t("table.confidence")}</th><th className="p-3">{t("table.anomaly")}</th><th className="p-3"></th>
          </tr></thead>
          <tbody>
            {items.map((item) => (
              <Fragment key={item.id}>
                <tr className="border-b border-border/60 hover:bg-panel-2/30">
                  <td className="p-3">{item.description}</td>
                  <td className="p-3">{item.quantity}</td>
                  <td className="p-3">€{item.unit_price.toFixed(2)}</td>
                  <td className="p-3">€{item.total.toFixed(2)}</td>
                  <td className="p-3 text-muted">{item.supplier || "-"}</td>
                  <td className="p-3">
                    <div className="flex items-center gap-1">
                      <select
                        value={pendingCategory[item.id] ?? item.category_label ?? ""}
                        onChange={(e) => setPendingCategory((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        className="text-xs bg-teal/10 text-teal rounded px-1.5 py-0.5 border-0 focus:outline-none"
                      >
                        {!item.category_label && <option value="">{t("notAvailable")}</option>}
                        {CATEGORIES.map((c) => <option key={c} value={c}>{t(c, { ns: "categories", defaultValue: c })}</option>)}
                      </select>
                      {pendingCategory[item.id] && pendingCategory[item.id] !== item.category_label && (
                        <button
                          onClick={() => saveCategory(item)}
                          disabled={savingId === item.id}
                          className="text-xs text-ok hover:underline disabled:opacity-50"
                        >
                          {savingId === item.id ? "..." : t("save")}
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="p-3 text-xs text-muted">{item.category_unspsc || "-"}</td>
                  <td className="p-3 text-xs text-muted">{item.confidence ? `${(item.confidence * 100).toFixed(0)}%` : "-"}</td>
                  <td className="p-3">
                    {item.is_anomaly ? (
                      <span className="text-xs bg-danger/10 text-danger px-2 py-0.5 rounded" title={item.anomaly_reason || ""}>{t("anomalyBadge")}</span>
                    ) : <span className="text-xs text-ok">{t("okBadge")}</span>}
                  </td>
                  <td className="p-3 text-right whitespace-nowrap">
                    {feedbackSentId === item.id ? (
                      <span className="text-xs text-ok">{t("feedbackSent")}</span>
                    ) : (
                      <button
                        onClick={() => setFeedbackForId(feedbackForId === item.id ? null : item.id)}
                        className="text-xs text-muted hover:text-amber"
                      >
                        {t("notCorrect")}
                      </button>
                    )}
                  </td>
                </tr>
                {feedbackForId === item.id && (
                  <tr className="border-b border-border/60 bg-panel-2/40">
                    <td colSpan={10} className="p-3">
                      <div className="flex items-center gap-2">
                        <input
                          value={feedbackComment}
                          onChange={(e) => setFeedbackComment(e.target.value)}
                          placeholder={t("feedbackPlaceholder")}
                          aria-label={t("feedbackPlaceholder")}
                          className="flex-1 rounded border border-border bg-panel px-2 py-1 text-xs text-parchment placeholder:text-muted focus:outline-none focus:border-teal"
                        />
                        <button onClick={() => submitFeedback(item)} className="text-xs rounded bg-amber px-3 py-1 font-semibold text-surface">
                          {t("submitFeedback")}
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {items.length === 0 && <tr><td colSpan={10} className="p-6 text-center text-muted">{t("empty")}</td></tr>}
          </tbody>
        </table>
        </TableScroll>
      </div>
    </div>
  );
}
