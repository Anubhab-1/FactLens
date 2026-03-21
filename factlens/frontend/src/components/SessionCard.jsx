import { Archive, ArrowUpRight, Clock3, Pin, RotateCcw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import {
  formatSessionDate,
  getFreshestEvidence,
  getReportRouteId,
  getSessionStats,
  getSessionTitle,
} from "../lib/sessions";

const STATUS_META = {
  done: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
  running: "bg-blue-500/12 text-blue-200 ring-1 ring-inset ring-blue-400/20 animate-pulse-glow",
  error: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
};

function SessionCard({
  session,
  onReuseSession,
  onTogglePinned,
  onToggleArchived,
  onDelete,
  isActionBusy = false,
}) {
  const stats = getSessionStats(session);
  const freshestEvidence = getFreshestEvidence(session.results);

  return (
    <article className="glass-card rounded-[1.5rem] p-5 animate-fade-in-up">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium uppercase tracking-[0.16em] ${STATUS_META[session.status] || STATUS_META.done}`}
          >
            {session.status}
          </span>
          <span className="glass-pill rounded-full px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-400">
            {session.inputMode === "url" ? "Article URL" : "Pasted text"}
          </span>
          {session.isPinned ? (
            <span className="rounded-full bg-amber-500/12 px-3 py-1 text-xs uppercase tracking-[0.16em] text-amber-200 ring-1 ring-inset ring-amber-400/20">
              Pinned
            </span>
          ) : null}
          {session.isArchived ? (
            <span className="rounded-full bg-slate-500/12 px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-300 ring-1 ring-inset ring-slate-400/20">
              Archived
            </span>
          ) : null}
        </div>

        <div>
          <h3 className="text-lg font-semibold text-white">{getSessionTitle(session)}</h3>
          <p className="mt-2 flex items-center gap-2 text-sm text-slate-400">
            <Clock3 className="h-4 w-4" />
            {formatSessionDate(session.createdAt)}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-4">
          {[
            { label: "Claims", value: stats.totalClaims },
            { label: "Verified", value: stats.verifiedCount },
            { label: "Conflicts", value: stats.conflictCount },
            { label: "Freshest", value: freshestEvidence },
          ].map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-white/6 bg-white/4 px-3 py-3">
              <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{stat.label}</p>
              <p className="mt-2 font-mono text-lg font-semibold text-white">{stat.value}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to={`/report/${getReportRouteId(session)}`}
            className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:shadow-xl hover:scale-[1.03]"
          >
            <ArrowUpRight className="h-4 w-4" />
            Open report
          </Link>
          <button
            type="button"
            onClick={() => onReuseSession(session)}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-200 transition-all duration-300 hover:bg-white/10 hover:text-white"
          >
            <RotateCcw className="h-4 w-4" />
            Reuse
          </button>
          {onTogglePinned ? (
            <button
              type="button"
              onClick={() => onTogglePinned(session)}
              disabled={isActionBusy}
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-200 transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Pin className="h-4 w-4" />
              {session.isPinned ? "Unpin" : "Pin"}
            </button>
          ) : null}
          {onToggleArchived ? (
            <button
              type="button"
              onClick={() => onToggleArchived(session)}
              disabled={isActionBusy}
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-200 transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Archive className="h-4 w-4" />
              {session.isArchived ? "Restore" : "Archive"}
            </button>
          ) : null}
          {onDelete ? (
            <button
              type="button"
              onClick={() => onDelete(session)}
              disabled={isActionBusy}
              className="inline-flex items-center gap-2 rounded-full border border-rose-400/15 bg-rose-500/8 px-4 py-2 text-sm font-medium text-rose-200 transition-all duration-300 hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export default SessionCard;
