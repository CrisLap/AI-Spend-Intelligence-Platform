import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

const GITHUB_URL = "https://github.com/CrisLap/AI-Spend-Intelligence-Platform";

// lucide-react dropped brand/logo icons (including Github) starting in its
// v1 line, so the GitHub mark is inlined here instead of imported.
function GithubMark({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.57.1.78-.25.78-.55 0-.27-.01-1.16-.02-2.11-3.2.7-3.88-1.36-3.88-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.05-.72.08-.71.08-.71 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.05 11.05 0 0 1 5.79 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.24 2.76.12 3.05.74.81 1.18 1.83 1.18 3.09 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14 0 1.55-.01 2.79-.01 3.17 0 .3.2.66.79.55A10.53 10.53 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z" />
    </svg>
  );
}

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
          <GithubMark /> {t("githubLink")}
        </a>
        <Link to="/login" className="rounded-full bg-teal px-4 py-1.5 text-xs font-semibold text-surface hover:opacity-90">
          {t("loginLink")}
        </Link>
      </nav>
    </header>
  );
}
