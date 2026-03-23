import { useState } from "react";
import { Menu, X, Search, Zap, History, BarChart2 } from "lucide-react";
import { Link, NavLink } from "react-router-dom";

const NAV_LINKS = [
  { to: "/", label: "Home",        end: true  },
  { to: "/workspace", label: "Workspace" },
  { to: "/history",   label: "History"   },
  { to: "/demo",      label: "Demo"      },
  { to: "/methodology", label: "About"  },
];

function TopNavigation({ sessionCount }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="nav-frosted w-full animate-fade-in">
      <div
        style={{ maxWidth: "1280px", marginInline: "auto", height: "100%" }}
        className="flex items-center justify-between gap-4 px-4 sm:px-6 lg:px-8"
      >
        {/* Brand */}
        <Link
          to="/"
          className="flex shrink-0 items-center gap-2.5 transition-opacity hover:opacity-80"
          onClick={() => setMenuOpen(false)}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-500/15 ring-1 ring-blue-500/30">
            <Search className="h-4 w-4 text-blue-400" />
          </span>
          <span
            style={{ fontFamily: "'Space Grotesk', sans-serif", letterSpacing: "-0.02em" }}
            className="text-xl font-bold text-white"
          >
            FactLens
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-1 md:flex">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `rounded-full px-4 py-1.5 text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-white/8 text-white"
                    : "text-white/40 hover:bg-white/5 hover:text-white/80"
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Right actions */}
        <div className="flex shrink-0 items-center gap-2.5">
          {/* Session count badge */}
          <span className="glass-pill hidden sm:flex">
            <BarChart2 className="h-3 w-3" />
            {sessionCount} run{sessionCount !== 1 ? "s" : ""}
          </span>

          {/* CTA */}
          <Link
            to="/workspace"
            className="btn-primary btn-shimmer text-xs tracking-wide"
          >
            <Zap className="h-3.5 w-3.5 shrink-0 fill-current" />
            Verify
          </Link>

          {/* Mobile hamburger */}
          <button
            type="button"
            aria-label="Toggle menu"
            onClick={() => setMenuOpen((p) => !p)}
            className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/8 text-white/50 transition-colors hover:text-white md:hidden"
          >
            {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Mobile Dropdown */}
      {menuOpen && (
        <div
          className="absolute left-0 right-0 top-[72px] z-40 animate-fade-in border-t border-b border-white/5 bg-[#07070c]/95 backdrop-blur-2xl md:hidden"
        >
          <nav className="flex flex-col px-4 py-4 gap-1">
            {NAV_LINKS.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `rounded-xl px-4 py-3 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white/8 text-white"
                      : "text-white/40 hover:bg-white/5 hover:text-white"
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
            <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
              <span className="glass-pill">
                <History className="h-3 w-3" />
                {sessionCount} run{sessionCount !== 1 ? "s" : ""}
              </span>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

export default TopNavigation;
