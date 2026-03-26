import { Check, LoaderCircle } from "lucide-react";

const STEPS = [
  "Prepare input",
  "Extract claims",
  "Concurrent Verification",
  "Final Reflection",
  "Report ready",
];

function getActiveIndex(stage) {
  if (stage === "scraping" || stage === "detecting" || stage === "media_detecting") {
    return 0;
  }
  if (stage === "extracting") {
    return 1;
  }
  if (stage === "verifying") {
    return 2;
  }
  if (stage === "reflecting") {
    return 3;
  }
  if (stage === "done") {
    return 4;
  }
  return -1;
}

function getStatusMessage(stage, progress) {
  if (stage === "extracting") return "Identifying and refining atomic claims…";
  if (stage === "retrieving") return `Searching web & counter-evidence… (${progress.done}/${progress.total} claims)`;
  if (stage === "verifying") return `Concurrent web search & CoT verification… (${progress.done}/${progress.total} claims)`;
  if (stage === "reflecting") return "Performing session-wide consistency audit…";
  if (stage === "detecting") return "Running AI authorship analysis…";
  if (stage === "media_detecting") return "Reviewing extracted images for synthetic-media risk signals…";
  if (stage === "scraping") return "Fetching and cleaning article text…";
  if (stage === "done") return "Verification report ready.";
  return "Waiting to start…";
}

const AGENT_THOUGHTS = {
  extracting: [
    "Synthesizing core intents...",
    "Breaking down complex assertions...",
    "Normalizing claims for retrieval..."
  ],
  verifying: [
    "Cross-referencing multiple domains...",
    "Detecting temporal contradictions...",
    "Calibrating verdict based on source reputation...",
    "Isolating semantic drift in evidence...",
  ],
  reflecting: [
    "Auditing session-wide consistency...",
    "Resolving inter-claim dependencies...",
    "Finalizing grounded citations...",
  ]
};

function PipelineProgress({ stage, progress, liveQuery }) {
  const activeIndex = getActiveIndex(stage);
  const showTerminal = (stage === "retrieving" || stage === "verifying") && liveQuery;

  return (
    <section className="glass-card-static rounded-[2rem] px-6 py-6 animate-fade-in-up gradient-border">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {STEPS.map((step, index) => {
          const isComplete = activeIndex > index || (stage === "done" && index === 4);
          const isActive = activeIndex === index;

          return (
            <div key={step} className={`flex items-center gap-3 md:flex-col md:items-start animate-fade-in-up delay-${index + 1}`}>
              <div
                className={`flex h-11 w-11 items-center justify-center rounded-full border text-sm font-semibold transition-all duration-500 ${
                  isComplete
                    ? "border-emerald-400/30 bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/20 animate-scale-in"
                    : isActive
                      ? "border-blue-400/30 bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg shadow-blue-500/30 animate-pulse-glow"
                      : "border-white/8 bg-slate-900/50 text-slate-500"
                }`}
              >
                {isComplete ? (
                  <Check className="h-5 w-5" />
                ) : isActive ? (
                  <LoaderCircle className="h-5 w-5 animate-spin" />
                ) : (
                  <span className="font-mono">{index + 1}</span>
                )}
              </div>
              <div>
                <p className={`text-sm font-medium transition-colors duration-300 ${isComplete || isActive ? "text-white" : "text-slate-500"}`}>{step}</p>
                <p className={`text-xs transition-colors duration-300 ${isActive ? "text-blue-300" : "text-slate-500"}`}>
                  {isComplete ? "Complete" : isActive ? "In progress" : "Pending"}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Animated Progress Bar */}
      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-800/60">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 via-purple-500 to-emerald-500 transition-all duration-700 ease-out animate-gradient-flow"
          style={{ width: `${Math.min(((activeIndex + 1) / STEPS.length) * 100, 100)}%` }}
        />
      </div>

      {/* Live Retrieval Trace Terminal */}
      {showTerminal ? (
        <div className="mt-5 overflow-hidden rounded-xl border border-white/5 bg-black/40 font-mono animate-fade-in">
          <div className="flex items-center justify-between border-b border-white/5 bg-white/5 px-4 py-2">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-blue-400">Live Retrieval Trace</span>
            </div>
            <span className="text-[9px] text-white/20 uppercase tracking-tighter">Strategizing...</span>
          </div>
          <div className="p-4">
            <div className="flex items-start gap-3">
              <span className="mt-1 text-blue-500/50 leading-none">{">"}</span>
              <div className="space-y-1">
                <p className="text-xs leading-relaxed text-blue-100/90 italic drop-shadow-sm">
                  "{liveQuery}"
                </p>
                {AGENT_THOUGHTS[stage] && AGENT_THOUGHTS[stage].length > 0 && (
                  <p className="text-[9px] font-mono text-blue-400/60 animate-pulse">
                    Agent Process: {AGENT_THOUGHTS[stage][Math.floor((Date.now() / 3000) % AGENT_THOUGHTS[stage].length)]}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-4 glass-pill rounded-2xl px-4 py-3 text-sm text-slate-300">
          <span className="inline-flex items-center gap-2">
            {stage !== "done" ? <span className="flex h-2 w-2"><span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-blue-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" /></span> : null}
            {getStatusMessage(stage, progress)}
          </span>
        </div>
      )}
    </section>
  );
}

export default PipelineProgress;
