import { History, Search, Zap } from "lucide-react";
import { Link, NavLink } from "react-router-dom";

function navLinkClass({ isActive }) {
  return `relative rounded-full px-4 py-2 text-sm font-medium transition-all duration-300 ${
    isActive
      ? "bg-white/12 text-white shadow-lg shadow-blue-950/20 backdrop-blur-sm"
      : "text-slate-400 hover:bg-white/6 hover:text-white"
  }`;
}

function TopNavigation({ sessionCount }) {
  return (
    <header className="glass-card-static sticky top-4 z-20 rounded-[1.75rem] px-4 py-3 sm:px-5 animate-fade-in-up gradient-border">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/"
            className="group flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 text-blue-300 ring-1 ring-inset ring-blue-400/20 transition-all duration-300 hover:scale-110 hover:shadow-lg hover:shadow-blue-500/20"
          >
            <Search className="h-5 w-5 transition-transform duration-300 group-hover:rotate-12" />
          </Link>

          <div className="min-w-0">
            <Link to="/" className="font-display text-2xl leading-none text-white hover:text-gradient transition-all duration-300 sm:text-3xl">
              FactLens
            </Link>
            <p className="mt-1 hidden text-sm text-slate-400 sm:block">
              AI-powered claim verification engine
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex flex-wrap gap-1.5">
            <NavLink to="/" end className={navLinkClass}>
              Home
            </NavLink>
            <NavLink to="/workspace" className={navLinkClass}>
              Workspace
            </NavLink>
            <NavLink to="/history" className={navLinkClass}>
              History
            </NavLink>
            <NavLink to="/methodology" className={navLinkClass}>
              Methodology
            </NavLink>
          </nav>

          <div className="flex items-center gap-2">
            <div className="glass-pill flex items-center gap-2 rounded-full px-3 py-2 text-xs uppercase tracking-[0.18em] text-slate-400">
              <History className="h-3.5 w-3.5 shrink-0" />
              {sessionCount} run{sessionCount === 1 ? "" : "s"}
            </div>
            <Link
              to="/workspace"
              className="btn-shimmer inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-all duration-300 hover:shadow-xl hover:shadow-blue-500/30 hover:scale-[1.03]"
            >
              <Zap className="h-4 w-4 shrink-0" />
              Analyze
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}

export default TopNavigation;
