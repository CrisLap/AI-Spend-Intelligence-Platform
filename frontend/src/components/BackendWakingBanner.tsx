import { useTranslation } from "react-i18next";
import { useBackendWaking } from "../hooks/useBackendWaking";

export default function BackendWakingBanner() {
  const { t } = useTranslation("common");
  const isWaking = useBackendWaking();
  if (!isWaking) return null;

  return (
    <div
      role="status"
      className="w-full bg-amber/10 border-b border-amber/30 text-amber text-sm px-4 py-2 text-center"
    >
      {t("backendWaking")}
    </div>
  );
}
