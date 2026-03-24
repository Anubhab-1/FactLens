import { ArrowRight, BookOpenText, Clock3, Eye, ShieldCheck, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import SessionCard from "../components/SessionCard";
import { sampleInputs } from "../data/sampleInputs";

// ─── Feature data ───────────────────────────────────────────────────
const FEATURES = [
  {
    icon: ShieldCheck,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    title: "Trust-aware scoring",
    desc: "Authority, freshness, conflict, and date visibility are built into every verdict.",
  },
  {
    icon: Clock3,
    color: "text-amber-400",
    bg: "bg-amber-400/10",
    title: "Time-sensitive flags",
    desc: "Claims are downgraded automatically when evidence is undated or stale.",
  },
  {
    icon: Eye,
    color: "text-blue-400",
    bg: "bg-blue-400/10",
    title: "AI & media signals",
    desc: "Detects AI-generated text and synthetic-media risk in embedded imagery.",
  },
];

const PIPELINE_STEPS = [
  { n: "01", title: "Extract", desc: "Atomic, verifiable statements are isolated using LLM extraction." },
  { n: "02", title: "Search",  desc: "Multiple query strategies target diverse, authoritative sources."  },
  { n: "03", title: "Verify",  desc: "Evidence is triaged, verdicts calibrated, flags surfaced clearly." },
];

// ─── Subcomponents ───────────────────────────────────────────────────
function FeatureCard({ icon: Icon, color, bg, title, desc, delay }) {
  return (
    <div className={`glass-card p-5 space-y-4 animate-fade-in-up ${delay}`}>
      <span className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${bg}`}>
        <Icon className={`h-4 w-4 ${color}`} />
      </span>
      <div>
        <p className="text-sm font-semibold text-white">{title}</p>
        <p className="mt-1.5 text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>{desc}</p>
      </div>
    </div>
  );
}

function StepCard({ n, title, desc, delay }) {
  return (
    <div className={`glass-card p-5 space-y-3 animate-fade-in-up ${delay}`}>
      <span
        className="font-mono text-xs font-bold"
        style={{ color: "var(--ink-3)", letterSpacing: "0.1em" }}
      >
        {n}
      </span>
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>{desc}</p>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function HomePage({ sessions, onUseSample, onReuseSession }) {
  const recentSessions = sessions.slice(0, 3);

  return (
    <div className="page-wrapper space-y-16 animate-fade-in">

      {/* ── Hero ──────────────────────────────────────────────────── */}
      <section className="grid gap-14 lg:grid-cols-[1fr_360px] lg:items-start">
        {/* Left */}
        <div className="space-y-8">
          <div className="animate-fade-in-up">
            <span className="label-cap">AI-powered fact verification</span>
            <h1
              className="mt-4 text-5xl font-extrabold text-white sm:text-6xl lg:text-7xl animate-fade-in-up delay-1"
              style={{ lineHeight: "1", letterSpacing: "-0.04em" }}
            >
              <span className="shimmer-text">Verify any claim.</span><br />
              <span className="text-gradient-nebula inline-block mt-2">Transparently.</span>
            </h1>
            <p
              className="mt-6 text-lg leading-relaxed max-w-xl animate-fade-in-up delay-2"
              style={{ color: "var(--ink-2)" }}
            >
              FactLens extracts atomic claims, searches across authoritative
              sources, and explains every verdict with full source traceability.
            </p>
          </div>

          <div className="flex flex-wrap gap-3 animate-fade-in-up delay-3">
            <Link to="/workspace" className="btn-primary btn-shimmer text-sm">
              <Zap className="h-4 w-4 shrink-0 fill-current" />
              Open Workspace
              <ArrowRight className="h-4 w-4 shrink-0" />
            </Link>
            <Link to="/demo" className="btn-secondary text-sm">
              <Sparkles className="h-4 w-4 shrink-0" />
              Try the demo
            </Link>
            <Link to="/methodology" className="btn-secondary text-sm">
              <BookOpenText className="h-4 w-4 shrink-0" />
              Methodology
            </Link>
          </div>

          {/* Features grid */}
          <div className="grid gap-4 sm:grid-cols-3 animate-fade-in-up delay-4">
            {FEATURES.map((f, i) => (
              <FeatureCard key={f.title} {...f} delay={`delay-${i + 4}`} />
            ))}
          </div>
        </div>

        {/* Right — Sample inputs */}
        <div className="glass-card-static p-5 space-y-4 animate-fade-in-up delay-3">
          <span className="label-cap">Try a sample</span>
          <div className="space-y-2.5">
            {sampleInputs.map((sample, i) => (
              <button
                key={sample.id}
                type="button"
                onClick={() => onUseSample(sample)}
                className={`glass-card group w-full p-4 text-left animate-fade-in-up delay-${i + 4}`}
              >
                <p className="text-sm font-semibold text-white group-hover:text-blue-300 transition-colors">
                  {sample.label}
                </p>
                <p className="mt-1 text-sm leading-relaxed" style={{ color: "var(--ink-2)" }}>
                  {sample.description}
                </p>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* ── Pipeline + Recent runs ─────────────────────────────────── */}
      <section className="grid gap-8 lg:grid-cols-[1fr_400px]">
        {/* Pipeline */}
        <div className="glass-card-static p-7 space-y-6 animate-fade-in-up delay-2">
          <div>
            <span className="label-cap">How it works</span>
            <h2 className="mt-3 text-2xl font-bold text-white">From raw input to verified report</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {PIPELINE_STEPS.map((s, i) => (
              <StepCard key={s.n} {...s} delay={`delay-${i + 3}`} />
            ))}
          </div>
        </div>

        {/* Recent runs */}
        <div className="glass-card-static p-7 space-y-5 animate-fade-in-up delay-3">
          <div>
            <span className="label-cap">Recent runs</span>
            <h2 className="mt-3 text-xl font-bold text-white">Your latest analyses</h2>
          </div>
          <div className="space-y-3">
            {recentSessions.length ? (
              recentSessions.map((session) => (
                <SessionCard
                  key={session.id}
                  session={session}
                  onReuseSession={onReuseSession}
                />
              ))
            ) : (
              <div
                className="rounded-2xl border border-dashed p-8 text-center text-sm"
                style={{ borderColor: "var(--border-faint)", color: "var(--ink-3)" }}
              >
                Your completed analyses will appear here.
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ── Demo CTA ──────────────────────────────────────────────── */}
      <section className="glass-card-static p-8 animate-fade-in-up delay-4">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2 min-w-0">
            <span className="label-cap">Presentation mode</span>
            <h2 className="text-2xl font-bold text-white">Scenario deck for demos</h2>
            <p className="text-sm leading-relaxed max-w-2xl" style={{ color: "var(--ink-2)" }}>
              Curated demo packs for clean truth, mixed verdicts, time-sensitive claims,
              and live URLs — follow a deliberate narrative in any presentation.
            </p>
          </div>
          <Link to="/demo" className="btn-primary btn-shimmer shrink-0 text-sm">
            Open demo
            <ArrowRight className="h-4 w-4 shrink-0" />
          </Link>
        </div>
      </section>

    </div>
  );
}

export default HomePage;
