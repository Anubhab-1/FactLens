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
  LIKELY_AI: {
    label: "Likely AI-generated image",
    tone: "border-fuchsia-400/20 bg-fuchsia-500/8 text-fuchsia-100",
    glow: "glow-purple",
    barColor: "from-fuchsia-500 to-rose-400",
    Icon: ImageOff,
  },
  POSSIBLY_AI: {
    label: "Possibly AI-generated image",
    tone: "border-orange-400/20 bg-orange-500/8 text-orange-100",
    glow: "glow-amber",
    barColor: "from-orange-500 to-amber-400",
    Icon: ImageOff,
  },
  LIKELY_HUMAN: {
    label: "Likely authentic photograph",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    barColor: "from-emerald-500 to-teal-400",
    Icon: Camera,
  },
  UNKNOWN: {
    label: "Visual authenticity unavailable",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    barColor: "from-slate-500 to-slate-400",
    Icon: Camera,
  },
};

function SignalCard({ title, detection, metaMap, imagePreview = false }) {
  const meta = metaMap[detection?.label] || metaMap.UNKNOWN;
  const Icon = meta.Icon;
  const probability =
    typeof detection?.ai_probability === "number"
      ? Math.round(detection.ai_probability * 100)
      : null;

  return (
    <article className={`rounded-[1.5rem] border p-4 transition-all duration-300 sm:p-5 ${meta.tone} ${meta.glow} animate-fade-in-up`}>
      <div className="flex gap-3 sm:gap-4">
        {imagePreview && detection?.media_url ? (
          <div className="scan-overlay h-14 w-20 shrink-0 overflow-hidden rounded-xl border border-white/15 bg-black/30 shadow-lg sm:h-16 sm:w-24">
            <img src={detection.media_url} alt="Analyzed media" className="h-full w-full object-cover" />
          </div>
        ) : (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-black/15 ring-1 ring-inset ring-white/8 sm:h-11 sm:w-11">
            <Icon className="h-5 w-5" />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-75">{title}</p>
          <p className="mt-1.5 text-sm font-semibold sm:mt-2">{meta.label}</p>
          <div className="mt-2 flex items-center gap-3">
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-black/20 sm:w-24">
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

      {detection?.explanation ? (
        <p className="mt-4 text-sm leading-6 opacity-85">{detection.explanation}</p>
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
    </article>
  );
}

function AuthenticitySignalsPanel({ aiDetection, mediaDetection }) {
  const hasMediaSignal =
    mediaDetection && (mediaDetection.media_url || mediaDetection.label !== "UNKNOWN");

  if (!aiDetection && !hasMediaSignal) {
    return null;
  }

  return (
    <section className="glass-card-static rounded-[1.75rem] p-4 animate-fade-in-up sm:p-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Authenticity signals</p>
        <h3 className="mt-2 text-xl font-semibold text-white sm:text-2xl">Context signals, not truth verdicts</h3>
        <p className="mt-2 text-sm leading-7 text-slate-400">
          These checks estimate whether the submitted text or media looks machine-generated. They help frame risk, but they do not determine factual accuracy on their own.
        </p>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        {aiDetection ? (
          <SignalCard title="Submitted text" detection={aiDetection} metaMap={AI_META} />
        ) : null}
        {hasMediaSignal ? (
          <SignalCard title="Detected article media" detection={mediaDetection} metaMap={MEDIA_META} imagePreview />
        ) : null}
      </div>
    </section>
  );
}

export default AuthenticitySignalsPanel;
