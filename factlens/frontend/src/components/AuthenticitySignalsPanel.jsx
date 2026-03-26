import { Bot, Camera, ImageOff, ShieldAlert, User } from "lucide-react";

const AI_META = {
  LIKELY_AI: {
    label: "Likely AI-generated text",
    tone: "border-purple-400/20 bg-purple-500/8 text-purple-100",
    glow: "glow-purple",
    barColor: "from-purple-500 to-purple-400",
    Icon: Bot,
  },
  POSSIBLY_AI: {
    label: "Possibly AI-generated text",
    tone: "border-amber-400/20 bg-amber-500/8 text-amber-100",
    glow: "glow-amber",
    barColor: "from-amber-500 to-amber-400",
    Icon: Bot,
  },
  LIKELY_HUMAN: {
    label: "Likely human-written text",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    barColor: "from-emerald-500 to-emerald-400",
    Icon: User,
  },
  UNKNOWN: {
    label: "Text authenticity unavailable",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    barColor: "from-slate-500 to-slate-400",
    Icon: ShieldAlert,
  },
};

const MEDIA_META = {
  LIKELY_SYNTHETIC: {
    label: "Likely synthetic-media signal",
    tone: "border-fuchsia-400/20 bg-fuchsia-500/8 text-fuchsia-100",
    glow: "glow-purple",
    barColor: "from-fuchsia-500 to-rose-400",
    Icon: ImageOff,
  },
  POSSIBLY_SYNTHETIC: {
    label: "Possible synthetic-media signal",
    tone: "border-orange-400/20 bg-orange-500/8 text-orange-100",
    glow: "glow-amber",
    barColor: "from-orange-500 to-amber-400",
    Icon: ImageOff,
  },
  NO_STRONG_SIGNAL: {
    label: "No strong synthetic-media signal",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    barColor: "from-emerald-500 to-teal-400",
    Icon: Camera,
  },
  UNKNOWN: {
    label: "Visual media review unavailable",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    barColor: "from-slate-500 to-slate-400",
    Icon: Camera,
  },
};

function formatAnalysisMode(value) {
  const labels = {
    text_llm_stylistic_review: "Stylistic LLM review",
    specialized_classifier: "Specialized classifier",
    disabled: "Disabled",
    unavailable: "Unavailable",
    none: "No media",
  };
  return labels[value] || String(value || "Unavailable").replace(/_/g, " ");
}

function SignalCard({ title, detection, metaMap, imagePreview = false, compact = false }) {
  const meta = metaMap[detection?.label] || metaMap.UNKNOWN;
  const Icon = meta.Icon;
  const probability =
    typeof detection?.ai_probability === "number"
      ? Math.round(detection.ai_probability * 100)
      : null;

  return (
    <article
      className={`glass-card-inner-glow rounded-[1.5rem] border p-4 transition-all duration-300 ${
        compact ? "sm:p-4" : "sm:p-5"
      } ${meta.tone} ${meta.glow} animate-fade-in-up`}
    >
      <div className="flex gap-3 sm:gap-4">
        {imagePreview && detection?.media_url ? (
          <div
            className={`scan-overlay shrink-0 overflow-hidden rounded-xl border border-white/15 bg-black/30 shadow-lg ${
              compact ? "h-12 w-[4.5rem] sm:h-14 sm:w-20" : "h-14 w-20 sm:h-16 sm:w-24"
            }`}
          >
            <img src={detection.media_url} alt="Analyzed media" className="h-full w-full object-cover" />
          </div>
        ) : (
          <div
            className={`flex shrink-0 items-center justify-center rounded-2xl bg-black/15 ring-1 ring-inset ring-white/8 ${
              compact ? "h-9 w-9 sm:h-10 sm:w-10" : "h-10 w-10 sm:h-11 sm:w-11"
            }`}
          >
            <Icon className="h-5 w-5" />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-75">{title}</p>
          <p className="mt-1.5 text-sm font-semibold sm:mt-2">{meta.label}</p>
          <div className="mt-2 flex items-center gap-3">
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-black/20 sm:w-24">
              <div
                className={`h-full rounded-full bg-gradient-to-r ${meta.barColor} transition-all duration-700 ease-out shadow-[0_0_8px_rgba(255,255,255,0.1)]`}
                style={{ width: `${probability ?? 0}%` }}
              />
            </div>
            <span className="font-mono text-[10px] font-bold opacity-60 tabular-nums">
              {probability !== null ? `${probability}%` : "N/A"}
            </span>
          </div>
        </div>
      </div>

      {detection?.explanation ? (
        <p className="mt-4 text-sm leading-6 opacity-85">{detection.explanation}</p>
      ) : null}

      {(detection?.analysis_mode || detection?.provider_label || detection?.model) ? (
        <div className="mt-4 rounded-2xl border border-white/8 bg-black/10 px-4 py-3 text-sm">
          <p className="label-cap !text-[9px] opacity-60">Review method</p>
          <p className="mt-2 leading-6 opacity-90">
            {formatAnalysisMode(detection?.analysis_mode)}
            {detection?.provider_label ? ` via ${detection.provider_label}` : ""}
            {detection?.model ? ` (${detection.model})` : ""}
          </p>
          {typeof detection?.review_recommended === "boolean" ? (
            <p className="mt-2 text-xs uppercase tracking-[0.18em] opacity-70">
              {detection.review_recommended ? "Human review recommended" : "No extra review suggested"}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {(detection?.signals_found || []).length ? (
          detection.signals_found.map((signal) => (
            <span key={signal} className="glass-pill rounded-full px-3 py-1 text-xs font-medium">
              {signal}
            </span>
          ))
        ) : (
          <span className="text-xs uppercase tracking-[0.18em] opacity-60">No specific signals returned</span>
        )}
      </div>

      {(detection?.warnings || []).length ? (
        <div className="mt-4 rounded-2xl border border-amber-400/15 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-white/80">Warnings</p>
          <div className="mt-2 space-y-2">
            {detection.warnings.map((warning) => (
              <p key={warning} className="leading-6">
                {warning}
              </p>
            ))}
          </div>
        </div>
      ) : null}

      {(detection?.limitations || []).length ? (
        <div className="mt-4 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-slate-300">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">Limitations</p>
          <div className="mt-2 space-y-2">
            {detection.limitations.map((item) => (
              <p key={item} className="leading-6">
                {item}
              </p>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function AuthenticitySignalsPanel({ aiDetection, mediaDetection, compact = false }) {
  const hasMediaSignal =
    mediaDetection && (mediaDetection.media_url || mediaDetection.label !== "UNKNOWN");
  const signalCount = Number(Boolean(aiDetection)) + Number(Boolean(hasMediaSignal));

  if (!aiDetection && !hasMediaSignal) {
    return null;
  }

  return (
    <section className="glass-card-static glass-card-inner-glow rounded-[1.75rem] p-5 animate-fade-in-up sm:p-7">
      <div className="space-y-3">
        <p className="label-cap">Authenticity Analysis</p>
        <h3 className="text-2xl font-bold text-white sm:text-3xl tracking-tight">Context signals, not truth verdicts</h3>
        <p className="mt-2 text-sm leading-7 text-slate-400">
          These checks estimate whether the submitted text or media looks machine-generated. They help frame risk, but they do not determine factual accuracy on their own, and visual-media analysis only runs when a specialized classifier is available.
        </p>
      </div>

      <div
        data-testid="authenticity-signals-layout"
        className={`mt-5 ${compact || signalCount < 2 ? "space-y-4" : "grid gap-4 lg:grid-cols-2"}`}
      >
        {aiDetection ? (
          <SignalCard
            title="Submitted text"
            detection={aiDetection}
            metaMap={AI_META}
            compact={compact}
          />
        ) : null}
        {hasMediaSignal ? (
          <SignalCard
            title="Detected article media"
            detection={mediaDetection}
            metaMap={MEDIA_META}
            imagePreview
            compact={compact}
          />
        ) : null}
      </div>
    </section>
  );
}

export default AuthenticitySignalsPanel;
