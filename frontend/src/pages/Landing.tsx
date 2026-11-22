import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import PublicHeader from "../components/PublicHeader";

const GITHUB_URL = "https://github.com/CrisLap/AI-Spend-Intelligence-Platform";

const STACK = [
  "Python 3.12 / FastAPI",
  "Ollama / Groq / ReAct",
  "PostgreSQL / Qdrant",
  "React 19 / TypeScript / Tailwind v4",
  "Docker / GitHub Actions / Render",
];

export default function Landing() {
  const { t } = useTranslation(["landing", "common"]);
  useDocumentTitle(t("common:tagline"));

  return (
    <div className="flex min-h-[100dvh] flex-col bg-surface">
      <PublicHeader />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-12 px-6 pb-20 pt-12 lg:pt-20">
        <div className="flex max-w-2xl flex-col gap-6">
          <h1 className="text-4xl font-medium leading-[1.08] tracking-[-0.02em] text-parchment md:text-6xl md:tracking-[-0.03em]">
            {t("headline")}
          </h1>
          <p className="max-w-xl text-lg leading-7 text-secondary">{t("subheadline")}</p>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-3">
              <Link
                to="/login?demo=buyer"
                className="inline-flex h-11 items-center rounded-lg bg-teal px-5 text-sm font-medium text-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] transition hover:brightness-110 active:scale-[0.98]"
              >
                {t("tryDemoCta")}
              </Link>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-11 items-center rounded-lg border border-border bg-panel-2 px-5 text-sm font-medium text-parchment transition hover:bg-panel-2/70 active:scale-[0.98]"
              >
                {t("viewCodeCta")}
              </a>
            </div>
            <p className="text-sm text-muted">{t("coldStartNote")}</p>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-border bg-panel p-2">
          <img
            src="/dashboard-screenshot.png"
            alt={t("screenshotAlt")}
            className="w-full rounded-xl"
            loading="lazy"
          />
        </div>

        <ul className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-muted">
          {STACK.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </main>
    </div>
  );
}
