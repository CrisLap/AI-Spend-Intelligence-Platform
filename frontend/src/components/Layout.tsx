import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle, Bot, FileText, LayoutDashboard, Link2, Menu, MessageSquare,
  Moon, Search, ShieldCheck, Sparkles, Sun, Tags, X,
} from "lucide-react";
import { type User } from "../App";
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from "../i18n";
import { useTheme } from "../context/ThemeContext";

const NAV = [
  { to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
  { to: "/documents", labelKey: "nav.documents", icon: FileText },
  { to: "/classification", labelKey: "nav.classification", icon: Tags },
  { to: "/search", labelKey: "nav.search", icon: Search },
  { to: "/chat", labelKey: "nav.chat", icon: MessageSquare },
  { to: "/cost-saving", labelKey: "nav.costSaving", icon: Bot },
  { to: "/anomalies", labelKey: "nav.anomalies", icon: AlertTriangle },
  { to: "/duplicates", labelKey: "nav.duplicates", icon: Link2 },
];

const ADMIN_NAV = { to: "/admin", labelKey: "nav.admin", icon: ShieldCheck };

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
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-panel backdrop-blur-md px-4 py-3">
        <div className="flex items-center gap-3">
          <button onClick={() => setSidebarOpen(true)} aria-label={t("openMenu")} className="md:hidden text-parchment">
            <Menu size={20} aria-hidden="true" />
          </button>
          <span className="flex items-center gap-2 text-sm font-bold tracking-wider text-teal uppercase">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal/15 text-teal">
              <Sparkles size={16} aria-hidden="true" />
            </span>
            {t("appName")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1">
            {SUPPORTED_LANGUAGES.map((lng: SupportedLanguage) => (
              <button
                key={lng}
                onClick={() => i18n.changeLanguage(lng)}
                className={`rounded-full px-2 py-0.5 text-xs font-semibold transition-colors ${
                  i18n.resolvedLanguage === lng ? "bg-teal/10 text-teal" : "text-muted hover:text-parchment"
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
            className="rounded-full p-2 text-muted hover:text-parchment hover:bg-panel-2 transition-colors"
          >
            {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
          </button>
          <div className="hidden sm:flex flex-col items-end leading-tight">
            <span className="text-xs text-parchment">{user.full_name}</span>
            <span className="text-[10px] text-muted/70">{user.role}</span>
          </div>
          <button onClick={onLogout} className="text-xs text-danger hover:underline">{t("logout")}</button>
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
          className={`w-60 border-r border-border bg-panel backdrop-blur-md p-4 flex flex-col gap-1 shrink-0 fixed inset-y-0 left-0 z-50 top-14 transform overflow-y-auto transition-transform duration-200 md:sticky md:top-14 md:h-[calc(100vh-3.5rem)] md:translate-x-0 ${
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
            <NavLink key={n.to} to={n.to} end={n.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-full px-3 py-2 text-sm transition-colors ${isActive ? "bg-teal text-surface font-semibold" : "text-muted hover:text-parchment hover:bg-panel-2"}`
              }>
              <n.icon size={16} aria-hidden="true" /> {t(n.labelKey)}
            </NavLink>
          ))}
        </aside>
        <main className="flex-1 p-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
