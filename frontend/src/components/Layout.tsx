import { NavLink } from "react-router-dom";
import { type User } from "../App";

const NAV = [
  { to: "/", label: "Dashboard", icon: "📊" },
  { to: "/documents", label: "Documents", icon: "📄" },
  { to: "/classification", label: "Classification", icon: "🏷️" },
  { to: "/search", label: "Search", icon: "🔍" },
  { to: "/chat", label: "Chat", icon: "💬" },
  { to: "/cost-saving", label: "Cost Saving Agent", icon: "🤖" },
  { to: "/anomalies", label: "Anomalies", icon: "⚠️" },
  { to: "/duplicates", label: "Duplicates", icon: "🔗" },
];

const ADMIN_NAV = { to: "/admin", label: "Admin", icon: "🛡️" };

export default function Layout({ children, user, onLogout }: { children: React.ReactNode; user: User; onLogout: () => void }) {
  const nav = user.role === "admin" ? [...NAV, ADMIN_NAV] : NAV;
  return (
    <div className="flex min-h-screen">
      <aside className="w-60 border-r border-border bg-panel p-4 flex flex-col gap-1 shrink-0">
        <div className="mb-6">
          <h1 className="text-sm font-bold tracking-wider text-teal uppercase">SpendIntel</h1>
          <p className="text-xs text-muted mt-1">AI Spend Intelligence</p>
        </div>
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors ${isActive ? "bg-teal/10 text-teal" : "text-muted hover:text-parchment hover:bg-panel-2"}`
            }>
            <span>{n.icon}</span> {n.label}
          </NavLink>
        ))}
        <div className="mt-auto pt-4 border-t border-border">
          <p className="text-xs text-muted">{user.full_name}</p>
          <p className="text-xs text-muted/60">{user.role}</p>
          <button onClick={onLogout} className="mt-2 text-xs text-danger hover:underline">Logout</button>
        </div>
      </aside>
      <main className="flex-1 p-6 overflow-auto">{children}</main>
    </div>
  );
}
