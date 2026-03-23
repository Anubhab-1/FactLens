import { useEffect, useState } from "react";
import { ArrowLeft, Download, Pin, RefreshCcw, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import AuthenticitySignalsPanel from "../components/AuthenticitySignalsPanel";
import ClaimCard from "../components/ClaimCard";
import ClaimNavigator from "../components/ClaimNavigator";
import ClaimExtractionPanel from "../components/ClaimExtractionPanel";
import ClaimTracePanel from "../components/ClaimTracePanel";
import EvaluationPanel from "../components/EvaluationPanel";
import ReportOverview from "../components/ReportOverview";
import SourceCapturePanel from "../components/SourceCapturePanel";
import SourceReviewPanel from "../components/SourceReviewPanel";
import SourceTimeline from "../components/SourceTimeline";
import {
  deleteReport,
  fetchReport,
  getReportExportUrl,
  getReportPdfExportUrl,
  getReportShareUrl,
  recalculateReportClaim,
  updateReport,
} from "../lib/api";
import { sessionFromReport } from "../lib/sessions";

// ─── Helpers ─────────────────────────────────────────────────────────
function matchesFilter(result, filter) {
  if (filter === "all") return true;
  if (filter === "time_sensitive") return Boolean(result.time_sensitive);
  if (filter === "conflict") return Boolean(result.conflict_detected);
  return result.verdict === filter;
}

// ─── State splash ────────────────────────────────────────────────────
function StateSplash({ icon, title, body, action }) {
  return (
    <div className="page-wrapper flex min-h-[60vh] flex-col items-center justify-center text-center animate-fade-in">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-white/8 text-white/30">
        {icon}
      </div>
      <h2 className="text-2xl font-bold text-white">{title}</h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>{body}</p>
      {action && <div className="mt-8">{action}</div>}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function ReportPage({ sessions, onHydrateReport, onRemoveReport, onReuseSession, onUpsertReport }) {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [remoteSession, setRemoteSession] = useState(null);
  const [isFetching, setIsFetching] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [shareState, setShareState] = useState("idle");
  const [actionError, setActionError] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [reviewingClaimId, setReviewingClaimId] = useState(null);
  const [reviewErrors, setReviewErrors] = useState({});
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [filter, setFilter] = useState("all");
  const [selectedClaimId, setSelectedClaimId] = useState(null);

  const shareToken = searchParams.get("share");
  const session =
    sessions.find((s) => s.id === sessionId || s.reportId === sessionId) ||
    remoteSession ||
    null;
  const matchingSession =
    sessions.find((s) => s.id === sessionId || s.reportId === sessionId) || null;

  useEffect(() => { setFilter("all"); }, [sessionId]);

  useEffect(() => {
    setSelectedClaimId(null);
  }, [sessionId]);

  useEffect(() => {
    let active = true;
    if (matchingSession?.canManage && !shareToken) {
      setRemoteSession(null);
      setIsFetching(false);
      setFetchFailed(false);
      return;
    }
    setIsFetching(true);
    fetchReport(sessionId, { shareToken })
      .then((r) => { if (active) { setRemoteSession(sessionFromReport(r)); onHydrateReport(r); } })
      .catch(() => { if (active) setFetchFailed(true); })
      .finally(() => { if (active) setIsFetching(false); });
    return () => { active = false; };
  }, [matchingSession, onHydrateReport, sessionId, shareToken]);

  const filteredResults = session
    ? session.results.filter((r) => matchesFilter(r, filter))
    : [];
  const selectedResult = filteredResults.find((result) => result.claim_id === selectedClaimId) || filteredResults[0] || null;

  useEffect(() => {
    if (!filteredResults.length) {
      if (selectedClaimId !== null) {
        setSelectedClaimId(null);
      }
      return;
    }

    if (!filteredResults.some((result) => result.claim_id === selectedClaimId)) {
      setSelectedClaimId(filteredResults[0].claim_id);
    }
  }, [filteredResults, selectedClaimId]);

  const handleShare = async () => {
    if (!session?.reportId) return;
    try {
      await navigator.clipboard.writeText(
        getReportShareUrl(session.reportId, session.shareToken || shareToken)
      );
      setShareState("copied");
      setTimeout(() => setShareState("idle"), 2000);
    } catch { setShareState("failed"); }
  };

  const applyUpdate = (report) => {
    setRemoteSession(sessionFromReport(report));
    onUpsertReport(report);
  };

  const handlePin = async () => {
    if (!session?.reportId || actionBusy) return;
    setActionBusy(true); setActionError(null);
    try { applyUpdate(await updateReport(session.reportId, { is_pinned: !session.isPinned })); }
    catch { setActionError("Update failed."); } finally { setActionBusy(false); }
  };

  const handleArchive = async () => {
    if (!session?.reportId || actionBusy) return;
    setActionBusy(true); setActionError(null);
    try { applyUpdate(await updateReport(session.reportId, { is_archived: !session.isArchived })); }
    catch { setActionError("Update failed."); } finally { setActionBusy(false); }
  };

  const handleApplyOverrides = async (claimId, overrides) => {
    if (!session?.reportId || !claimId || reviewingClaimId) return;

    setReviewingClaimId(claimId);
    setReviewErrors((current) => ({
      ...current,
      [claimId]: null,
    }));

    try {
      const updated = await recalculateReportClaim(session.reportId, claimId, overrides);
      applyUpdate(updated);
    } catch {
      setReviewErrors((current) => ({
        ...current,
        [claimId]: "Manual review could not be applied.",
      }));
    } finally {
      setReviewingClaimId(null);
    }
  };

  const handleDelete = async () => {
    if (!session?.reportId) return;
    setActionBusy(true); setConfirmDelete(false);
    try { await deleteReport(session.reportId); onRemoveReport(session.reportId); navigate("/history"); }
    catch { setActionError("Delete failed."); setActionBusy(false); }
  };

  // ── Loading states ─────────────────────────────────────────────────
  if (!session && (isFetching || !fetchFailed)) {
    return (
      <StateSplash
        icon={<div className="h-4 w-4 rounded-full bg-blue-500 animate-pulse" />}
        title="Loading report"
        body="Retrieving your verification payload from the database."
      />
    );
  }

  if (!session && fetchFailed) {
    return (
      <StateSplash
        icon={<div className="h-5 w-5 text-rose-400" style={{ fontSize: "1.25rem" }}>⚠</div>}
        title="Report not found"
        body="This verification record may have expired or been moved."
        action={
          <Link to="/workspace" className="btn-primary text-sm">Open Workspace</Link>
        }
      />
    );
  }

  // ── Main render ────────────────────────────────────────────────────
  return (
    <div className="page-wrapper space-y-10 animate-fade-in">

      {/* ── Page Header ─────────────────────────────────────────── */}
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2 min-w-0">
          <Link
            to="/history"
            className="inline-flex items-center gap-1.5 text-xs font-semibold transition-colors hover:text-white"
            style={{ color: "var(--ink-3)" }}
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to History
          </Link>
          <p className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
            Report #{sessionId?.slice(0, 8)}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button
            onClick={() => onReuseSession(session)}
            className="btn-secondary text-xs"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            Rerun
          </button>
          <button
            onClick={handlePin}
            disabled={actionBusy}
            className={`btn-secondary text-xs ${session.isPinned ? "text-blue-400 border-blue-500/30" : ""}`}
          >
            <Pin className="h-3.5 w-3.5" />
            {session.isPinned ? "Unpin" : "Pin"}
          </button>
          <button
            onClick={handleArchive}
            disabled={actionBusy}
            className="btn-secondary text-xs"
          >
            {session.isArchived ? "Restore" : "Archive"}
          </button>
          <button
            onClick={handleShare}
            className="btn-secondary text-xs"
          >
            {shareState === "copied" ? "✓ Copied!" : "Share link"}
          </button>
          {session.reportId && (
            <a
              href={getReportExportUrl(session.reportId, {
                shareToken: session.shareToken || shareToken,
              })}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              JSON
            </a>
          )}
          <button
            onClick={() => setConfirmDelete(true)}
            disabled={actionBusy}
            className="btn-secondary text-xs text-rose-400 border-rose-500/20 hover:bg-rose-500/10"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {actionError && (
        <p className="rounded-xl border border-rose-500/20 bg-rose-500/8 px-4 py-3 text-xs text-rose-400">
          {actionError}
        </p>
      )}

      {/* ── Overview Hero ────────────────────────────────────────── */}
      <ReportOverview session={session} />

      {/* ── Main 2-column grid ───────────────────────────────────── */}
      <main className="grid gap-10 lg:grid-cols-[1fr_360px]">

        {/* Left — Claims feed */}
        <div className="min-w-0 space-y-8">
          <SourceCapturePanel
            sourceCapture={session.sourceCapture}
            inputMode={session.inputMode}
          />

          {session.claimExtraction ? (
            <ClaimExtractionPanel claimExtraction={session.claimExtraction} />
          ) : null}

          {session.sourceText && session.claims?.length ? (
            <ClaimTracePanel
              sourceText={session.sourceText}
              claims={session.claims}
              selectedClaimId={selectedResult?.claim_id || null}
              onSelectClaimId={setSelectedClaimId}
              isTruncated={session.sourceTextTruncated}
            />
          ) : null}

          {/* Claims list */}
          <div className="space-y-5">
            {filteredResults.length > 0 ? (
              filteredResults.map((r, i) => (
                <div
                  key={r.claim_id}
                  onClick={() => setSelectedClaimId(r.claim_id)}
                  className={`space-y-4 rounded-[1.8rem] transition-all duration-300 animate-fade-in-up delay-${Math.min(i + 1, 8)} ${
                    selectedResult?.claim_id === r.claim_id
                      ? "ring-1 ring-blue-400/25 shadow-[0_0_0_1px_rgba(96,165,250,0.08)]"
                      : ""
                  }`}
                >
                  <ClaimCard
                    anchorId={`claim-${r.claim_id}`}
                    result={r}
                    claim={session.claims?.find((c) => c.id === r.claim_id)}
                  />
                  <SourceReviewPanel
                    result={r}
                    canManage={Boolean(session.canManage)}
                    onApplyOverrides={handleApplyOverrides}
                    isBusy={reviewingClaimId === r.claim_id}
                    error={reviewErrors[r.claim_id] || null}
                  />
                </div>
              ))
            ) : (
              <div
                className="rounded-2xl border border-dashed p-10 text-center text-sm"
                style={{ borderColor: "var(--border-faint)", color: "var(--ink-3)" }}
              >
                No claims match this filter.
              </div>
            )}
          </div>
        </div>

        {/* Right — Diagnostics sidebar */}
        <aside className="min-w-0">
          <div className="sticky space-y-6" style={{ top: "calc(var(--nav-height) + 1.5rem)" }}>
            <ClaimNavigator
              results={filteredResults}
              allResults={session.results}
              activeFilter={filter}
              onFilterChange={setFilter}
              selectedClaimId={selectedResult?.claim_id || null}
              onSelectClaimId={setSelectedClaimId}
            />

            {selectedResult ? (
              <SourceTimeline result={selectedResult} />
            ) : null}

            <EvaluationPanel evaluation={session.evaluation} />

            <AuthenticitySignalsPanel
              aiDetection={session.aiDetection}
              mediaDetection={session.mediaDetection}
              compact
            />

            <div className="glass-card-static p-5 space-y-4">
              <span className="label-cap">Export</span>
              <div className="space-y-2">
                {session.reportId && (
                  <>
                    <a
                      href={getReportExportUrl(session.reportId, {
                        shareToken: session.shareToken || shareToken,
                      })}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-xs font-medium transition-colors hover:bg-white/5"
                      style={{ color: "var(--ink-2)", border: "1px solid var(--border-faint)" }}
                    >
                      Download data file
                      <Download className="h-3.5 w-3.5 shrink-0" />
                    </a>
                    <a
                      href={getReportPdfExportUrl(session.reportId, {
                        shareToken: session.shareToken || shareToken,
                      })}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex w-full items-center justify-between rounded-xl px-4 py-3 text-xs font-medium transition-colors hover:bg-white/5"
                      style={{ color: "var(--ink-2)", border: "1px solid var(--border-faint)" }}
                    >
                      Download PDF
                      <Download className="h-3.5 w-3.5 shrink-0" />
                    </a>
                  </>
                )}
              </div>
            </div>
          </div>
        </aside>
      </main>

      {/* ── Delete dialog ─────────────────────────────────────────── */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-lg animate-fade-in"
          style={{ background: "rgba(2,2,4,0.85)" }}
        >
          <div className="glass-card-static max-w-sm w-full p-8 space-y-6 animate-fade-in-up">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-500/15 mx-auto">
              <Trash2 className="h-5 w-5 text-rose-400" />
            </div>
            <div className="text-center space-y-2">
              <h3 className="text-xl font-bold text-white">Delete this report?</h3>
              <p className="text-sm" style={{ color: "var(--ink-2)" }}>
                This action cannot be undone. The verification record will be permanently removed.
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleDelete}
                className="flex-1 rounded-full bg-rose-500 py-3 text-sm font-bold text-white hover:bg-rose-400 transition-colors"
              >
                Delete
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex-1 btn-secondary py-3 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ReportPage;
