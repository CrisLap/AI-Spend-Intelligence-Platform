import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export default function NotFound() {
  const { t } = useTranslation("common");
  return (
    <div className="flex h-full min-h-[50vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm font-semibold text-parchment">{t("notFound.title")}</p>
      <p className="text-xs text-muted">{t("notFound.description")}</p>
      <Link to="/" className="rounded bg-teal px-4 py-1.5 text-xs font-semibold text-surface">
        {t("notFound.backHome")}
      </Link>
    </div>
  );
}
