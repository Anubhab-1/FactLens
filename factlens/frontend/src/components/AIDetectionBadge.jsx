import { useState } from "react";
import { Bot, ChevronDown, ChevronUp, User } from "lucide-react";

const LABEL_META = {
  LIKELY_AI: {
    label: "Likely AI-generated",
    tone: "border-purple-400/20 bg-purple-500/8 text-purple-100",
    glow: "glow-purple",
    barColor: "from-purple-500 to-purple-400",
  },
  POSSIBLY_AI: {
    label: "Possibly AI-generated",
    tone: "border-amber-400/20 bg-amber-500/8 text-amber-100",
    glow: "glow-amber",
    barColor: "from-amber-500 to-amber-400",
  },
  LIKELY_HUMAN: {
    label: "Likely human-written",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    barColor: "from-emerald-500 to-emerald-400",
  },
  UNKNOWN: {
    label: "AI detection unavailable",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    barColor: "from-slate-500 to-slate-400",
  },
};

function AIDetectionBadge({ aiDetection }) {
  const [expanded, setExpanded] = useState(false);
  const meta = LABEL_META[aiDetection.label] || LABEL_META.UNKNOWN;
  const Icon = aiDetection.label === "LIKELY_HUMAN" ? User : Bot;
  const probability =
    typeof aiDetection.ai_probability === "number"
      ? Math.round(aiDetection.ai_probability * 100)
      : null;

  return (
    <section className={`rounded-[1.5rem] border px-5 py-4 transition-all duration-300 ${meta.tone} ${meta.glow} animate-fade-in-up`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-black/20 ring-1 ring-inset ring-white/10">
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold">{meta.label}</p>
            <div className="mt-1.5 flex items-center gap-3">
              <div className="h-1.5 w-24 overflow-hidden rounded-full bg-black/20">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${meta.barColor} transition-all duration-700`}
                  style={{ width: `${probability ?? 0}%` }}
                />
              </div>
              <span className="font-mono text-xs opacity-80">
                {probability !== null ? `${probability}%` : "N/A"}
              </span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className="inline-flex items-center gap-2 text-sm font-medium transition-all duration-200 hover:opacity-80"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          {expanded ? "Hide signals" : "Show signals"}
        </button>
      </div>

      {expanded ? (
        <div className="mt-4 rounded-2xl bg-black/15 px-4 py-3 text-sm animate-fade-in">
          <p>{aiDetection.explanation}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(aiDetection.signals_found || []).length ? (
              aiDetection.signals_found.map((signal) => (
                <span key={signal} className="glass-pill rounded-full px-3 py-1 text-xs font-medium">
                  {signal}
                </span>
              ))
            ) : (
              <span className="text-sm opacity-75">No specific signals were returned.</span>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default AIDetectionBadge;
