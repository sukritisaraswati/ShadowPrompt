/**
 * Persistent shell: top navigation with the two service groups, plus the
 * defensive-use notice that the blueprint requires on every screen.
 */

import { NavLink, Outlet } from "react-router-dom";

import { useTheme } from "@/context/ThemeContext";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const LAB_NAV: NavItem[] = [
  { to: "/lab/connect", label: "Connect" },
  { to: "/lab/configure", label: "Configure" },
  { to: "/lab/packs", label: "Custom tests" },
  { to: "/lab/history", label: "History" },
  { to: "/lab/compare", label: "Compare" },
];

const SCAN_NAV: NavItem[] = [
  { to: "/scan", label: "Scanner", end: true },
  { to: "/scan/demo", label: "Demo Lab" },
  { to: "/scan/history", label: "History" },
];

function navClass({ isActive }: { isActive: boolean }): string {
  const base = "rounded-md px-2.5 py-1.5 text-sm transition-colors";
  return isActive
    ? `${base} bg-accent-500 text-white`
    : `${base} text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-shadow-800`;
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-shadow-800"
    >
      {theme === "dark" ? "Light" : "Dark"}
    </button>
  );
}

function NavGroup({ title, items }: { title: string; items: NavItem[] }) {
  return (
    <div className="flex items-center gap-1">
      <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </span>
      {items.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
          {item.label}
        </NavLink>
      ))}
    </div>
  );
}

export default function Layout() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-shadow-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
          <NavLink to="/" className="text-lg font-bold tracking-tight">
            Shadow<span className="text-accent-500">Prompt</span>
          </NavLink>

          <nav className="flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Main">
            <NavGroup title="Lab" items={LAB_NAV} />
            <NavGroup title="ShadowScan" items={SCAN_NAV} />
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <NavLink to="/about" className={navClass}>
              Methodology
            </NavLink>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 px-4 py-4 text-center text-xs text-slate-500 dark:border-slate-800">
        ShadowPrompt v0.5.0 &middot; For authorized, educational, and defensive security
        research only. It does not attack real users, websites, or production systems.
      </footer>
    </div>
  );
}
