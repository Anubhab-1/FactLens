import { ArrowRight, BookOpenText, Clock3, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";

import AccuracyReport from "../components/AccuracyReport";
import AuthenticitySignalsPanel from "../components/AuthenticitySignalsPanel";
import InputPanel from "../components/InputPanel";
import PipelineProgress from "../components/PipelineProgress";
import SessionCard from "../components/SessionCard";
import { sampleInputs } from "../data/sampleInputs";
import { getReportRouteId } from "../lib/sessions";

function WorkspacePage({
  inputMode,
  setInputMode,
  inputValue,
  setInputValue,
  onSubmit,
  activeSession,
  sessions,
  onUseSample,
  onReuseSession,
}) {
  const isLoading = activeSession?.status === "running";
  const recentSessions = sessions.slice(0, 3);
  const hasResults = activeSession?.results.length > 0;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_330px]">
      <div className="space-y-6">
        <section className="glass-card-static rounded-[1.75rem] px-6 py-5 animate-fade-in-up">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Workspace</p>
          <div className="mt-3 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="text-3xl font-semibold text-white">Run a new verification pass</h1>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-400">
                Start with pasted text or a URL. Completed runs are saved so reports can be reopened and shared.
              </p>
            </div>
            <Link
              to="/methodology"
              className="glass-pill inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-slate-300 transition-all duration-300 hover:bg-white/10 hover:text-white"
            >
              <BookOpenText className="h-4 w-4" />
              How scoring works
            </Link>
          </div>
        </section>

        <InputPanel
          inputMode={inputMode}
          setInputMode={setInputMode}
          inputValue={inputValue}
          setInputValue={setInputValue}
          onSubmit={onSubmit}
          isLoading={isLoading}
        />

        <AuthenticitySignalsPanel
          aiDetection={activeSession?.aiDetection}
          mediaDetection={activeSession?.mediaDetection}
        />

        {activeSession?.error ? (
          <section className="rounded-[1.75rem] border border-rose-400/20 bg-rose-500/8 px-5 py-5 text-rose-200 glow-rose animate-fade-in-up">
            <h2 className="text-xl font-semibold text-white">The latest run stopped before completion.</h2>
            <p className="mt-3 text-sm leading-7">{activeSession.error}</p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={onSubmit}
                className="btn-shimmer rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-rose-100"
              >
                Retry current input
              </button>
              <button
                type="button"
                onClick={() => onUseSample(sampleInputs[1])}
                className="glass-pill rounded-full px-4 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-white/10"
              >
                Load clean sample
              </button>
            </div>
          </section>
        ) : null}

        {isLoading ? (
          <PipelineProgress stage={activeSession.pipelineStage} progress={activeSession.progress} />
        ) : null}

        {!activeSession ? (
          <section className="glass-card rounded-[1.75rem] border-dashed px-5 py-5 text-sm leading-7 text-slate-400 animate-fade-in-up">
            Start with a sample or paste a passage. The first successful run will be saved automatically and opened as a report.
          </section>
        ) : null}

        {activeSession?.status === "done" ? (
          <div className="rounded-[1.75rem] border border-emerald-400/20 bg-emerald-500/8 px-5 py-4 text-sm text-emerald-200 glow-emerald animate-fade-in-up">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p>The report is ready and saved.</p>
              <Link
                to={`/report/${getReportRouteId(activeSession)}`}
                className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 font-semibold text-slate-950 transition-all duration-300 hover:bg-emerald-100"
              >
                Open saved report
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        ) : null}

        {!isLoading && !activeSession?.error && activeSession?.pipelineStage === "done" && activeSession.claims.length === 0 ? (
          <section className="rounded-[1.75rem] border border-amber-400/20 bg-amber-500/8 px-5 py-5 text-amber-200 glow-amber animate-fade-in-up">
            <h2 className="text-xl font-semibold text-white">No verifiable claims were extracted.</h2>
            <p className="mt-3 text-sm leading-7">
              The input may have been too narrative, too sparse, or too outline-like for the extractor to produce atomic facts.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onUseSample(sampleInputs[1])}
                className="btn-shimmer rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-amber-100"
              >
                Load clean sample
              </button>
            </div>
          </section>
        ) : null}

        {!isLoading &&
        !activeSession?.error &&
        activeSession?.pipelineStage === "done" &&
        activeSession.claims.length > 0 &&
        activeSession.results.length === 0 ? (
          <section className="rounded-[1.75rem] border border-amber-400/20 bg-amber-500/8 px-5 py-5 text-sm text-amber-200 glow-amber animate-fade-in-up">
            <h2 className="text-xl font-semibold text-white">Claims were extracted, but the report did not fully resolve.</h2>
            <p className="mt-3 leading-7">
              This usually means upstream model or retrieval failures interrupted verification after extraction.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={onSubmit}
                className="btn-shimmer rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-amber-100"
              >
                Retry current input
              </button>
            </div>
          </section>
        ) : null}

        {hasResults ? (
          <section className="space-y-4 animate-fade-in-up">
            <div className="glass-card-static rounded-[1.75rem] px-5 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Workspace preview</p>
              <h2 className="mt-2 text-2xl font-semibold text-white">Claim map preview</h2>
              <p className="mt-2 text-sm leading-7 text-slate-400">
                Quick preview while you work. The dedicated report page gives a cleaner single-claim review flow.
              </p>
              <div className="mt-5">
                <Link
                  to={`/report/${getReportRouteId(activeSession)}`}
                  className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03]"
                >
                  Open full report
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
            <AccuracyReport results={activeSession.results} claims={activeSession.claims} />
          </section>
        ) : null}
      </div>

      <div className="space-y-6">
        <section className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up delay-2">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Starter kits</p>
          <div className="mt-4 space-y-3">
            {sampleInputs.map((sample, index) => (
              <button
                key={sample.id}
                type="button"
                onClick={() => onUseSample(sample)}
                disabled={isLoading}
                className={`group w-full rounded-[1.25rem] border border-white/6 bg-white/4 px-4 py-4 text-left transition-all duration-300 hover:border-blue-400/20 hover:bg-white/8 disabled:cursor-not-allowed disabled:opacity-50 animate-fade-in-up delay-${index + 3}`}
              >
                <p className="text-sm font-semibold text-white group-hover:text-blue-200 transition-colors">{sample.label}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">{sample.description}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up delay-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Platform capabilities</p>
          <div className="mt-4 space-y-3">
            <div className="glass-card rounded-[1.2rem] px-4 py-4">
              <Clock3 className="h-4 w-4 text-amber-300" />
              <p className="mt-3 text-sm font-semibold text-white">Persistent reports</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Analyses are persisted by the backend so history survives refreshes.
              </p>
            </div>
            <div className="glass-card rounded-[1.2rem] px-4 py-4">
              <Sparkles className="h-4 w-4 text-blue-300" />
              <p className="mt-3 text-sm font-semibold text-white">Multi-page experience</p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Home, workspace, report, history, and methodology pages give the product a clear structure.
              </p>
            </div>
          </div>
        </section>

        <section className="space-y-4 animate-fade-in-up delay-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Recent analyses</p>
            <Link to="/history" className="text-sm font-medium text-blue-300 transition-all duration-300 hover:text-blue-200">
              View all
            </Link>
          </div>
          {recentSessions.length ? (
            recentSessions.map((session) => (
              <SessionCard key={session.id} session={session} onReuseSession={onReuseSession} />
            ))
          ) : (
            <div className="glass-card rounded-[1.5rem] border-dashed px-4 py-5 text-sm leading-7 text-slate-400">
              Completed analyses will appear after the first successful run.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default WorkspacePage;
