import { AlertTriangle, BookOpenText, Cpu, ShieldCheck, TimerReset, Zap } from "lucide-react";

const STEPS = [
  {
    icon: BookOpenText,
    iconColor: "from-blue-500 to-blue-600",
    title: "1. Atomic Extraction",
    description: "Complex documents are decomposed into discrete, verifiable 'claims'. This eliminates ambiguity and ensures every verdict is traceable to a specific statement.",
  },
  {
    icon: ShieldCheck,
    iconColor: "from-emerald-500 to-emerald-600",
    title: "2. Weighted Evidence",
    description: "Sources aren't just 'found'—they are scored by authority, domain reputation, and independence. FactLens prioritizes official records over social echoes.",
  },
  {
    icon: Cpu,
    iconColor: "from-violet-500 to-violet-600",
    title: "3. Conflict Resolution",
    description: "When sources disagree, FactLens doesn't pick a side. It identifies the contradiction, alerts the user, and provides the context for both perspectives.",
  },
  {
    icon: TimerReset,
    iconColor: "from-amber-500 to-amber-600",
    title: "4. Temporal Awareness",
    description: "Information has a shelf life. FactLens identifies time-sensitive facts and flags results when evidence is stale or publication dates are missing.",
  },
];

function MethodologyPage() {
  return (
    <div className="space-y-12 pb-12">
      {/* ── Heading ─────────────────────────────────────────── */}
      <section className="animate-fade-in-up">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-400">Project Mission</p>
        <h1 className="mt-4 text-4xl md:text-5xl font-bold text-white tracking-tight">
          Restoring Trust in the <br />
          <span className="text-blue-500">AI-Generated Era.</span>
        </h1>
      </section>

      {/* ── Problem Statement ────────────────────────────────── */}
      <section className="grid gap-8 md:grid-cols-2 animate-fade-in-up delay-1">
        <div className="glass-card-static p-8 space-y-4 border-l-4 border-l-rose-500/50">
          <div className="flex items-center gap-3 text-rose-400">
            <AlertTriangle className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-wider">The Problem</span>
          </div>
          <h2 className="text-2xl font-bold text-white">The Truth Crisis</h2>
          <p className="text-sm leading-7 text-slate-400">
            The rapid proliferation of AI-generated content has led to a surge in 
            <span className="text-white"> LLM hallucinations</span> and digital misinformation. 
            Manually fact-checking every statement in dense documents is labor-intensive and unscalable. 
            Trust in digital news is at an all-time low.
          </p>
        </div>

        <div className="glass-card-static p-8 space-y-4 border-l-4 border-l-emerald-500/50">
          <div className="flex items-center gap-3 text-emerald-400">
            <Zap className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-wider">The Solution</span>
          </div>
          <h2 className="text-2xl font-bold text-white">Objective Verification</h2>
          <p className="text-sm leading-7 text-slate-400">
            FactLens is an <span className="text-white">AI-driven verification engine</span> that 
            validates text integrity against real-time data. It doesn't just give an answer—it shows 
            its work, citing exact sources and providing a traceable chain-of-thought for every verdict.
          </p>
        </div>
      </section>

      {/* ── Technical Pipeline ───────────────────────────────── */}
      <section className="space-y-8 animate-fade-in-up delay-2">
        <div className="text-center md:text-left">
          <h2 className="text-2xl font-bold text-white">The FactLens Engine</h2>
          <p className="mt-2 text-sm text-slate-400">
            How we transform raw noise into verified intelligence.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {STEPS.map((step, index) => (
            <div
              key={step.title}
              className={`glass-card-static rounded-[1.75rem] p-6 transition-all hover:bg-white/5 animate-fade-in-up`}
              style={{ animationDelay: `${(index + 3) * 0.1}s` }}
            >
              <div className={`inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br ${step.iconColor} shadow-lg mb-4`}>
                <step.icon className="h-6 w-6 text-white" />
              </div>
              <h3 className="text-lg font-bold text-white">{step.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-slate-400">{step.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Target Impact ────────────────────────────────────── */}
      <section className="glass-card-static p-10 text-center space-y-6 rounded-[2.5rem] bg-gradient-to-b from-blue-500/5 to-transparent animate-fade-in-up delay-5">
        <h2 className="text-3xl font-bold text-white italic tracking-tight">"Truth is the only compliance that matters."</h2>
        <div className="flex flex-wrap justify-center gap-8 pt-4">
          <div className="space-y-1">
            <p className="text-2xl font-bold text-blue-400">100%</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Traceability</p>
          </div>
          <div className="space-y-1">
            <p className="text-2xl font-bold text-blue-400">Live</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Web Retrieval</p>
          </div>
          <div className="space-y-1">
            <p className="text-2xl font-bold text-blue-400">AI</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Hallucination Shield</p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default MethodologyPage;

