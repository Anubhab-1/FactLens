import { Gauge, Microscope, Search, ShieldAlert } from "lucide-react";

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "0%";
  }
  return `${Math.round(numeric * 100)}%`;
}

function formatMetric(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  return Number.isInteger(numeric) ? `${numeric}` : numeric.toFixed(1);
}

function formatMode(value) {
  return String(value || "unknown").replace(/_/g, " ");
}

function Metric({ label, value }) {
  return (
    <div className="rounded-[1.1rem] border border-white/6 bg-white/4 px-3 py-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function EvaluationPanel({ evaluation }) {
  if (!evaluation) {
    return null;
  }

  const summary = evaluation.summary || {};
  const extraction = evaluation.extraction || {};
  const retrieval = evaluation.retrieval || {};
  const verification = evaluation.verification || {};
  const contradictionTypes = Array.isArray(verification.contradiction_type_breakdown)
    ? verification.contradiction_type_breakdown
    : [];
  const qualityFlags = Array.isArray(evaluation.quality_flags) ? evaluation.quality_flags : [];

  return (
    <section className="glass-card-static rounded-[1.75rem] p-4 sm:p-5 space-y-5 animate-fade-in-up">
      <div className="space-y-1">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Run diagnostics</p>
        <h3 className="text-lg font-semibold text-white sm:text-xl">Calibration snapshot</h3>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        <Metric label="Claims" value={formatMetric(summary.total_claims)} />
        <Metric label="Avg conf." value={formatPercent(summary.average_confidence)} />
        <Metric label="Recovery" value={formatPercent(retrieval.recovery_rate)} />
        <Metric label="Conservative" value={formatPercent(summary.conservative_claim_rate)} />
      </div>

      <div className="space-y-3">
        <div className="rounded-[1.25rem] border border-white/6 bg-white/4 px-4 py-4">
          <div className="flex items-center gap-2">
            <Microscope className="h-4 w-4 text-blue-300" />
            <p className="text-sm font-semibold text-white">Extraction</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">
            <span className="glass-pill rounded-full px-3 py-1">Mode: {formatMode(extraction.mode)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Warnings: {formatMetric(extraction.warning_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Compound claims: {formatMetric(extraction.compound_claim_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Atomic rate: {formatPercent(extraction.atomic_claim_rate)}</span>
          </div>
        </div>

        <div className="rounded-[1.25rem] border border-white/6 bg-white/4 px-4 py-4">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-blue-300" />
            <p className="text-sm font-semibold text-white">Retrieval</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">
            <span className="glass-pill rounded-full px-3 py-1">Avg queries: {formatMetric(retrieval.avg_query_attempt_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Avg sources: {formatMetric(retrieval.avg_sources_per_claim)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Independent avg: {formatMetric(retrieval.avg_independent_source_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Provider instability: {formatMetric(retrieval.provider_instability_claim_count)}</span>
          </div>
        </div>

        <div className="rounded-[1.25rem] border border-white/6 bg-white/4 px-4 py-4">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-blue-300" />
            <p className="text-sm font-semibold text-white">Verification</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">
            <span className="glass-pill rounded-full px-3 py-1">Low confidence: {formatMetric(verification.low_confidence_claim_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">High confidence: {formatMetric(verification.high_confidence_claim_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Manual overrides: {formatMetric(verification.manual_override_claim_count)}</span>
            <span className="glass-pill rounded-full px-3 py-1">Reflection fixes: {formatMetric(verification.reflection_adjusted_claim_count)}</span>
          </div>
          {contradictionTypes.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {contradictionTypes.slice(0, 4).map((item) => (
                <span
                  key={item?.id || item?.label}
                  className="rounded-full bg-rose-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-rose-200 ring-1 ring-inset ring-rose-300/20"
                >
                  {item?.label || "Unknown"}: {formatMetric(item?.count)}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {qualityFlags.length ? (
        <div className="rounded-[1.25rem] border border-amber-400/15 bg-amber-500/8 px-4 py-4 text-sm text-amber-100">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0 text-amber-300" />
            <p className="font-semibold text-white">Evaluation flags</p>
          </div>
          <div className="mt-3 space-y-2">
            {qualityFlags.map((flag) => (
              <p key={flag} className="leading-6">{flag}</p>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default EvaluationPanel;
