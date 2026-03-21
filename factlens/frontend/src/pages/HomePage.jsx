import { ArrowRight, BookOpenText, Clock3, Eye, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";

import SessionCard from "../components/SessionCard";
import { sampleInputs } from "../data/sampleInputs";

function FeatureCard({ icon: Icon, iconColor, title, description, delay }) {
  return (
    <div className={`glass-card rounded-[1.4rem] px-5 py-5 animate-fade-in-up ${delay}`}>
      <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${iconColor} shadow-lg`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <p className="mt-4 text-sm font-semibold text-white">{title}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
    </div>
  );
}

function HomePage({ sessions, onUseSample, onReuseSession }) {
  const recentSessions = sessions.slice(0, 2);

  return (
    <div className="space-y-6">
      {/* Hero Section */}
      <section className="glass-card-static overflow-hidden rounded-[2rem] p-8 gradient-border animate-fade-in-up">
        <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_360px] xl:items-start">
          <div>
            <p className="animate-fade-in-up delay-1 text-xs font-semibold uppercase tracking-[0.3em] text-blue-300">
              AI-Powered Verification Engine
            </p>
            <h1 className="animate-fade-in-up delay-2 mt-5 max-w-3xl font-display text-5xl leading-tight text-white sm:text-6xl">
              Turn any text into an{" "}
              <span className="text-gradient">evidence-backed</span>{" "}
              claim report.
            </h1>
            <p className="animate-fade-in-up delay-3 mt-5 max-w-2xl text-base leading-8 text-slate-300">
              FactLens extracts claims, searches the web for corroborating and conflicting sources,
              flags stale evidence, detects AI-generated content, and explains every verdict with full transparency.
            </p>

            <div className="animate-fade-in-up delay-4 mt-8 flex flex-wrap gap-3">
              <Link
                to="/workspace"
                className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-all duration-300 hover:shadow-xl hover:shadow-blue-500/30 hover:scale-[1.03]"
              >
                <Zap className="h-4 w-4" />
                Open workspace
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/methodology"
                className="glass-pill inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-slate-200 transition-all duration-300 hover:bg-white/10 hover:text-white"
              >
                <BookOpenText className="h-4 w-4" />
                Review methodology
              </Link>
            </div>

            <div className="mt-10 grid gap-4 md:grid-cols-3">
              <FeatureCard
                icon={ShieldCheck}
                iconColor="from-emerald-500 to-emerald-600"
                title="Trust-aware scoring"
                description="Authority, freshness, conflict, and date visibility are built into the core verdict logic."
                delay="delay-3"
              />
              <FeatureCard
                icon={Clock3}
                iconColor="from-amber-500 to-amber-600"
                title="Time-sensitive warnings"
                description="Claims that look current or contested are downgraded when the evidence is undated or stale."
                delay="delay-4"
              />
              <FeatureCard
                icon={Eye}
                iconColor="from-blue-500 to-purple-500"
                title="AI & Deepfake detection"
                description="Detects AI-generated text and analyzes embedded images for synthetic manipulation signals."
                delay="delay-5"
              />
            </div>
          </div>

          <div className="glass-card rounded-[1.75rem] p-5 animate-fade-in-up delay-3">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Try a sample</p>
            <div className="mt-4 space-y-3">
              {sampleInputs.map((sample, index) => (
                <button
                  key={sample.id}
                  type="button"
                  onClick={() => onUseSample(sample)}
                  className={`group w-full rounded-[1.35rem] border border-white/6 bg-white/4 px-4 py-4 text-left transition-all duration-300 hover:border-blue-400/20 hover:bg-white/8 hover:shadow-lg hover:shadow-blue-950/10 animate-fade-in-up delay-${index + 4}`}
                >
                  <p className="text-sm font-semibold text-white group-hover:text-blue-200 transition-colors">{sample.label}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{sample.description}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* How it works + Recent Runs */}
      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="glass-card-static rounded-[2rem] p-6 animate-fade-in-up delay-2">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">How the pipeline works</p>
          <h2 className="mt-3 text-3xl font-semibold text-white">From raw input to verified report</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[
              { step: "1", title: "Extract claims", desc: "Atomic, verifiable statements are isolated from the input text using LLM-driven extraction." },
              { step: "2", title: "Search & retrieve", desc: "Multiple query strategies per claim find diverse, authoritative, and time-appropriate sources." },
              { step: "3", title: "Verify & report", desc: "Evidence is triaged, verdicts are calibrated, and risk flags are surfaced transparently." },
            ].map((item, index) => (
              <div key={item.step} className={`glass-card rounded-[1.4rem] px-5 py-5 animate-fade-in-up delay-${index + 3}`}>
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 font-mono text-sm font-bold text-blue-300 ring-1 ring-inset ring-blue-400/20">
                  {item.step}
                </div>
                <p className="mt-4 text-sm font-semibold text-white">{item.title}</p>
                <p className="mt-2 text-sm leading-6 text-slate-400">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card-static rounded-[2rem] p-6 animate-fade-in-up delay-3">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Recent runs</p>
          <h2 className="mt-2 text-2xl font-semibold text-white">Recovered from saved reports</h2>
          <div className="mt-5 space-y-4">
            {recentSessions.length ? (
              recentSessions.map((session) => (
                <SessionCard key={session.id} session={session} onReuseSession={onReuseSession} />
              ))
            ) : (
              <div className="glass-card rounded-[1.4rem] border-dashed px-5 py-6 text-sm leading-7 text-slate-400">
                Your completed analyses will appear here after the first run.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export default HomePage;
