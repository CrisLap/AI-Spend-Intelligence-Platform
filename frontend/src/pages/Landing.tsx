import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import PublicHeader from "../components/PublicHeader";
import Card from "../components/Card";

const GITHUB_URL = "https://github.com/CrisLap/AI-Spend-Intelligence-Platform";

const STACK_BADGES = [
  "Python 3.12 · FastAPI",
  "Ollama · Groq · ReAct",
  "PostgreSQL · Qdrant",
  "React 19 · TypeScript · Tailwind v4",
  "Docker · GitHub Actions · Render",
];

export default function Landing() {
  const { t } = useTranslation(["landing", "common"]);
  useDocumentTitle(t("common:tagline"));

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <PublicHeader />
      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-12 flex flex-col gap-10 items-center text-center">
        <h1 className="text-3xl md:text-5xl font-bold text-parchment max-w-3xl">{t("headline")}</h1>
        <p className="text-sm md:text-base text-muted max-w-xl">{t("subheadline")}</p>
        <div className="flex flex-col items-center gap-2">
          <div className="flex flex-wrap gap-3 justify-center">
            <Link
              to="/login?demo=buyer"
              className="rounded-full bg-teal px-6 py-2.5 text-sm font-semibold text-surface hover:opacity-90"
            >
              {t("tryDemoCta")}
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-border px-6 py-2.5 text-sm font-semibold text-parchment hover:bg-panel-2"
            >
              {t("viewCodeCta")}
            </a>
          </div>
          <p className="text-xs text-muted">{t("coldStartNote")}</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-center">
          {STACK_BADGES.map((badge) => (
            <span key={badge} className="rounded-full border border-border px-3 py-1 text-xs text-muted">
              {badge}
            </span>
          ))}
        </div>
        <Card padding="none" className="overflow-hidden w-full max-w-4xl">
          <img src="/dashboard-screenshot.png" alt={t("screenshotAlt")} className="w-full" loading="lazy" />
        </Card>
      </main>
    </div>
  );
}
