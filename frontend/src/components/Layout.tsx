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
    <div className="flex min-h-screen">
      <div className="md:hidden fixed inset-x-0 top-0 z-30 flex items-center justify-between border-b border-border bg-panel px-4 py-3">
        <span className="text-sm font-bold tracking-wider text-teal uppercase">{t("appName")}</span>
        <button onClick={() => setSidebarOpen(true)} aria-label={t("openMenu")} className="text-parchment">
          <Menu size={20} aria-hidden="true" />
        </button>
      </div>

      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-surface/70"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`w-60 border-r border-border bg-panel p-4 flex flex-col gap-1 shrink-0 fixed inset-y-0 left-0 z-50 transform overflow-y-auto transition-transform duration-200 md:relative md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-sm font-bold tracking-wider text-teal uppercase">{t("appName")}</h1>
            <p className="text-xs text-muted mt-1">{t("tagline")}</p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label={t("closeMenu")}
            className="md:hidden text-muted hover:text-parchment"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors ${isActive ? "bg-teal/10 text-teal" : "text-muted hover:text-parchment hover:bg-panel-2"}`
            }>
            <n.icon size={16} aria-hidden="true" /> {t(n.labelKey)}
          </NavLink>
        ))}
        <div className="mt-auto pt-4 border-t border-border">
          <div className="mb-2 flex items-center gap-1">
            {SUPPORTED_LANGUAGES.map((lng: SupportedLanguage) => (
              <button
                key={lng}
                onClick={() => i18n.changeLanguage(lng)}
                className={`rounded px-2 py-0.5 text-xs font-semibold transition-colors ${
                  i18n.resolvedLanguage === lng ? "bg-teal/10 text-teal" : "text-muted hover:text-parchment"
                }`}
              >
                {t(`language.${lng}`)}
              </button>
            ))}
            <button
              onClick={toggleTheme}
              aria-label={theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark")}
              title={theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark")}
              className="ml-auto rounded p-1 text-muted hover:text-parchment transition-colors"
            >
              {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
            </button>
          </div>
          <p className="text-xs text-muted">{user.full_name}</p>
          <p className="text-xs text-muted/60">{user.role}</p>
          <button onClick={onLogout} className="mt-2 text-xs text-danger hover:underline">{t("logout")}</button>
        </div>
      </aside>
      <main className="flex-1 p-6 overflow-auto mt-14 md:mt-0">{children}</main>
    </div>
  );
}
