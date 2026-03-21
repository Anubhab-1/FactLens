const FILTERS = [
  { value: "all", label: "All" },
  { value: "TRUE", label: "True" },
  { value: "FALSE", label: "False" },
  { value: "PARTIALLY_TRUE", label: "Partial" },
  { value: "UNVERIFIABLE", label: "Unverifiable" },
  { value: "time_sensitive", label: "Time-sensitive" },
  { value: "conflict", label: "Conflicts" },
];

const VERDICT_DOT = {
  TRUE: "bg-emerald-400",
  FALSE: "bg-rose-400",
  PARTIALLY_TRUE: "bg-amber-400",
  UNVERIFIABLE: "bg-slate-400",
};

function getFilterCount(filter, results) {
  if (filter.value === "all") {
    return results.length;
  }
  if (filter.value === "time_sensitive") {
    return results.filter((result) => result.time_sensitive).length;
  }
  if (filter.value === "conflict") {
    return results.filter((result) => result.conflict_detected).length;
  }
  return results.filter((result) => result.verdict === filter.value).length;
}

function ClaimNavigator({
  results,
  allResults,
  activeFilter,
  onFilterChange,
  selectedClaimId,
  onSelectClaimId,
}) {
  return (
    <aside className="glass-card-static rounded-[1.75rem] p-5 animate-slide-in-left">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Claim navigator</p>
      <h3 className="mt-2 text-xl font-semibold text-white">Review one at a time</h3>
      <p className="mt-2 text-sm leading-6 text-slate-400">
        Filter and select a single claim to inspect its verdict, evidence, and risk flags.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            onClick={() => onFilterChange(filter.value)}
            className={`rounded-full px-3 py-2 text-xs font-medium uppercase tracking-[0.16em] transition-all duration-300 ${
              activeFilter === filter.value
                ? "bg-white text-slate-950 shadow-lg shadow-slate-950/10"
                : "glass-pill text-slate-300 hover:bg-white/10 hover:text-white"
            }`}
          >
            {filter.label} {getFilterCount(filter, allResults)}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-2">
        {results.length ? (
          results.map((result) => (
            <button
              key={result.claim_id}
              type="button"
              onClick={() => onSelectClaimId(result.claim_id)}
              className={`group block w-full rounded-[1.2rem] border px-4 py-3 text-left transition-all duration-300 ${
                selectedClaimId === result.claim_id
                  ? "border-blue-400/25 bg-blue-500/10 shadow-lg shadow-blue-950/10 glow-blue"
                  : "border-white/6 bg-white/4 hover:border-white/12 hover:bg-white/8"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${VERDICT_DOT[result.verdict] || VERDICT_DOT.UNVERIFIABLE}`} />
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">
                    {result.verdict.replace(/_/g, " ")}
                  </p>
                </div>
                <p className="font-mono text-xs font-medium text-slate-400">
                  {Math.round((result.confidence || 0) * 100)}%
                </p>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-200 group-hover:text-white transition-colors">{result.claim}</p>
            </button>
          ))
        ) : (
          <div className="rounded-[1.2rem] border border-dashed border-white/8 bg-white/3 px-4 py-4 text-sm text-slate-400">
            No claims match this filter.
          </div>
        )}
      </div>
    </aside>
  );
}

export default ClaimNavigator;
