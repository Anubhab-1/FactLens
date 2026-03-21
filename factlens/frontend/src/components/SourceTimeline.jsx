import { Clock3, ExternalLink, Search } from "lucide-react";

const STANCE_META = {
  SUPPORT: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
  CONFLICT: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
  MIXED: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
  IRRELEVANT: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
};

function collectSources(result) {
  const byUrl = new Map();
  const evidenceBuckets = [
    ...(result.supporting_evidence || []),
    ...(result.conflicting_evidence || []),
    ...(result.mixed_evidence || []),
    ...(result.neutral_evidence || []),
  ];

  for (const source of evidenceBuckets) {
    if (!source.url) {
      continue;
    }

    const existing = byUrl.get(source.url);
    if (!existing || (source.overall_score || 0) > (existing.overall_score || 0)) {
      byUrl.set(source.url, source);
    }
  }

  return [...byUrl.values()].sort((left, right) => {
    if (left.published_label === "unknown" && right.published_label !== "unknown") {
      return 1;
    }
    if (left.published_label !== "unknown" && right.published_label === "unknown") {
      return -1;
    }
    if ((left.published_label || "") !== (right.published_label || "")) {
      return String(right.published_label || "").localeCompare(String(left.published_label || ""));
    }
    return (right.overall_score || 0) - (left.overall_score || 0);
  });
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-[1.1rem] border border-white/6 bg-white/4 px-3 py-3">
      <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function SourceTimeline({ result }) {
  const sources = collectSources(result);
  const retrievalSummary = result.retrieval_summary || {};

  return (
    <div className="space-y-5 animate-slide-in-right">
      <section className="glass-card-static rounded-[1.75rem] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Evidence rail</p>
        <h3 className="mt-2 text-xl font-semibold text-white">Source timeline</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <MetricCard label="Sources" value={retrievalSummary.source_count ?? 0} />
          <MetricCard label="Dated" value={retrievalSummary.dated_count ?? 0} />
          <MetricCard label="Domains" value={retrievalSummary.distinct_domain_count ?? 0} />
        </div>

        <div className="mt-5 space-y-3">
          {/* Timeline connector line */}
          <div className="relative">
            <div className="absolute left-5 top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/30 via-purple-500/20 to-transparent" />
            <div className="space-y-3">
              {sources.length ? (
                sources.slice(0, 6).map((source, index) => (
                  <article
                    key={source.url}
                    className={`glass-card relative ml-10 rounded-[1.2rem] px-4 py-4 animate-fade-in-up delay-${Math.min(index + 1, 6)}`}
                  >
                    {/* Timeline dot */}
                    <div className="absolute -left-[calc(2.5rem+4px)] top-5 h-2.5 w-2.5 rounded-full bg-blue-400 ring-2 ring-blue-400/20" />

                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em] ${STANCE_META[source.stance] || STANCE_META.IRRELEVANT}`}
                      >
                        {String(source.stance || "IRRELEVANT").replace(/_/g, " ")}
                      </span>
                      <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                        {source.domain || "unknown"}
                      </span>
                      <span className="glass-pill inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                        <Clock3 className="h-3 w-3" />
                        {source.published_label || "unknown"}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-semibold text-white">{source.title}</p>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-blue-300 transition-all duration-300 hover:text-blue-200"
                    >
                      <ExternalLink className="h-4 w-4" />
                      Open source
                    </a>
                  </article>
                ))
              ) : (
                <div className="ml-10 rounded-[1.2rem] border border-dashed border-white/8 bg-white/3 px-4 py-4 text-sm text-slate-400">
                  No evidence sources available yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {result.query_variants?.length ? (
        <section className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up delay-3">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-blue-300" />
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Search strategy</p>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {result.query_variants.map((query) => (
              <span
                key={`${query.objective}-${query.query}`}
                className="glass-pill rounded-full px-3 py-2 text-sm text-slate-300 transition-all duration-300 hover:bg-white/10 hover:text-white"
              >
                {query.query}
              </span>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default SourceTimeline;
