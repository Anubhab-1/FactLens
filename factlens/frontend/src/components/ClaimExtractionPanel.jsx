import { AlertTriangle, CheckCircle2, Cpu, FileWarning, PencilRuler, SearchCode } from "lucide-react";

const MODE_META = {
  llm: {
    title: "Model-drafted claims",
    tone: "border-emerald-400/20 bg-emerald-500/8 text-emerald-100",
    glow: "glow-emerald",
    Icon: CheckCircle2,
  },
  heuristic: {
    title: "Heuristic fallback draft",
    tone: "border-amber-400/20 bg-amber-500/8 text-amber-100",
    glow: "glow-amber",
    Icon: SearchCode,
  },
  manual_review: {
    title: "Human-reviewed claims",
    tone: "border-blue-400/20 bg-blue-500/8 text-blue-100",
    glow: "glow-blue",
    Icon: PencilRuler,
  },
  outline_blocked: {
    title: "Outline-like input",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    Icon: FileWarning,
  },
  failed: {
    title: "Extraction failed",
    tone: "border-rose-400/20 bg-rose-500/8 text-rose-100",
    glow: "glow-rose",
    Icon: AlertTriangle,
  },
  pending: {
    title: "Extraction pending",
    tone: "border-slate-400/15 bg-slate-500/8 text-slate-200",
    glow: "glow-slate",
    Icon: Cpu,
  },
};

function formatMode(mode) {
  return MODE_META[mode] || MODE_META.pending;
}

function SourceBadge({ claimExtraction }) {
  if (!claimExtraction?.provider_label && !claimExtraction?.provider && !claimExtraction?.source_mode) {
    return null;
  }

  const providerLabel = claimExtraction.provider_label || claimExtraction.provider;

  return (
    <div className="flex flex-wrap gap-2">
      {providerLabel ? (
        <span className="glass-pill rounded-full px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
          {providerLabel}
        </span>
      ) : null}
      {claimExtraction.model ? (
        <span className="glass-pill max-w-full break-all rounded-full px-3 py-1 text-xs text-slate-300">
          {claimExtraction.model}
        </span>
      ) : null}
      {claimExtraction.source_mode ? (
        <span className="rounded-full bg-white/8 px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-300">
          Draft source: {claimExtraction.source_mode.replace(/_/g, " ")}
        </span>
      ) : null}
    </div>
  );
}

function ClaimExtractionPanel({ claimExtraction }) {
  if (!claimExtraction) {
    return null;
  }

  const meta = formatMode(claimExtraction.mode);
  const Icon = meta.Icon;
  const warnings = Array.isArray(claimExtraction.warnings) ? claimExtraction.warnings : [];

  return (
    <section className={`rounded-[1.75rem] border px-5 py-5 animate-fade-in-up ${meta.tone} ${meta.glow}`}>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-black/15 ring-1 ring-inset ring-white/8">
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] opacity-80">Claim extraction</p>
              <h3 className="mt-1 text-xl font-semibold text-white">{meta.title}</h3>
            </div>
          </div>

          <p className="mt-4 text-sm leading-7 opacity-90">
            {claimExtraction.mode === "llm"
              ? "The initial claim draft came from a language model and can be reviewed before verification."
              : claimExtraction.mode === "heuristic"
                ? "FactLens could not use an LLM for extraction, so it generated a heuristic draft. Treat these claims as untrusted until reviewed."
                : claimExtraction.mode === "manual_review"
                  ? "The claims that entered verification were manually reviewed. This is the most trustworthy path when the draft looked weak or ambiguous."
                  : claimExtraction.mode === "outline_blocked"
                    ? "The input looked more like headings than prose, so FactLens did not guess at atomic claims."
                    : "FactLens stopped before generating a trustworthy automatic draft."}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-black/15 px-3 py-1.5 text-xs uppercase tracking-[0.18em] text-white/80 ring-1 ring-inset ring-white/8">
            {claimExtraction.claim_count || 0} claim{claimExtraction.claim_count === 1 ? "" : "s"}
          </span>
          <SourceBadge claimExtraction={claimExtraction} />
        </div>
      </div>

      {claimExtraction.error ? (
        <div className="mt-4 rounded-[1.2rem] border border-white/10 bg-black/10 px-4 py-3 text-sm leading-7 text-white/90">
          {claimExtraction.error}
        </div>
      ) : null}

      {warnings.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {warnings.map((warning) => (
            <span key={warning} className="max-w-full rounded-[1rem] bg-black/15 px-3 py-2 text-xs leading-6 text-white/85 ring-1 ring-inset ring-white/8">
              {warning}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export default ClaimExtractionPanel;
