import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useToast, type ToastVariant } from "../context/ToastContext";

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  info: "bg-panel-2 border-border text-parchment",
  success: "bg-ok/10 border-ok/30 text-ok",
  error: "bg-danger/10 border-danger/30 text-danger",
};

export default function ToastContainer() {
  const { t } = useTranslation("common");
  const { toasts, dismissToast } = useToast();

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`rounded-lg border px-3 py-2 text-sm flex items-start justify-between gap-2 ${VARIANT_CLASSES[toast.variant]}`}
        >
          <span className="flex-1">{toast.message}</span>
          <button
            onClick={() => dismissToast(toast.id)}
            aria-label={t("dismiss")}
            className="mt-0.5 opacity-60 transition-opacity hover:opacity-100"
          >
            <X size={14} strokeWidth={1.5} aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  );
}
