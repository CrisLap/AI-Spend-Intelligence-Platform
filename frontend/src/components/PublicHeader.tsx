import { Link } from "react-router-dom";
import { Github, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

const GITHUB_URL = "https://github.com/CrisLap/AI-Spend-Intelligence-Platform";

export default function PublicHeader() {
  const { t } = useTranslation(["landing", "common"]);
  return (
    <header className="flex items-center justify-between max-w-6xl mx-auto w-full px-6 py-4">
      <Link to="/" className="flex items-center gap-2 text-sm font-bold tracking-wider text-teal uppercase">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal/15 text-teal">
          <Sparkles size={16} aria-hidden="true" />
        </span>
        {t("common:appName")}
      </Link>
      <nav className="flex items-center gap-4">
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-xs text-muted hover:text-parchment"
        >
          <Github size={14} aria-hidden="true" /> {t("githubLink")}
        </a>
        <Link to="/login" className="rounded-full bg-teal px-4 py-1.5 text-xs font-semibold text-surface hover:opacity-90">
          {t("loginLink")}
        </Link>
      </nav>
    </header>
  );
}
