import { useState } from "react";
import { Camera, ChevronDown, ChevronUp, ImageOff } from "lucide-react";

const LABEL_META = {
  LIKELY_AI: {
    label: "Likely AI-generated Image",
    tone: "border-purple-400/20 bg-purple-500/8 text-purple-100",
    glow: "glow-purple",
    barColor: "from-purple-500 to-rose-400",
  },
  POSSIBLY_AI: {
    label: "Possibly AI-generated Image",
    tone: "border-orange-400/20 bg-orange-500/8 text-orange-100",
    glow: "glow-amber",
    barColor: "from-orange-500 to-amber-400",
  },
  LIKELY_HUMAN: {
    label: "Likely Authentic Photograph",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    barColor: "from-emerald-500 to-teal-400",
  },
  UNKNOWN: {
    label: "Image AI detection unavailable",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    barColor: "from-slate-500 to-slate-400",
  },
};

function MediaDetectionBadge({ mediaDetection }) {
  const [expanded, setExpanded] = useState(false);
  const meta = LABEL_META[mediaDetection.label] || LABEL_META.UNKNOWN;
  const Icon = mediaDetection.label === "LIKELY_HUMAN" ? Camera : ImageOff;
  const probability =
    typeof mediaDetection.ai_probability === "number"
      ? Math.round(mediaDetection.ai_probability * 100)
      : null;

  if (!mediaDetection.media_url && mediaDetection.label === "UNKNOWN") {
    return null;
  }

  return (
    <section className={`rounded-[1.5rem] border px-5 py-4 transition-all duration-300 ${meta.tone} ${meta.glow} animate-fade-in-up`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          {mediaDetection.media_url ? (
            <div className="scan-overlay h-16 w-24 shrink-0 overflow-hidden rounded-xl border border-white/15 bg-black/40 shadow-lg">
              <img src={mediaDetection.media_url} alt="Analyzed media" className="h-full w-full object-cover" />
            </div>
          ) : null}
          <div>
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4" />
              <p className="text-sm font-semibold">{meta.label}</p>
            </div>
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
          className="mt-2 inline-flex items-center gap-2 text-sm font-medium transition-all duration-200 hover:opacity-80 sm:mt-0"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          {expanded ? "Hide signals" : "Show signals"}
        </button>
      </div>

      {expanded ? (
        <div className="mt-4 rounded-2xl bg-black/15 px-4 py-3 text-sm animate-fade-in">
          <p>{mediaDetection.explanation}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(mediaDetection.signals_found || []).length ? (
              mediaDetection.signals_found.map((signal) => (
                <span key={signal} className="glass-pill rounded-full px-3 py-1 text-xs font-medium">
                  {signal}
                </span>
              ))
            ) : (
              <span className="text-sm opacity-75">No specific visual anomalies were noted.</span>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default MediaDetectionBadge;
