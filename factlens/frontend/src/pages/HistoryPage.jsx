import { useEffect, useMemo, useState } from "react";

import SessionCard from "../components/SessionCard";
import { deleteReport, fetchReports, updateReport } from "../lib/api";
import { mergeSessions, sessionFromReport } from "../lib/sessions";

const PAGE_SIZE = 12;

function HistoryPage({ sessions, onReuseSession, onUpsertReport, onRemoveReport }) {
  const [includeArchived, setIncludeArchived] = useState(false);
  const [historySessions, setHistorySessions] = useState(() => sessions);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [actionReportId, setActionReportId] = useState(null);
  const [error, setError] = useState(null);

  const sortedSessions = useMemo(
    () =>
      [...historySessions].sort((left, right) => {
        if (Boolean(left.isPinned) !== Boolean(right.isPinned)) {
          return left.isPinned ? -1 : 1;
        }
        return new Date(right.createdAt) - new Date(left.createdAt);
      }),
    [historySessions],
  );

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);

    fetchReports({ limit: PAGE_SIZE, offset: 0, includeArchived })
      .then((payload) => {
        if (!active) {
          return;
        }

        const nextSessions = (payload.reports || []).map(sessionFromReport);
        setHistorySessions(nextSessions);
        setOffset(nextSessions.length);
        setHasMore(Boolean(payload.has_more));
      })
      .catch(() => {
        if (!active) {
          return;
        }

        setError("Saved reports could not be loaded right now.");
        setHistorySessions(includeArchived ? [] : sessions);
        setOffset(includeArchived ? 0 : sessions.length);
        setHasMore(false);
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [includeArchived, sessions]);

  const loadMore = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const payload = await fetchReports({
        limit: PAGE_SIZE,
        offset,
        includeArchived,
      });
      const nextSessions = (payload.reports || []).map(sessionFromReport);
      setHistorySessions((current) => mergeSessions(current, nextSessions));
      setOffset((current) => current + nextSessions.length);
      setHasMore(Boolean(payload.has_more));
    } catch {
      setError("More saved reports could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTogglePinned = async (session) => {
    if (!session.reportId) {
      return;
    }

    setActionReportId(session.reportId);
    setError(null);

    try {
      const updated = await updateReport(session.reportId, {
        is_pinned: !session.isPinned,
      });
      const normalized = sessionFromReport(updated);
      setHistorySessions((current) => mergeSessions(current, [normalized]));
      onUpsertReport(updated);
    } catch {
      setError("The report could not be updated.");
    } finally {
      setActionReportId(null);
    }
  };

  const handleToggleArchived = async (session) => {
    if (!session.reportId) {
      return;
    }

    setActionReportId(session.reportId);
    setError(null);

    try {
      const updated = await updateReport(session.reportId, {
        is_archived: !session.isArchived,
      });
      const normalized = sessionFromReport(updated);
      setHistorySessions((current) => {
        const merged = mergeSessions(current, [normalized]);
        return includeArchived ? merged : merged.filter((item) => !item.isArchived);
      });
      if (!includeArchived && normalized.isArchived) {
        setOffset((current) => Math.max(current - 1, 0));
      }
      onUpsertReport(updated);
    } catch {
      setError("The report archive state could not be updated.");
    } finally {
      setActionReportId(null);
    }
  };

  const handleDelete = async (session) => {
    if (!session.reportId) {
      return;
    }

    const confirmed = window.confirm("Delete this saved report permanently?");
    if (!confirmed) {
      return;
    }

    setActionReportId(session.reportId);
    setError(null);

    try {
      await deleteReport(session.reportId);
      setHistorySessions((current) =>
        current.filter((item) => item.reportId !== session.reportId),
      );
      setOffset((current) => Math.max(current - 1, 0));
      onRemoveReport(session.reportId);
    } catch {
      setError("The report could not be deleted.");
    } finally {
      setActionReportId(null);
    }
  };

  return (
    <div className="space-y-6">
      <section className="glass-card-static rounded-[2rem] p-6 animate-fade-in-up gradient-border">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">History</p>
            <h1 className="mt-2 text-3xl font-semibold text-white">Saved analyses</h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
              Manage saved reports with pin, archive, restore, delete, and paginated loading.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setIncludeArchived(false)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-300 ${
                !includeArchived
                  ? "bg-white text-slate-950 shadow-lg shadow-slate-950/10"
                  : "glass-pill text-slate-300 hover:bg-white/10"
              }`}
            >
              Active reports
            </button>
            <button
              type="button"
              onClick={() => setIncludeArchived(true)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-all duration-300 ${
                includeArchived
                  ? "bg-white text-slate-950 shadow-lg shadow-slate-950/10"
                  : "glass-pill text-slate-300 hover:bg-white/10"
              }`}
            >
              All reports
            </button>
          </div>
        </div>
      </section>

      {error ? (
        <div className="rounded-[1.5rem] border border-rose-400/20 bg-rose-500/8 px-5 py-4 text-sm text-rose-200 glow-rose animate-fade-in-up">
          {error}
        </div>
      ) : null}

      {sortedSessions.length ? (
        <div className="space-y-5">
          <div className="grid gap-5">
            {sortedSessions.map((session) => (
              <SessionCard
                key={session.reportId || session.id}
                session={session}
                onReuseSession={onReuseSession}
                onTogglePinned={handleTogglePinned}
                onToggleArchived={handleToggleArchived}
                onDelete={handleDelete}
                isActionBusy={actionReportId === session.reportId}
              />
            ))}
          </div>

          {hasMore ? (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={isLoading}
                className="glass-pill rounded-full px-5 py-3 text-sm font-medium text-slate-300 transition-all duration-300 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isLoading ? "Loading more..." : "Load more reports"}
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="glass-card rounded-[2rem] border-dashed px-6 py-6 text-sm leading-7 text-slate-400 animate-fade-in-up">
          {isLoading
            ? "Loading saved analyses..."
            : includeArchived
              ? "There are no saved reports yet."
              : "No active analyses right now. Archived reports can still be viewed from the All reports tab."}
        </div>
      )}
    </div>
  );
}

export default HistoryPage;
