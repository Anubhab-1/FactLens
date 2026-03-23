import { ArrowUpRight, RotateCcw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import {
  formatSessionDate,
  getFreshestEvidence,
  getReportRouteId,
  getSessionStats,
  getSessionTitle,
} from "../lib/sessions";

const STATUS = {
  done: { dot: "bg-emerald-400", text: "text-emerald-400", label: "Done" },
  running: { dot: "bg-blue-400 animate-pulse", text: "text-blue-400", label: "Running" },
  error: { dot: "bg-rose-400", text: "text-rose-400", label: "Failed" },
  needs_review: { dot: "bg-amber-400", text: "text-amber-400", label: "Review" },
};

function ActionButton({ children, onClick, disabled = false, tone = "default" }) {
  const toneClassName = tone === "danger"
    ? "border-rose-500/20 text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
    : "border-white/8 text-slate-300 hover:bg-white/8 hover:text-white";

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50 ${toneClassName}`}
    >
      {children}
    </button>
  );
}

function IconButton({ label, onClick, disabled = false, children, tone = "default" }) {
  const toneClassName = tone === "danger"
    ? "hover:bg-rose-500/10 hover:text-rose-400"
    : "hover:bg-white/8";

  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      disabled={disabled}
      className={`rounded-lg p-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${toneClassName}`}
      style={{ color: "var(--ink-3)" }}
    >
      {children}
    </button>
  );
}

function SessionCard({
  session,
  onReuseSession,
  onTogglePinned,
  onToggleArchived,
  onDelete,
  compact = false,
  isActionBusy = false,
}) {
  const meta = STATUS[session.status] || STATUS.done;
  const stats = getSessionStats(session);
  const freshestEvidence = getFreshestEvidence(session.results);
  const routeId = getReportRouteId(session);

  return (
    <article className="glass-card group p-4 space-y-3 animate-fade-in-up" style={{ minWidth: 0 }}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${meta.dot}`} />
          <span className={`text-[10px] font-bold uppercase tracking-widest ${meta.text}`}>
            {meta.label}
          </span>
        </div>
        <span className="font-mono text-[10px] shrink-0" style={{ color: "var(--ink-3)" }}>
          {formatSessionDate(session.createdAt)}
        </span>
      </div>

      <div className="min-w-0">
        <Link
          to={`/report/${routeId}`}
          className="block truncate text-sm font-semibold text-white transition-colors group-hover:text-blue-300"
        >
          {getSessionTitle(session)}
        </Link>
        {!compact ? (
          <p className="mt-0.5 font-mono text-[10px] truncate" style={{ color: "var(--ink-3)" }}>
            {stats.totalClaims} claims - {stats.verifiedCount} verified
            {freshestEvidence && freshestEvidence !== "unknown" ? ` - ${freshestEvidence}` : ""}
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          {onReuseSession ? (
            compact ? (
              <IconButton
                label="Re-run with same input"
                onClick={() => onReuseSession(session)}
                disabled={isActionBusy}
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </IconButton>
            ) : (
              <ActionButton onClick={() => onReuseSession(session)} disabled={isActionBusy}>
                Re-run
              </ActionButton>
            )
          ) : null}

          {!compact && onTogglePinned ? (
            <ActionButton onClick={() => onTogglePinned(session)} disabled={isActionBusy}>
              {session.isPinned ? "Pinned" : "Pin"}
            </ActionButton>
          ) : null}

          {!compact && onToggleArchived ? (
            <ActionButton onClick={() => onToggleArchived(session)} disabled={isActionBusy}>
              {session.isArchived ? "Restore" : "Archive"}
            </ActionButton>
          ) : null}

          {onDelete ? (
            compact ? (
              <IconButton
                label="Delete"
                onClick={() => onDelete(session)}
                disabled={isActionBusy}
                tone="danger"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </IconButton>
            ) : (
              <ActionButton
                onClick={() => onDelete(session)}
                disabled={isActionBusy}
                tone="danger"
              >
                Delete
              </ActionButton>
            )
          ) : null}
        </div>

        <Link
          to={`/report/${routeId}`}
          className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider transition-colors"
          style={{ color: "var(--ink-3)" }}
        >
          View
          <ArrowUpRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </Link>
      </div>
    </article>
  );
}

export default SessionCard;
