import { useTranslation } from "react-i18next";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useTranslation("common");

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-surface/70 px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div className="w-full max-w-sm rounded-xl border border-border bg-panel p-5">
        <h2 id="confirm-dialog-title" className="text-sm font-medium text-parchment">{title}</h2>
        <p className="mt-2 text-sm text-secondary">{message}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-border bg-panel-2 px-3 py-2 text-sm text-parchment transition-colors hover:bg-panel-2/70"
          >
            {cancelLabel ?? t("actions.cancel")}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-danger px-3 py-2 text-sm font-medium text-white transition hover:brightness-110 active:scale-[0.98]"
          >
            {confirmLabel ?? t("actions.confirm")}
          </button>
        </div>
      </div>
    </div>
  );
}
