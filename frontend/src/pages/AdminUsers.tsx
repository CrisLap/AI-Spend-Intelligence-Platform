import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { users, classification } from "../api";
import { useToast } from "../context/ToastContext";
import ConfirmDialog from "../components/ConfirmDialog";
import { SkeletonTable } from "../components/Skeleton";
import InlineError from "../components/InlineError";
import TableScroll from "../components/TableScroll";
import Card from "../components/Card";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

type User = { id: number; email: string; full_name: string; role: string; is_active: boolean; created_at: string; };
type AuditEntry = { id: number; action: string; entity_type: string; entity_id: number | null; details: any; created_at: string; };

const ROLES = ["buyer", "finance", "admin"];

export default function AdminUsers() {
  const { t } = useTranslation("admin");
  useDocumentTitle(t("title"));
  const [list, setList] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [retrainMessage, setRetrainMessage] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  const { showToast } = useToast();

  function load() {
    setError("");
    setLoading(true);
    users.list().then(setList).catch((err: any) => setError(err.message)).finally(() => setLoading(false));
  }
  useEffect(load, []);

  function handleRoleChange(u: User, role: string) {
    users.updateRole(u.id, role)
      .then((updated: User) => setList((prev) => prev.map((x) => (x.id === u.id ? updated : x))))
      .catch((err: any) => showToast(err.message, "error"));
  }

  function confirmDelete() {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    users.delete(id).then(load).catch((err: any) => showToast(err.message, "error"));
  }

  function toggleAuditLog(u: User) {
    if (expandedId === u.id) { setExpandedId(null); return; }
    setExpandedId(u.id);
    setAuditLoading(true);
    users.auditLog(u.id).then(setAuditLog).catch((err: any) => showToast(err.message, "error")).finally(() => setAuditLoading(false));
  }

  async function handleRetrain() {
    setRetraining(true);
    setRetrainMessage("");
    try {
      const res = await classification.retrain();
      setRetrainMessage(res.message);
    } catch (err: any) {
      setRetrainMessage(err.message);
    } finally {
      setRetraining(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{t("title")}</h1>
        <div className="flex items-center gap-2">
          {retrainMessage && <span className="text-xs text-muted">{retrainMessage}</span>}
          <button onClick={handleRetrain} disabled={retraining} className="rounded-full bg-teal px-4 py-1.5 text-xs font-semibold text-surface disabled:opacity-50">
            {retraining ? t("retraining") : t("retrainButton")}
          </button>
        </div>
      </div>
      {error && <InlineError message={error} onRetry={load} />}
      {loading ? (
        <SkeletonTable cols={5} />
      ) : (
        <Card className="overflow-hidden">
          <TableScroll>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border bg-panel-2 text-left text-xs text-muted uppercase tracking-wide">
              <th className="p-3">{t("table.email")}</th><th className="p-3">{t("table.name")}</th><th className="p-3">{t("table.role")}</th><th className="p-3">{t("table.created")}</th><th className="p-3"></th>
            </tr></thead>
            <tbody>
              {list.map((u) => (
                <Fragment key={u.id}>
                  <tr className="border-b border-border/60 hover:bg-panel-2/30">
                    <td className="p-3">{u.email}</td>
                    <td className="p-3 text-muted">{u.full_name}</td>
                    <td className="p-3">
                      <select
                        value={u.role}
                        onChange={(e) => handleRoleChange(u, e.target.value)}
                        className="text-xs bg-teal/10 text-teal rounded-full px-1.5 py-0.5 border-0 focus:outline-none"
                      >
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className="p-3 text-muted text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td className="p-3 text-right whitespace-nowrap">
                      <button onClick={() => toggleAuditLog(u)} className="text-xs text-muted hover:text-parchment mr-3">
                        {expandedId === u.id ? t("hideLog") : t("auditLog")}
                      </button>
                      <button onClick={() => setDeleteTarget(u)} className="text-xs text-danger hover:underline">{t("delete")}</button>
                    </td>
                  </tr>
                  {expandedId === u.id && (
                    <tr className="border-b border-border/60 bg-panel-2/40">
                      <td colSpan={5} className="p-3">
                        {auditLoading ? (
                          <p className="text-xs text-muted">{t("loadingAuditLog")}</p>
                        ) : auditLog.length === 0 ? (
                          <p className="text-xs text-muted">{t("noAuditEntries")}</p>
                        ) : (
                          <div className="flex flex-col gap-1">
                            {auditLog.map((e) => (
                              <div key={e.id} className="flex items-center justify-between text-xs text-muted border-b border-border/30 py-1">
                                <span>{e.action} — {e.entity_type} {e.entity_id ?? ""}</span>
                                <span>{new Date(e.created_at).toLocaleString()}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {list.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted text-sm">{t("empty")}</td></tr>}
            </tbody>
          </table>
          </TableScroll>
        </Card>
      )}
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("deleteDialog.title")}
        message={deleteTarget ? t("deleteDialog.message", { email: deleteTarget.email }) : ""}
        confirmLabel={t("deleteDialog.confirm")}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
