import { useState } from "react";
import { ArrowRight, BookOpenText, ChevronRight, Search } from "lucide-react";
import { Link } from "react-router-dom";

import AccuracyReport from "../components/AccuracyReport";
import AuthenticitySignalsPanel from "../components/AuthenticitySignalsPanel";
import ClaimExtractionPanel from "../components/ClaimExtractionPanel";
import ClaimReviewPanel from "../components/ClaimReviewPanel";
import ClaimTracePanel from "../components/ClaimTracePanel";
import InputPanel from "../components/InputPanel";
import PipelineProgress from "../components/PipelineProgress";
import SessionCard from "../components/SessionCard";
import SourceCapturePanel from "../components/SourceCapturePanel";
import { sampleInputs } from "../data/sampleInputs";
import { getReportRouteId } from "../lib/sessions";

const SAMPLE_INPUTS = sampleInputs;

function WorkspacePage({
  inputMode, setInputMode,
  inputValue, setInputValue,
  onSubmit, onReviewClaims,
  activeSession, claimDraft,
  isPreparingDraft, isSubmittingReviewedClaims,
  onUpdateDraftClaim, onAddDraftClaim, onRemoveDraftClaim,
  onDiscardDraft, onVerifyReviewedClaims,
  sessions, onUseSample, onReuseSession,
}) {
  const [selectedClaimId, setSelectedClaimId] = useState(null);

  const isLoading = activeSession?.status === "running" || activeSession?.status === "processing";
  const hasResults  = (activeSession?.results?.length ?? 0) > 0;
  const hasReviewDraft = claimDraft?.status === "ready";
  const previewState   = hasReviewDraft ? claimDraft : activeSession;
  const recentSessions = sessions.slice(0, 4);

  const handleApplySample = (sample) => {
    setInputMode(sample.mode ?? "text");
    setInputValue(sample.value ?? "");
  };

  return (
    <div className="page-wrapper animate-fade-in">
      {/* ── Page header ────────────────────────────────────────── */}
      <header className="mb-10 space-y-3">
        <span className="label-cap">Workspace</span>
        <h1 className="text-4xl font-extrabold text-white sm:text-5xl" style={{ letterSpacing: "-0.03em" }}>
          Fact-check anything.
        </h1>
        <p className="max-w-xl text-base leading-relaxed" style={{ color: "var(--ink-2)" }}>
          Paste text, a URL, or a YouTube link. FactLens will extract atomic claims and verify them
          against cross-referenced primary sources.
        </p>
      </header>

      {/* ── Two-column layout ─────────────────────────────────── */}
      <div className="grid gap-10 lg:grid-cols-[1fr_340px]">

        {/* ── Main Column ──────────────────────────────────────── */}
        <div className="min-w-0 space-y-8">

          {/* Input Hub */}
          <InputPanel
            inputMode={inputMode}
            inputValue={inputValue}
            setInputMode={setInputMode}
            setInputValue={setInputValue}
            onSubmit={onSubmit}
            onReviewClaims={onReviewClaims}
            isLoading={isLoading}
            isReviewLoading={isPreparingDraft}
          />

          {/* Error: draft failed */}
          {claimDraft?.status === "error" && (
            <div className="glass-card-static rounded-2xl border border-rose-500/20 bg-rose-500/8 p-6 space-y-3 animate-fade-in-up">
              <div className="flex items-center gap-2.5">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                <p className="text-sm font-semibold text-rose-400">Draft Generation Failed</p>
              </div>
              <p className="text-sm leading-relaxed break-words" style={{ color: "var(--ink-2)" }}>
                {claimDraft.error}
              </p>
              {inputMode === "url" && inputValue && (
                <div className="space-y-2 pt-1">
                  <p className="text-xs" style={{ color: "var(--ink-3)" }}>
                    The URL may be paywalled, JS-rendered, or blocked. You can paste the article text directly instead.
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      setInputMode("text");
                      setInputValue("");
                    }}
                    className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-white transition-all hover:bg-white/15"
                  >
                    Switch to text mode →
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Error: analysis interrupted */}
          {!hasReviewDraft && activeSession?.status === "error" && (
            <div className="glass-card-static rounded-2xl border border-rose-500/20 bg-rose-500/8 p-6 space-y-3 animate-fade-in-up">
              <div className="flex items-center gap-2.5">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                <p className="text-sm font-semibold text-rose-400">Analysis Interrupted</p>
              </div>
              <p className="text-sm leading-relaxed break-words" style={{ color: "var(--ink-2)" }}>
                {activeSession.error}
              </p>
              <button
                onClick={onSubmit}
                className="text-xs font-semibold"
                style={{ color: "var(--ink-3)", letterSpacing: "0.05em" }}
              >
                Try again →
              </button>
            </div>
          )}

          {/* Claim review */}
          {hasReviewDraft && (
            <div className="animate-fade-in">
              <ClaimReviewPanel
                draft={claimDraft}
                onUpdateClaim={onUpdateDraftClaim}
                onAddClaim={onAddDraftClaim}
                onRemoveClaim={onRemoveDraftClaim}
                onVerifyReviewedClaims={onVerifyReviewedClaims}
                onDiscardDraft={onDiscardDraft}
                isSubmitting={isSubmittingReviewedClaims}
              />
            </div>
          )}

          {/* Authenticity panels */}
          {previewState && (
            <div className="space-y-5 animate-fade-in">
              <AuthenticitySignalsPanel
                aiDetection={previewState.aiDetection}
                mediaDetection={previewState.mediaDetection}
              />
              <SourceCapturePanel
                sourceCapture={previewState.sourceCapture}
                inputMode={previewState.inputMode ?? inputMode}
              />
              {previewState.claimExtraction && (
                <ClaimExtractionPanel claimExtraction={previewState.claimExtraction} />
              )}
            </div>
          )}

          {/* Claim trace */}
          {previewState?.sourceText && (previewState?.claims?.length ?? 0) > 0 && (
            <ClaimTracePanel
              sourceText={previewState.sourceText}
              claims={previewState.claims}
              selectedClaimId={selectedClaimId}
              onSelectClaimId={setSelectedClaimId}
              isTruncated={previewState.sourceTextTruncated}
            />
          )}

          {/* Pipeline progress */}
          {isLoading && activeSession?.pipelineStage && (
            <div className="space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <span className="label-cap">Pipeline active</span>
                <span className="label-cap animate-pulse" style={{ color: "var(--blue-400)" }}>
                  processing…
                </span>
              </div>
              <PipelineProgress stage={activeSession.pipelineStage} progress={activeSession.progress} />
            </div>
          )}

          {/* Completion banner */}
          {!hasReviewDraft && activeSession?.status === "done" && (
            <div className="glass-card-static flex items-center justify-between gap-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/8 p-5 animate-fade-in-up">
              <div>
                <p className="text-sm font-semibold text-emerald-400">Verification complete</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--ink-3)" }}>
                  Report has been synthesized and indexed.
                </p>
              </div>
              <Link
                to={`/report/${getReportRouteId(activeSession)}`}
                className="btn-primary text-xs shrink-0"
              >
                View report <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          )}

          {/* Live preview strip */}
          {!hasReviewDraft && hasResults && (
            <section className="space-y-4 animate-fade-in">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">Live Preview</h3>
                <Link
                  to={`/report/${getReportRouteId(activeSession)}`}
                  className="text-xs font-semibold text-blue-400 hover:underline"
                >
                  Fullscreen report →
                </Link>
              </div>
              <AccuracyReport results={activeSession.results} claims={activeSession.claims} />
            </section>
          )}
        </div>

        {/* ── Sidebar ──────────────────────────────────────────── */}
        <aside className="min-w-0 space-y-8">

          {/* Quick presets */}
          <div className="glass-card-static p-5 space-y-4">
            <span className="label-cap">Quick presets</span>
            <div className="space-y-2">
              {SAMPLE_INPUTS.map((sample, i) => (
                <button
                  key={i}
                  onClick={() => handleApplySample(sample)}
                  className="glass-card group w-full p-4 text-left animate-fade-in-up"
                  style={{ animationDelay: `${i * 0.05}s` }}
                >
                  <p className="text-xs font-semibold text-white group-hover:text-blue-300 transition-colors">
                    {sample.label}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed break-words" style={{ color: "var(--ink-3)" }}>
                    {sample.description}
                  </p>
                </button>
              ))}
            </div>
          </div>

          {/* Recent passes */}
          <div className="glass-card-static p-5 space-y-4">
            <div className="flex items-center justify-between">
              <span className="label-cap">Recent passes</span>
              <Link to="/history" className="text-[10px] font-bold text-blue-500 hover:underline uppercase tracking-wider">
                All →
              </Link>
            </div>
            <div className="space-y-2.5">
              {recentSessions.length > 0 ? (
                recentSessions.map((s) => (
                  <SessionCard key={s.id} session={s} onReuseSession={onReuseSession} compact />
                ))
              ) : (
                <p className="rounded-xl border border-dashed p-6 text-center text-xs" style={{ borderColor: "var(--border-faint)", color: "var(--ink-3)" }}>
                  No passes yet
                </p>
              )}
            </div>
          </div>

          {/* Methodology link */}
          <Link
            to="/methodology"
            className="glass-card group flex items-start gap-4 p-5"
          >
            <BookOpenText className="h-5 w-5 shrink-0 text-blue-400 mt-0.5" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors">
                Scientific methodology
              </p>
              <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--ink-3)" }}>
                Learn how the retrieval engine generates credibility scores.
              </p>
            </div>
            <ArrowRight className="h-4 w-4 shrink-0 self-center text-white/20 group-hover:text-blue-400 transition-colors" />
          </Link>
        </aside>
      </div>
    </div>
  );
}

export default WorkspacePage;
