import { useToast, type ToastVariant } from "../context/ToastContext";

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  info: "bg-panel-2 border-border text-parchment",
  success: "bg-ok/10 border-ok/30 text-ok",
  error: "bg-danger/10 border-danger/30 text-danger",
};

export default function ToastContainer() {
  const { toasts, dismissToast } = useToast();

  return (
    <div
      aria-live="polite"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded border px-3 py-2 text-sm shadow-lg flex items-start justify-between gap-2 ${VARIANT_CLASSES[t.variant]}`}
        >
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => dismissToast(t.id)}
            aria-label="Dismiss"
            className="text-xs opacity-60 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
