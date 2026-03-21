import { useEffect, useState } from "react";
import { Archive, ArrowRight, Download, Link2, Pin, RefreshCcw, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import AuthenticitySignalsPanel from "../components/AuthenticitySignalsPanel";
import ClaimCard from "../components/ClaimCard";
import ClaimNavigator from "../components/ClaimNavigator";
import PipelineProgress from "../components/PipelineProgress";
import ReportOverview from "../components/ReportOverview";
import SourceTimeline from "../components/SourceTimeline";
import { sampleInputs } from "../data/sampleInputs";
import {
  deleteReport,
  fetchReport,
  getReportExportUrl,
  getReportPdfExportUrl,
  getReportShareUrl,
  updateReport,
} from "../lib/api";
import { sessionFromReport } from "../lib/sessions";

function matchesFilter(result, filter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "time_sensitive") {
    return Boolean(result.time_sensitive);
  }
  if (filter === "conflict") {
    return Boolean(result.conflict_detected);
  }
  return result.verdict === filter;
}

function ReviewStateCard({ title, body, primaryAction, secondaryAction, tone = "slate" }) {
  const toneClass = {
    slate: "border-white/8 bg-white/5 text-slate-300",
    rose: "border-rose-400/15 bg-rose-500/8 text-rose-200",
    amber: "border-amber-400/15 bg-amber-500/8 text-amber-200",
  }[tone];

  const glowClass = {
    slate: "",
    rose: "glow-rose",
    amber: "glow-amber",
  }[tone];

  return (
    <section className={`glass-card-static rounded-[1.75rem] border px-5 py-5 animate-fade-in-up ${toneClass} ${glowClass}`}>
      <h2 className="text-2xl font-semibold text-white">{title}</h2>
      <p className="mt-3 max-w-3xl text-sm leading-7">{body}</p>
      <div className="mt-5 flex flex-wrap gap-3">
        {primaryAction}
        {secondaryAction}
      </div>
    </section>
  );
}

function ReportPage({ sessions, onHydrateReport, onRemoveReport, onReuseSession, onUpsertReport, onUseSample }) {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [remoteSession, setRemoteSession] = useState(null);
  const [isFetchingRemote, setIsFetchingRemote] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [shareState, setShareState] = useState("idle");
  const [actionError, setActionError] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const session =
    sessions.find((item) => item.id === sessionId || item.reportId === sessionId) ||
    remoteSession ||
    null;
  const [filter, setFilter] = useState("all");
  const [selectedClaimId, setSelectedClaimId] = useState(null);
  const supportsNativeShare =
    typeof navigator !== "undefined" && typeof navigator.share === "function";
  const shareToken = searchParams.get("share");
  const matchingSession =
    sessions.find((item) => item.id === sessionId || item.reportId === sessionId) || null;

  useEffect(() => {
    setFilter("all");
  }, [sessionId]);

  useEffect(() => {
    let active = true;

    if (matchingSession && matchingSession.canManage && !shareToken) {
      setRemoteSession(null);
      setIsFetchingRemote(false);
      setFetchFailed(false);
      return () => {
        active = false;
      };
    }

    setIsFetchingRemote(true);
    setFetchFailed(false);

    fetchReport(sessionId, { shareToken })
      .then((report) => {
        if (!active) {
          return;
        }

        const recoveredSession = sessionFromReport(report);
        setRemoteSession(recoveredSession);
        onHydrateReport(report);
      })
      .catch(() => {
        if (!active) {
          return;
        }

        setFetchFailed(true);
      })
      .finally(() => {
        if (active) {
          setIsFetchingRemote(false);
        }
      });

    return () => {
      active = false;
    };
  }, [matchingSession, onHydrateReport, sessionId, shareToken]);

  const filteredResults = session ? session.results.filter((result) => matchesFilter(result, filter)) : [];

  useEffect(() => {
    if (!filteredResults.length) {
      setSelectedClaimId(null);
      return;
    }

    if (!filteredResults.some((result) => result.claim_id === selectedClaimId)) {
      setSelectedClaimId(filteredResults[0].claim_id);
    }
  }, [filteredResults, selectedClaimId]);

  const handleCopyShareLink = async () => {
    if (!session?.reportId) {
      return;
    }

    const shareUrl = getReportShareUrl(session.reportId, session.shareToken || shareToken);

    try {
      if (supportsNativeShare) {
        await navigator.share({
          title: "FactLens report",
          text: "Open this saved FactLens verification report.",
          url: shareUrl,
        });
        setShareState("shared");
        window.setTimeout(() => setShareState("idle"), 2000);
        return;
      }

      await navigator.clipboard.writeText(shareUrl);
      setShareState("copied");
      window.setTimeout(() => setShareState("idle"), 2000);
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      setShareState("failed");
      window.setTimeout(() => setShareState("idle"), 2000);
    }
  };

  const handleTogglePinned = async () => {
    if (!session?.reportId) {
      return;
    }

    setActionBusy(true);
    setActionError(null);

    try {
      const updated = await updateReport(session.reportId, {
        is_pinned: !session.isPinned,
      });
      const normalized = sessionFromReport(updated);
      setRemoteSession(normalized);
      onUpsertReport(updated);
    } catch {
      setActionError("The report pin state could not be updated.");
    } finally {
      setActionBusy(false);
    }
  };

  const handleToggleArchived = async () => {
    if (!session?.reportId) {
      return;
    }

    setActionBusy(true);
    setActionError(null);

    try {
      const updated = await updateReport(session.reportId, {
        is_archived: !session.isArchived,
      });
      const normalized = sessionFromReport(updated);
      setRemoteSession(normalized);
      onUpsertReport(updated);
    } catch {
      setActionError("The report archive state could not be updated.");
    } finally {
      setActionBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!session?.reportId) {
      return;
    }

    const confirmed = window.confirm("Delete this saved report permanently?");
    if (!confirmed) {
      return;
    }

    setActionBusy(true);
    setActionError(null);

    try {
      await deleteReport(session.reportId);
      onRemoveReport(session.reportId);
      navigate("/history");
    } catch {
      setActionError("The report could not be deleted.");
      setActionBusy(false);
    }
  };

  if (!session && (isFetchingRemote || !fetchFailed)) {
    return (
      <ReviewStateCard
        title="Loading saved report"
        body="FactLens is retrieving the report payload from the backend store."
      />
    );
  }

  if (!session && fetchFailed) {
    return (
      <ReviewStateCard
        title="No saved analysis matched this report ID."
        body="The local history may have been cleared, or this report has not been generated in the current browser yet."
        primaryAction={
          <Link
            to="/workspace"
            className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03]"
          >
            Open workspace
            <ArrowRight className="h-4 w-4" />
          </Link>
        }
        secondaryAction={
          <button
            type="button"
            onClick={() => onUseSample(sampleInputs[0])}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
          >
            Load sample
          </button>
        }
      />
    );
  }

  const selectedResult =
    filteredResults.find((result) => result.claim_id === selectedClaimId) || filteredResults[0] || null;
  const selectedClaim = session.claims.find((claim) => claim.id === selectedResult?.claim_id);

  return (
    <div className="space-y-6">
      <ReportOverview session={session} />

      {/* Action Toolbar */}
      <section className="flex flex-wrap gap-2 animate-fade-in-up delay-2">
        <button
          type="button"
          onClick={() => onReuseSession(session)}
          className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03]"
        >
          <RefreshCcw className="h-4 w-4" />
          Reuse input
        </button>
        {session.reportId && session.canManage ? (
          <button
            type="button"
            onClick={handleTogglePinned}
            disabled={actionBusy}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Pin className="h-4 w-4" />
            {session.isPinned ? "Unpin" : "Pin"}
          </button>
        ) : null}
        {session.reportId && session.canManage ? (
          <button
            type="button"
            onClick={handleToggleArchived}
            disabled={actionBusy}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Archive className="h-4 w-4" />
            {session.isArchived ? "Restore" : "Archive"}
          </button>
        ) : null}
        {session.reportId ? (
          <button
            type="button"
            onClick={handleCopyShareLink}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
          >
            <Link2 className="h-4 w-4" />
            {shareState === "shared"
              ? "Shared"
              : shareState === "copied"
                ? "Link copied"
                : shareState === "failed"
                  ? "Share failed"
                  : supportsNativeShare
                    ? "Share report"
                    : "Copy share link"}
          </button>
        ) : null}
        {session.reportId ? (
          <a
            href={getReportExportUrl(session.reportId, { shareToken: session.shareToken || shareToken })}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
          >
            <Download className="h-4 w-4" />
            JSON
          </a>
        ) : null}
        {session.reportId ? (
          <a
            href={getReportPdfExportUrl(session.reportId, { shareToken: session.shareToken || shareToken })}
            className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
          >
            <Download className="h-4 w-4" />
            PDF
          </a>
        ) : null}
        {session.reportId && session.canManage ? (
          <button
            type="button"
            onClick={handleDelete}
            disabled={actionBusy}
            className="inline-flex items-center gap-2 rounded-full border border-rose-400/15 bg-rose-500/8 px-4 py-2 text-sm font-medium text-rose-200 transition-all duration-300 hover:bg-rose-500/15 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Delete
          </button>
        ) : null}
        <Link
          to="/workspace"
          className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
        >
          Run another analysis
        </Link>
      </section>

      {actionError ? (
        <div className="rounded-[1.5rem] border border-rose-400/20 bg-rose-500/8 px-5 py-4 text-sm text-rose-200 glow-rose animate-fade-in">
          {actionError}
        </div>
      ) : null}

      <AuthenticitySignalsPanel
        aiDetection={session.aiDetection}
        mediaDetection={session.mediaDetection}
      />

      {session.status === "running" ? (
        <div className="space-y-4">
          <ReviewStateCard
            title="This analysis is still running."
            body="The report page is available immediately, but the pipeline has not finished retrieving and verifying every claim yet."
            primaryAction={
              <Link
                to="/workspace"
                className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-blue-100"
              >
                Return to workspace
                <ArrowRight className="h-4 w-4" />
              </Link>
            }
          />
          <PipelineProgress stage={session.pipelineStage} progress={session.progress} />
        </div>
      ) : null}

      {session.status === "error" ? (
        <ReviewStateCard
          title="This run stopped before the report was fully resolved."
          body={session.error || "An unexpected error interrupted the analysis."}
          tone="rose"
          primaryAction={
            <button
              type="button"
              onClick={() => onReuseSession(session)}
              className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-rose-100"
            >
              Reuse input in workspace
            </button>
          }
          secondaryAction={
            <Link
              to="/workspace"
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
            >
              Open workspace
            </Link>
          }
        />
      ) : null}

      {session.status === "done" && session.claims.length === 0 ? (
        <ReviewStateCard
          title="No verifiable claims were extracted from this input."
          body="The content may have been too narrative, too short, or too outline-like for the claim extractor to produce atomic facts."
          tone="amber"
          primaryAction={
            <button
              type="button"
              onClick={() => onReuseSession(session)}
              className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-amber-100"
            >
              Refine and rerun
            </button>
          }
          secondaryAction={
            <button
              type="button"
              onClick={() => onUseSample(sampleInputs[1])}
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
            >
              Load clean sample
            </button>
          }
        />
      ) : null}

      {session.status === "done" && session.claims.length > 0 && session.results.length === 0 ? (
        <ReviewStateCard
          title="Claims were extracted, but no completed verdicts were returned."
          body="This usually means retrieval or verification failed upstream after extraction."
          tone="amber"
          primaryAction={
            <button
              type="button"
              onClick={() => onReuseSession(session)}
              className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-amber-100"
            >
              Reuse input in workspace
            </button>
          }
        />
      ) : null}

      {session.results.length > 0 ? (
        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_320px]">
          <div className="xl:sticky xl:top-28 xl:self-start">
            <ClaimNavigator
              results={filteredResults}
              allResults={session.results}
              activeFilter={filter}
              onFilterChange={setFilter}
              selectedClaimId={selectedClaimId}
              onSelectClaimId={setSelectedClaimId}
            />
          </div>

          <div className="space-y-4">
            {filter !== "all" ? (
              <div className="glass-card rounded-[1.35rem] px-4 py-4 text-sm text-slate-300 animate-fade-in">
                Showing {filteredResults.length} claim{filteredResults.length === 1 ? "" : "s"} for the current filter.
              </div>
            ) : null}

            {selectedResult ? (
              <div className="space-y-4">
                <section className="glass-card-static rounded-[1.5rem] px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Selected claim</p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">Deep review view</h2>
                  <p className="mt-2 text-sm leading-7 text-slate-400">
                    Focus on a single claim, inspect its evidence, then move to the next claim from the navigator.
                  </p>
                </section>
                <ClaimCard
                  anchorId={`claim-${selectedResult.claim_id}`}
                  result={selectedResult}
                  claim={selectedClaim}
                />
              </div>
            ) : (
              <ReviewStateCard
                title="No claim is selected."
                body="Choose a claim from the navigator to inspect its verdict, risk flags, and supporting evidence."
              />
            )}
          </div>

          <div className="xl:sticky xl:top-28 xl:self-start">
            {selectedResult ? (
              <SourceTimeline result={selectedResult} />
            ) : (
              <div className="glass-card-static rounded-[1.75rem] p-5">
                <p className="text-sm text-slate-400">Select a claim to inspect its evidence rail.</p>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ReportPage;
