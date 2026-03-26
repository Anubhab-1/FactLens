import { useState } from "react";
import { ArrowRight, BookOpenText, ChevronRight, Search, Check, LoaderCircle } from "lucide-react";
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
import ApiHealthPanel from "../components/ApiHealthPanel";
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
      <header className="mb-12 space-y-4">
        <span className="label-cap">Workspace</span>
        <h1 className="text-4xl font-extrabold sm:text-6xl text-gradient-blue" style={{ letterSpacing: "-0.04em" }}>
          Fact-check anything.
        </h1>
        <p className="max-w-2xl text-base leading-relaxed sm:text-lg" style={{ color: "var(--ink-2)" }}>
          Paste text, a URL, or a YouTube link. FactLens will extract atomic claims and verify them
          against cross-referenced primary sources.
        </p>
      </header>

      {/* ── Two-column layout ─────────────────────────────────── */}
      <div className="grid gap-10 lg:grid-cols-[1fr_340px]">

        {/* ── Main Column ──────────────────────────────────────── */}
        <div className="min-w-0 space-y-12 relative">
          {/* subtle background glow for the main column */}
          <div className="absolute -top-20 -left-20 w-64 h-64 bg-blue-500/5 blur-[100px] pointer-events-none" />
          
          <section className="space-y-6">
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
          </section>

          {/* Error: draft failed */}
          {claimDraft?.status === "error" && (
            <div className="glass-card-static rounded-3xl border border-rose-500/20 bg-rose-500/10 p-8 space-y-4 animate-fade-in-up">
              <div className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
                <h3 className="text-sm font-bold text-rose-400 uppercase tracking-widest">Draft Generation Failed</h3>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>
                {claimDraft.error}
              </p>
              {inputMode === "url" && (
                <button
                  type="button"
                  onClick={() => { setInputMode("text"); setInputValue(""); }}
                  className="btn-secondary text-xs"
                >
                  Switch to text mode →
                </button>
              )}
            </div>
          )}

          {/* Analysis Active / Results */}
          {(hasReviewDraft || previewState) && (
            <div className="space-y-16 animate-fade-in">
              
              {/* Claim Review Suite */}
              {hasReviewDraft && (
                <div className="space-y-8">
                  <div className="flex items-center gap-4">
                    <span className="label-cap text-blue-400 shrink-0">Review Suite</span>
                    <div className="h-px w-full bg-gradient-to-r from-blue-400/20 to-transparent" />
                  </div>
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

              {/* Discovery Suite: Context and Authenticity */}
              {previewState && (
                <div className="space-y-8 relative">
                  <div className="absolute -right-20 top-0 w-48 h-48 bg-emerald-500/5 blur-[80px] pointer-events-none" />
                  <div className="flex items-center gap-4">
                    <span className="label-cap text-emerald-400 shrink-0">Discovery Suite</span>
                    <div className="h-px w-full bg-gradient-to-r from-emerald-400/20 to-transparent" />
                  </div>
                  <div className="grid gap-6">
                    <AuthenticitySignalsPanel
                      aiDetection={previewState.aiDetection}
                      mediaDetection={previewState.mediaDetection}
                    />
                    <SourceCapturePanel
                      sourceCapture={previewState.sourceCapture}
                      inputMode={previewState.inputMode ?? inputMode}
                    />
                  </div>
                </div>
              )}

              {/* Extraction & Trace Suite */}
              {previewState?.sourceText && (previewState?.claims?.length ?? 0) > 0 && (
                <div className="space-y-8">
                  <div className="flex items-center gap-4">
                    <span className="label-cap text-purple-400 shrink-0">Logic Suite</span>
                    <div className="h-px w-full bg-gradient-to-r from-purple-400/20 to-transparent" />
                  </div>
                  <div className="space-y-6">
                    {previewState.claimExtraction && (
                      <ClaimExtractionPanel claimExtraction={previewState.claimExtraction} />
                    )}
                    <ClaimTracePanel
                      sourceText={previewState.sourceText}
                      claims={previewState.claims}
                      selectedClaimId={selectedClaimId}
                      onSelectClaimId={setSelectedClaimId}
                      isTruncated={previewState.sourceTextTruncated}
                    />
                  </div>
                </div>
              )}

              {/* Verification Suite */}
              {(isLoading || hasResults) && (
                <div className="space-y-8 relative">
                  <div className="absolute -left-20 bottom-0 w-64 h-64 bg-blue-500/5 blur-[100px] pointer-events-none" />
                  <div className="flex items-center gap-4">
                    <span className="label-cap text-blue-400 shrink-0">Verification Suite</span>
                    <div className="h-px w-full bg-gradient-to-r from-blue-400/20 to-transparent" />
                  </div>
                  
                  <div className="space-y-8">
                    {/* Pipeline progress */}
                    {isLoading && activeSession?.pipelineStage && (
                      <div className="glass-card-static p-8 space-y-6">
                        <div className="flex items-center justify-between">
                          <h3 className="text-sm font-bold text-white uppercase tracking-widest">Pipeline Active</h3>
                          <span className="label-cap animate-pulse text-blue-400">processing…</span>
                        </div>
                        <PipelineProgress
                          stage={activeSession.pipelineStage}
                          progress={activeSession.progress}
                          liveQuery={activeSession.liveQuery}
                        />
                      </div>
                    )}

                    {/* Completion banner */}
                    {!hasReviewDraft && activeSession?.status === "done" && (
                      <div className="glass-card-static flex flex-col sm:flex-row items-center justify-between gap-6 rounded-[2.5rem] border border-emerald-500/20 bg-emerald-500/10 p-10 animate-fade-in-up relative overflow-hidden group">
                        {/* Animated background accent */}
                        <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/10 blur-[80px] -mr-32 -mt-32 animate-pulse" />
                        <div className="absolute bottom-0 left-0 w-32 h-32 bg-emerald-500/5 blur-[60px] -ml-16 -mb-16" />
                        
                        <div className="space-y-4 relative z-10 text-center sm:text-left">
                          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/20 border border-emerald-500/30">
                            <Check className="h-3 w-3 text-emerald-400" />
                            <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Protocol Success</span>
                          </div>
                          <div className="space-y-1">
                            <h3 className="text-2xl font-bold text-white">Consensus Reached</h3>
                            <p className="text-sm max-w-md leading-relaxed" style={{ color: "var(--ink-2)" }}>
                              The multi-agent validation protocol has finalized its audit. A high-fidelity consensus report is now available.
                            </p>
                          </div>
                        </div>
                        <Link
                          to={`/report/${getReportRouteId(activeSession)}`}
                          className="btn-primary btn-shimmer group-hover:scale-105 transition-transform text-sm px-8 py-4 shadow-emerald relative z-10"
                        >
                          Access Intelligence Report
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </div>
                    )}

                    {/* Live Preview / Accuracy Report */}
                    {hasResults && (
                      <div className="space-y-6">
                        <div className="flex items-center justify-between px-2">
                          <h3 className="text-lg font-bold text-white">Live Verification Insights</h3>
                          <Link
                            to={`/report/${getReportRouteId(activeSession)}`}
                            className="text-xs font-bold text-blue-400 hover:text-blue-300 transition-colors uppercase tracking-widest"
                          >
                            Fullscreen report →
                          </Link>
                        </div>
                        <AccuracyReport results={activeSession.results} claims={activeSession.claims} />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Sidebar ──────────────────────────────────────────── */}
        <aside className="min-w-0 space-y-8">
          
          <ApiHealthPanel />

          {/* Quick presets */}
          <div className="glass-card-static glass-card-inner-glow p-5 space-y-4">
            <span className="label-cap">Quick presets</span>
            <div className="space-y-2">
              {SAMPLE_INPUTS.map((sample, i) => (
                <button
                  key={i}
                  onClick={() => handleApplySample(sample)}
                  className="glass-card glass-card-inner-glow group w-full p-4 text-left animate-fade-in-up"
                  style={{ animationDelay: `${0.1 + i * 0.05}s` }}
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
          <div className="glass-card-static glass-card-inner-glow p-5 space-y-4 animate-fade-in-up" style={{ animationDelay: "0.3s" }}>
            <div className="flex items-center justify-between">
              <span className="label-cap">Recent passes</span>
              <Link to="/history" className="text-[10px] font-bold text-blue-500 hover:underline uppercase tracking-wider">
                All →
              </Link>
            </div>
            <div className="space-y-2.5">
              {recentSessions.length > 0 ? (
                recentSessions.map((s, i) => (
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
            className="glass-card glass-card-inner-glow group flex items-start gap-4 p-5 animate-fade-in-up"
            style={{ animationDelay: "0.4s" }}
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
