import { BookOpenText, ShieldCheck, TimerReset, TriangleAlert } from "lucide-react";

const STEPS = [
  {
    icon: BookOpenText,
    iconColor: "from-blue-500 to-blue-600",
    title: "1. Claim extraction",
    description: "Long passages are broken into independently verifiable statements so each verdict is traceable to a single claim.",
  },
  {
    icon: ShieldCheck,
    iconColor: "from-emerald-500 to-emerald-600",
    title: "2. Source scoring",
    description: "Sources are weighted by authority, relevance, recency, and domain diversity before they influence final calibration.",
  },
  {
    icon: TimerReset,
    iconColor: "from-amber-500 to-amber-600",
    title: "3. Freshness safeguards",
    description: "Time-sensitive claims are penalized when relevant evidence is stale or when publication dates cannot be found.",
  },
  {
    icon: TriangleAlert,
    iconColor: "from-rose-500 to-rose-600",
    title: "4. Limits and caution",
    description: "A strong verdict is not a substitute for editorial judgment. Sparse evidence, source disagreement, and stale data all reduce confidence.",
  },
];

function MethodologyPage() {
  return (
    <div className="space-y-6">
      <section className="glass-card-static rounded-[2rem] p-6 animate-fade-in-up gradient-border">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Methodology</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">How FactLens reaches a verdict</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
          FactLens is designed to show its work. The product extracts atomic claims, generates search strategies,
          retrieves multiple sources, scores those sources, and then calibrates the verdict with explicit risk flags.
        </p>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        {STEPS.map((step, index) => (
          <section
            key={step.title}
            className={`glass-card rounded-[1.75rem] p-5 animate-fade-in-up delay-${index + 1}`}
          >
            <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${step.iconColor} shadow-lg`}>
              <step.icon className="h-5 w-5 text-white" />
            </div>
            <h2 className="mt-4 text-xl font-semibold text-white">{step.title}</h2>
            <p className="mt-3 text-sm leading-7 text-slate-400">{step.description}</p>
          </section>
        ))}
      </div>
    </div>
  );
}

export default MethodologyPage;
