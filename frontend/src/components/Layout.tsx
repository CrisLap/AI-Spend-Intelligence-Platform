import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle, Bot, FileText, LayoutDashboard, Link2, Menu, MessageSquare,
  Moon, Search, ShieldCheck, Sun, Tags, X,
} from "lucide-react";
import { type User } from "../App";
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../i18n";
import { useTheme } from "../context/ThemeContext";

const NAV = [
  { to: "/app", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/app/documents", labelKey: "nav.documents", icon: FileText },
  { to: "/app/classification", labelKey: "nav.classification", icon: Tags },
  { to: "/app/search", labelKey: "nav.search", icon: Search },
  { to: "/app/chat", labelKey: "nav.chat", icon: MessageSquare },
  { to: "/app/cost-saving", labelKey: "nav.costSaving", icon: Bot },
  { to: "/app/anomalies", labelKey: "nav.anomalies", icon: AlertTriangle },
  { to: "/app/duplicates", labelKey: "nav.duplicates", icon: Link2 },
];

const ADMIN_NAV = { to: "/app/admin", labelKey: "nav.admin", icon: ShieldCheck };

export default function Layout({ children, user, onLogout }: { children: React.ReactNode; user: User; onLogout: () => void }) {
  const { t, i18n } = useTranslation("common");
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const nav = user.role === "admin" ? [...NAV, ADMIN_NAV] : NAV;

  // Off-canvas drawer below md: auto-close on every navigation so it never
  // stays open covering the next page.
  useEffect(() => { setSidebarOpen(false); }, [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      {/* Top bar: app identity on the left, theme/language/account controls
          on the right - visible at every breakpoint, unlike the old
          mobile-only bar. */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-surface px-4">
        <div className="flex items-center gap-3">
          <button onClick={() => setSidebarOpen(true)} aria-label={t("openMenu")} className="md:hidden text-parchment">
            <Menu size={20} aria-hidden="true" />
          </button>
          <span className="text-base font-medium text-parchment">{t("appName")}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1">
            {SUPPORTED_LANGUAGES.map((lng: SupportedLanguage) => (
              <button
                key={lng}
                onClick={() => i18n.changeLanguage(lng)}
                className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                  i18n.resolvedLanguage === lng ? "bg-panel-2 text-parchment" : "text-muted hover:text-parchment"
                }`}
              >
                {t(`language.${lng}`)}
              </button>
            ))}
          </div>
          <button
            onClick={toggleTheme}
            aria-label={theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark")}
            title={theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark")}
            className="rounded-lg p-2 text-muted hover:text-parchment hover:bg-panel-2 transition-colors"
          >
            {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
          </button>
          <div className="hidden sm:flex flex-col items-end leading-tight">
            <span className="text-sm text-parchment">{user.full_name}</span>
            <span className="text-xs text-muted">{user.role}</span>
          </div>
          <button onClick={onLogout} className="rounded-md px-2 py-1 text-sm text-secondary hover:text-parchment hover:bg-panel-2 transition-colors">{t("logout")}</button>
        </div>
      </header>

      <div className="flex flex-1">
        {sidebarOpen && (
          <div
            className="md:hidden fixed inset-0 z-40 bg-surface/70"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        <aside
          className={`w-60 border-r border-border bg-sidebar p-3 flex flex-col gap-0.5 shrink-0 fixed inset-y-0 left-0 z-50 top-14 transform overflow-y-auto transition-transform duration-200 md:sticky md:top-14 md:h-[calc(100vh-3.5rem)] md:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label={t("closeMenu")}
            className="md:hidden self-end mb-2 text-muted hover:text-parchment"
          >
            <X size={18} aria-hidden="true" />
          </button>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/app"}
              className={({ isActive }) =>
                `flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm transition-colors ${isActive ? "bg-panel-2 text-parchment font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]" : "text-secondary hover:text-parchment hover:bg-panel-2/60"}`
              }>
              <n.icon size={16} strokeWidth={1.5} aria-hidden="true" className="shrink-0 text-muted" /> {t(n.labelKey)}
            </NavLink>
          ))}
        </aside>
        <main className="flex-1 min-w-0 overflow-auto p-6 md:p-8"><div className="mx-auto w-full max-w-[1440px]">{children}</div></main>
      </div>
    </div>
  );
}
