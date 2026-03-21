import { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Clock3,
  ExternalLink,
  Search,
  ShieldCheck,
} from "lucide-react";

const VERDICT_STYLES = {
  TRUE: {
    badge: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
    bar: "bg-gradient-to-r from-emerald-500 to-emerald-400",
    panel: "border-emerald-400/15 bg-emerald-500/8",
    glow: "glow-emerald",
  },
  FALSE: {
    badge: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
    bar: "bg-gradient-to-r from-rose-500 to-rose-400",
    panel: "border-rose-400/15 bg-rose-500/8",
    glow: "glow-rose",
  },
  PARTIALLY_TRUE: {
    badge: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
    bar: "bg-gradient-to-r from-amber-500 to-amber-400",
    panel: "border-amber-400/15 bg-amber-500/8",
    glow: "glow-amber",
  },
  UNVERIFIABLE: {
    badge: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
    bar: "bg-gradient-to-r from-slate-500 to-slate-400",
    panel: "border-slate-400/15 bg-slate-500/8",
    glow: "glow-slate",
  },
};

const QUERY_LABELS = {
  direct: "Direct query",
  authoritative: "Authority query",
  recency: "Recency query",
};

function formatScore(value) {
  if (typeof value !== "number") {
    return "0.00";
  }
  return value.toFixed(2);
}

function formatClaimType(value) {
  return String(value || "entity").replace(/_/g, " ");
}

function EvidenceMetric({ label, value }) {
  return (
    <div className="rounded-2xl border border-white/6 bg-white/4 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function EvidenceSection({ title, subtitle, items, tone }) {
  if (!items?.length) {
    return null;
  }

  return (
    <section className={`rounded-[1.35rem] border p-4 ${tone} animate-fade-in-up`}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-white">{title}</p>
          <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-300">{subtitle}</p>
        </div>
        <span className="glass-pill rounded-full px-3 py-1 text-xs font-medium text-white/80">
          {items.length} source{items.length > 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-3">
        {items.map((source) => (
          <article
            key={`${title}-${source.url}`}
            className="glass-card rounded-[1.2rem] p-4"
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold text-white">{source.title}</h4>
                  <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {source.domain || "unknown"}
                  </span>
                  <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {source.source_type || "web"}
                  </span>
                  {source.published_label ? (
                    <span className="glass-pill inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      <Clock3 className="h-3 w-3" />
                      {source.published_label}
                    </span>
                  ) : null}
                </div>

                <p className="mt-3 text-sm leading-6 text-slate-300">
                  {source.snippet_used || source.snippet || source.content}
                </p>

                {source.assessment_summary ? (
                  <p className="mt-3 text-sm leading-6 text-slate-400">{source.assessment_summary}</p>
                ) : null}
              </div>

              <div className="grid min-w-56 grid-cols-3 gap-2 rounded-2xl border border-white/6 bg-white/3 p-3">
                <EvidenceMetric label="Trust" value={formatScore(source.authority_score)} />
                <EvidenceMetric label="Match" value={formatScore(source.relevance_score)} />
                <EvidenceMetric label="Weight" value={formatScore(source.overall_score)} />
              </div>
            </div>

            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-blue-300 transition-all duration-300 hover:text-blue-200"
            >
              <ExternalLink className="h-4 w-4" />
              Open source
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}

function ClaimCard({ result, claim, anchorId }) {
  const [showReasoning, setShowReasoning] = useState(false);
  const verdictStyle = VERDICT_STYLES[result.verdict] || VERDICT_STYLES.UNVERIFIABLE;
  const confidenceWidth = Math.max(0, Math.min((result.confidence || 0) * 100, 100));
  const breakdown = result.confidence_breakdown || {};
  const retrievalSummary = result.retrieval_summary || {};
  const queryVariants = result.query_variants || [];
  const riskFlags = result.risk_flags || [];
  const originalContext = claim?.context?.trim();
  const showContext = originalContext && originalContext !== result.claim;
  const datedCount = retrievalSummary.dated_count ?? 0;
  const distinctDomainCount = retrievalSummary.distinct_domain_count ?? 0;
  const showTemporalGap = result.time_sensitive && datedCount === 0;

  return (
    <article
      id={anchorId}
      className={`glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up ${verdictStyle.glow}`}
    >
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] ${verdictStyle.badge}`}
            >
              {result.verdict.replace(/_/g, " ")}
            </span>
            <span className="glass-pill rounded-full px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate-400">
              {formatClaimType(result.claim_type)}
            </span>
            {result.time_sensitive ? (
              <span className="rounded-full bg-blue-500/12 px-3 py-1 text-xs uppercase tracking-[0.16em] text-blue-200 ring-1 ring-inset ring-blue-400/20">
                Time-sensitive
              </span>
            ) : null}
            {showTemporalGap ? (
              <span className="rounded-full bg-amber-500/12 px-3 py-1 text-xs uppercase tracking-[0.16em] text-amber-200 ring-1 ring-inset ring-amber-400/20">
                No dated evidence
              </span>
            ) : null}
          </div>

          <blockquote className="mt-5 border-l-2 border-blue-400/30 pl-4 text-base leading-7 text-slate-200">
            {result.claim}
          </blockquote>

          {showContext ? (
            <div className="mt-4 glass-card rounded-[1.2rem] px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">Original context</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">{originalContext}</p>
            </div>
          ) : null}
        </div>

        <div className="w-full max-w-sm glass-card rounded-[1.5rem] p-4">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
            <span>Confidence</span>
            <span className="font-mono">{Math.round((result.confidence || 0) * 100)}%</span>
          </div>
          <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-800/60">
            <div
              className={`h-full rounded-full transition-all duration-700 ${verdictStyle.bar}`}
              style={{ width: `${confidenceWidth}%` }}
            />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <EvidenceMetric label="Support" value={formatScore(breakdown.support_score)} />
            <EvidenceMetric label="Conflict" value={formatScore(breakdown.conflict_score)} />
            <EvidenceMetric label="Quality" value={formatScore(breakdown.source_quality)} />
            <EvidenceMetric label="Freshness" value={formatScore(breakdown.freshness)} />
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        <EvidenceMetric label="Sources" value={retrievalSummary.source_count ?? 0} />
        <EvidenceMetric label="Authoritative" value={retrievalSummary.authoritative_count ?? 0} />
        <EvidenceMetric label="Dated" value={datedCount} />
        <EvidenceMetric label="Domains" value={distinctDomainCount} />
        <EvidenceMetric label="Recent" value={retrievalSummary.recent_count ?? 0} />
        <EvidenceMetric label="Freshest" value={retrievalSummary.freshest_date || "unknown"} />
      </div>

      {showTemporalGap ? (
        <div className="mt-5 rounded-[1.35rem] border border-amber-400/15 bg-amber-500/8 px-4 py-4 text-sm text-amber-200 glow-amber">
          This claim is time-sensitive, but the retrieved evidence does not expose publication dates. Treat any positive verdict as provisional.
        </div>
      ) : null}

      {queryVariants.length ? (
        <section className="mt-5 glass-card rounded-[1.35rem] p-4">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-blue-300" />
            <p className="text-sm font-semibold text-white">Search strategy</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {queryVariants.map((query) => (
              <div
                key={`${query.objective}-${query.query}`}
                className="rounded-2xl border border-white/6 bg-white/3 px-3 py-2"
              >
                <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
                  {QUERY_LABELS[query.objective] || query.objective || "Query"}
                </p>
                <p className="mt-1 text-sm text-slate-300">{query.query}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="mt-5">
        <button
          type="button"
          onClick={() => setShowReasoning((previous) => !previous)}
          className="inline-flex items-center gap-2 text-sm font-medium text-blue-300 transition-all duration-300 hover:text-blue-200"
        >
          {showReasoning ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          {showReasoning ? "Hide reasoning" : "Show reasoning"}
        </button>

        {showReasoning ? (
          <p className="mt-3 glass-card rounded-2xl px-4 py-3 text-sm leading-7 text-slate-300 animate-fade-in">
            {result.reasoning}
          </p>
        ) : null}
      </div>

      {riskFlags.length ? (
        <section className={`mt-5 rounded-[1.35rem] border p-4 ${verdictStyle.panel}`}>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-300" />
            <p className="text-sm font-semibold text-white">Why this verdict could be wrong</p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {riskFlags.map((flag) => (
              <span
                key={flag}
                className="glass-pill rounded-full px-3 py-1 text-xs font-medium text-slate-200"
              >
                {flag}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {result.conflict_detected ? (
        <div className="mt-5 rounded-[1.35rem] border border-amber-400/15 bg-amber-500/8 px-4 py-4 text-sm text-amber-200 glow-amber">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" />
            <p className="font-medium">Conflicting evidence was detected across retrieved sources.</p>
          </div>
        </div>
      ) : null}

      <div className="mt-5 space-y-4">
        <EvidenceSection
          title="Supporting evidence"
          subtitle="Sources that directly reinforce the claim"
          items={result.supporting_evidence}
          tone="border-emerald-400/15 bg-emerald-500/6"
        />
        <EvidenceSection
          title="Conflicting evidence"
          subtitle="Sources that directly contradict the claim"
          items={result.conflicting_evidence}
          tone="border-rose-400/15 bg-rose-500/6"
        />
        <EvidenceSection
          title="Mixed evidence"
          subtitle="Sources that only support part of the claim"
          items={result.mixed_evidence}
          tone="border-amber-400/15 bg-amber-500/6"
        />
        <EvidenceSection
          title="Low-signal evidence"
          subtitle="Sources the model considered too vague or off-target"
          items={result.neutral_evidence}
          tone="border-slate-400/15 bg-slate-500/6"
        />
      </div>
    </article>
  );
}

export default ClaimCard;
