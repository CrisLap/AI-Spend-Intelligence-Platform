import { useTranslation } from "react-i18next";

export default function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useTranslation("common");
  return (
    <div className="flex items-center gap-3 rounded border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="shrink-0 text-xs font-semibold underline hover:no-underline">
          {t("retry")}
        </button>
      )}
    </div>
  );
}
