import { Clock3, ExternalLink, Search } from "lucide-react";

const STANCE_META = {
  SUPPORT: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
  CONFLICT: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
  MIXED: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
  IRRELEVANT: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
};

function collectSources(result) {
  const byUrl = new Map();
  const evidenceBuckets = (result.evidence_used || []).length
    ? result.evidence_used
    : [
        ...(result.supporting_evidence || []),
        ...(result.conflicting_evidence || []),
        ...(result.mixed_evidence || []),
        ...(result.neutral_evidence || []),
      ];

  for (const source of evidenceBuckets) {
    if (!source.url) continue;
    const existing = byUrl.get(source.url);
    if (!existing || (source.overall_score || 0) > (existing.overall_score || 0)) {
      byUrl.set(source.url, source);
    }
  }

  return [...byUrl.values()].sort((left, right) => {
    if (left.published_label === "unknown" && right.published_label !== "unknown") return 1;
    if (left.published_label !== "unknown" && right.published_label === "unknown") return -1;
    if ((left.published_label || "") !== (right.published_label || "")) {
      return String(right.published_label || "").localeCompare(String(left.published_label || ""));
    }
    return (right.overall_score || 0) - (left.overall_score || 0);
  });
}

function MetricCard({ label, value }) {
  return (
    <div className="min-w-0 rounded-[1.1rem] border border-white/6 bg-white/4 px-3 py-2.5 sm:py-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 sm:text-[11px]">{label}</p>
      <p className="mt-1.5 font-mono text-base font-semibold text-white sm:mt-2 sm:text-lg">{value}</p>
    </div>
  );
}

function formatQueryObjective(value) {
  if (!value) {
    return "Query";
  }
  return String(value).replace(/_/g, " ");
}

function formatRecoveryStrategy(value) {
  const labels = {
    llm_planner: "LLM-planned recovery",
    llm_stop: "Planner stopped recovery",
    heuristic: "Heuristic recovery",
    heuristic_fallback: "Heuristic fallback",
    heuristic_after_llm: "Heuristic follow-up",
    heuristic_after_llm_stop: "Heuristic override after planner stop",
    not_needed: "No recovery needed",
    failed: "Recovery failed",
  };
  return labels[value] || String(value || "unknown").replace(/_/g, " ");
}

function formatAttemptStatus(value) {
  const normalized = String(value || "empty").toLowerCase();
  const labels = {
    ok: "usable",
    empty: "empty",
    error: "failed",
  };
  return labels[normalized] || normalized;
}

function formatSourceOrigin(value) {
  const origin = String(value || "").trim().toLowerCase();
  if (origin === "official") return "Official";
  if (origin === "first_party") return "First-party";
  if (origin === "reference") return "Reference";
  if (origin === "secondary") return "Secondary";
  if (origin === "social") return "Social";
  return "";
}

function temporalRiskMessage(result, retrievalSummary) {
  if (!result?.time_sensitive) {
    return "";
  }

  if (!retrievalSummary?.dated_count) {
    return "This claim is time-sensitive, but none of the relevant sources were date-stamped.";
  }

  if (retrievalSummary?.freshest_date === "unknown") {
    return "This claim is time-sensitive, but the freshest evidence date could not be established.";
  }

  return (
    (result?.risk_flags || []).find((flag) =>
      String(flag || "").toLowerCase().includes("time-sensitive"),
    ) || ""
  );
}

function SourceTimeline({ result }) {
  const sources = collectSources(result);
  const retrievalSummary = result.retrieval_summary || {};
  const conflictSummary = result.conflict_summary || {};
  const contradictionTypes = Array.isArray(conflictSummary.contradiction_types)
    ? conflictSummary.contradiction_types.filter(Boolean)
    : [];
  const recoveryPlannerNotes = String(retrievalSummary.recovery_planner_notes || "").trim();
  const recoveryReasons = Array.isArray(retrievalSummary.recovery_reason)
    ? retrievalSummary.recovery_reason.filter(Boolean)
    : [];
  const queryVariants = Array.isArray(result.query_variants) ? result.query_variants : [];
  const temporalRisk = temporalRiskMessage(result, retrievalSummary);

  return (
    <div className="space-y-5 animate-slide-in-right">
      <section className="glass-card-static rounded-[1.75rem] p-4 sm:p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Evidence rail</p>
        <h3 className="mt-2 text-lg font-semibold text-white sm:text-xl">Source timeline</h3>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
          <MetricCard label="Sources" value={retrievalSummary.source_count ?? 0} />
          <MetricCard label="Queries" value={retrievalSummary.query_attempt_count ?? queryVariants.length} />
          <MetricCard label="Dated" value={retrievalSummary.dated_count ?? 0} />
          <MetricCard label="Domains" value={retrievalSummary.distinct_domain_count ?? 0} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-400">
          <span className="glass-pill rounded-full px-3 py-1">
            Primary-preferred: {retrievalSummary.primary_source_count ?? 0}
          </span>
          <span className="glass-pill rounded-full px-3 py-1">
            Independent networks: {retrievalSummary.independent_source_count ?? 0}
          </span>
        </div>

        {temporalRisk ? (
          <div className="mt-4 rounded-[1.25rem] border border-rose-400/15 bg-rose-500/8 px-4 py-4 text-sm text-rose-100">
            <p className="font-semibold text-white">Temporal risk</p>
            <p className="mt-2 leading-6">{temporalRisk}</p>
          </div>
        ) : null}

        {retrievalSummary.failed_query_count ? (
          <div className="mt-4 rounded-[1.25rem] border border-white/8 bg-white/4 px-4 py-4 text-sm text-slate-300">
            <p className="font-semibold text-white">Provider instability</p>
            <p className="mt-2 leading-6">
              {retrievalSummary.failed_query_count} query attempt
              {retrievalSummary.failed_query_count === 1 ? "" : "s"} failed before FactLens found usable evidence.
            </p>
          </div>
        ) : null}

        {retrievalSummary.recovery_triggered ? (
          <div className="mt-4 rounded-[1.25rem] border border-amber-400/15 bg-amber-500/8 px-4 py-4 text-sm text-amber-100">
            <p className="font-semibold text-white">
              Recovery search triggered: {formatRecoveryStrategy(retrievalSummary.recovery_strategy)}
            </p>
            {recoveryReasons.length ? (
              <div className="mt-2 space-y-1.5">
                {recoveryReasons.map((reason) => (
                  <p key={reason} className="leading-6">{reason}</p>
                ))}
              </div>
            ) : null}
            {recoveryPlannerNotes ? (
              <p className="mt-2 leading-6">{recoveryPlannerNotes}</p>
            ) : null}
          </div>
        ) : null}

        {!retrievalSummary.recovery_triggered && retrievalSummary.recovery_strategy === "not_needed" ? (
          <div className="mt-4 rounded-[1.25rem] border border-emerald-400/15 bg-emerald-500/8 px-4 py-4 text-sm text-emerald-100">
            <p className="font-semibold text-white">First-pass retrieval was sufficient.</p>
            <p className="mt-2 leading-6">
              FactLens did not expand into a recovery search because the initial evidence passed its grounding checks.
            </p>
          </div>
        ) : null}

        {result.conflict_detected && conflictSummary.summary ? (
          <div className="mt-4 rounded-[1.25rem] border border-amber-400/15 bg-amber-500/8 px-4 py-4 text-sm text-amber-100">
            <p className="font-semibold text-white">Disagreement lens</p>
            <p className="mt-2 leading-6">{conflictSummary.summary}</p>
            {contradictionTypes.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {contradictionTypes.map((item) => (
                  <span
                    key={item?.id || item?.label}
                    className="rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-amber-100 ring-1 ring-inset ring-amber-300/20"
                  >
                    {item?.label || "Unknown conflict"}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-5 space-y-3">
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-px bg-gradient-to-b from-blue-500/30 via-purple-500/20 to-transparent sm:left-5" />
            <div className="space-y-3">
              {sources.length ? (
                sources.slice(0, 6).map((source, index) => (
                  <article
                    key={source.url}
                    className={`glass-card relative ml-8 rounded-[1.2rem] px-3 py-3 animate-fade-in-up sm:ml-10 sm:px-4 sm:py-4 delay-${Math.min(index + 1, 6)}`}
                  >
                    <div className="absolute -left-[calc(2rem+4px)] top-4 h-2.5 w-2.5 rounded-full bg-blue-400 ring-2 ring-blue-400/20 sm:-left-[calc(2.5rem+4px)] sm:top-5" />

                    <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] sm:px-2.5 sm:py-1 sm:text-[11px] ${STANCE_META[source.stance] || STANCE_META.IRRELEVANT}`}
                      >
                        {String(source.stance || "IRRELEVANT").replace(/_/g, " ")}
                      </span>
                      {formatSourceOrigin(source.source_origin) ? (
                        <span className="glass-pill rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-blue-300 sm:px-2.5 sm:py-1 sm:text-[11px]">
                          {formatSourceOrigin(source.source_origin)}
                        </span>
                      ) : null}
                      {Number(source.independence_group_size || 1) > 1 && Number(source.independence_weight || 1) < 1 ? (
                        <span className="glass-pill rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-amber-300 sm:px-2.5 sm:py-1 sm:text-[11px]">
                          Shared network
                        </span>
                      ) : null}
                      <span className="glass-pill rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-400 sm:px-2.5 sm:py-1 sm:text-[11px]">
                        {source.domain || "unknown"}
                      </span>
                      <span className="glass-pill inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-400 sm:px-2.5 sm:py-1 sm:text-[11px]">
                        <Clock3 className="h-3 w-3 shrink-0" />
                        {source.published_label || "unknown"}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-white sm:mt-3">{source.title}</p>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex items-center gap-2 text-sm font-medium text-blue-300 transition-all duration-300 hover:text-blue-200 sm:mt-3"
                    >
                      <ExternalLink className="h-4 w-4 shrink-0" />
                      Open source
                    </a>
                  </article>
                ))
              ) : (
                <div className="ml-8 rounded-[1.2rem] border border-dashed border-white/8 bg-white/3 px-4 py-4 text-sm text-slate-400 sm:ml-10">
                  No evidence sources available yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {queryVariants.length ? (
        <section className="glass-card-static rounded-[1.75rem] p-4 animate-fade-in-up delay-3 sm:p-5">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 shrink-0 text-blue-300" />
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Search strategy</p>
          </div>
          <div className="mt-4 space-y-3">
            {queryVariants.map((query) => (
              <div
                key={`${query.phase || "primary"}-${query.objective}-${query.query}`}
                className="glass-card rounded-[1.2rem] px-4 py-4 text-left text-sm text-slate-300"
              >
                <div className="flex flex-wrap gap-2">
                  <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {formatQueryObjective(query.objective)}
                  </span>
                  <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {query.phase === "recovery" ? "Recovery" : "Primary"}
                  </span>
                  {query.provider ? (
                    <span className="rounded-full bg-blue-500/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-blue-200 ring-1 ring-inset ring-blue-400/20">
                      {query.provider}
                    </span>
                  ) : null}
                  {query.status ? (
                    <span className="rounded-full bg-white/8 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-300">
                      {formatAttemptStatus(query.status)}
                    </span>
                  ) : null}
                  {query.planner ? (
                    <span className="glass-pill rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400">
                      {query.planner === "llm" ? "Planner" : "Fallback"}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1">{query.query}</p>
                {(query.warning || query.error) ? (
                  <p className="mt-2 text-xs leading-5 text-amber-200">
                    {query.error || query.warning}
                  </p>
                ) : null}
                {Array.isArray(query.provider_attempts) && query.provider_attempts.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {query.provider_attempts.map((attempt) => (
                      <span
                        key={`${query.query}-${attempt.provider}`}
                        className="rounded-full border border-white/8 bg-white/4 px-2.5 py-1 text-[11px] uppercase tracking-[0.18em] text-slate-400"
                      >
                        {attempt.provider}: {formatAttemptStatus(attempt.status)}
                        {typeof attempt.result_count === "number" ? ` (${attempt.result_count})` : ""}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default SourceTimeline;
