import ClaimCard from "./ClaimCard";

const VERDICT_META = {
  TRUE: {
    label: "True",
    badge: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
    bar: "bg-gradient-to-r from-emerald-500 to-emerald-400",
  },
  FALSE: {
    label: "False",
    badge: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
    bar: "bg-gradient-to-r from-rose-500 to-rose-400",
  },
  PARTIALLY_TRUE: {
    label: "Partially true",
    badge: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
    bar: "bg-gradient-to-r from-amber-500 to-amber-400",
  },
  UNVERIFIABLE: {
    label: "Unverifiable",
    badge: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
    bar: "bg-gradient-to-r from-slate-500 to-slate-400",
  },
};

function StatCard({ label, value, helper }) {
  return (
    <div className="glass-card rounded-[1.4rem] px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold text-white sm:text-3xl">{value}</p>
      <p className="mt-2 text-sm text-slate-400">{helper}</p>
    </div>
  );
}

function AccuracyReport({ results, claims }) {
  const totalClaims = claims.length;
  const verifiedCount = results.length;
  const claimMap = claims.reduce((accumulator, claim) => {
    accumulator[claim.id] = claim;
    return accumulator;
  }, {});
  const counts = results.reduce(
    (accumulator, result) => ({
      ...accumulator,
      [result.verdict]: (accumulator[result.verdict] || 0) + 1,
    }),
    { TRUE: 0, FALSE: 0, PARTIALLY_TRUE: 0, UNVERIFIABLE: 0 },
  );

  const claimTypeCounts = claims.reduce((accumulator, claim) => {
    const key = claim.claim_type || "entity";
    return { ...accumulator, [key]: (accumulator[key] || 0) + 1 };
  }, {});

  const decisiveCount = counts.TRUE + counts.FALSE;
  const decisiveRate = verifiedCount ? Math.round((decisiveCount / verifiedCount) * 100) : 0;
  const timeSensitiveCount = claims.filter((claim) => claim.time_sensitive).length;
  const conflictCount = results.filter((result) => result.conflict_detected).length;
  const avgConfidence = verifiedCount
    ? Math.round(
        (results.reduce((sum, result) => sum + (result.confidence || 0), 0) / verifiedCount) * 100,
      )
    : 0;
  const sourceTotals = results.reduce(
    (totals, result) => ({
      authoritative: totals.authoritative + (result.retrieval_summary?.authoritative_count || 0),
      dated: totals.dated + (result.retrieval_summary?.dated_count || 0),
      sources: totals.sources + (result.retrieval_summary?.source_count || 0),
    }),
    { authoritative: 0, dated: 0, sources: 0 },
  );
  const authorityCoverage = sourceTotals.sources
    ? Math.round((sourceTotals.authoritative / sourceTotals.sources) * 100)
    : 0;
  const datedCoverage = sourceTotals.sources
    ? Math.round((sourceTotals.dated / sourceTotals.sources) * 100)
    : 0;

  // Weighted credibility score: TRUE=1.0, PARTIALLY_TRUE=0.5, UNVERIFIABLE=0.2, FALSE=0
  const credibilityScore = verifiedCount
    ? Math.round(
        ((counts.TRUE * 1.0 + counts.PARTIALLY_TRUE * 0.5 + counts.UNVERIFIABLE * 0.2) / verifiedCount) *
          (avgConfidence / 100) *
          100,
      )
    : 0;
  const credibilityColor =
    credibilityScore >= 70
      ? { text: "text-emerald-300", badge: "bg-emerald-500/12 ring-1 ring-inset ring-emerald-400/20 text-emerald-200", label: "High credibility" }
      : credibilityScore >= 40
      ? { text: "text-amber-300", badge: "bg-amber-500/12 ring-1 ring-inset ring-amber-400/20 text-amber-200", label: "Moderate credibility" }
      : { text: "text-rose-300", badge: "bg-rose-500/12 ring-1 ring-inset ring-rose-400/20 text-rose-200", label: "Low credibility" };

  return (
    <section className="glass-card-static rounded-[2rem] p-4 animate-fade-in-up gradient-border sm:p-6">
      <div className="flex flex-col gap-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-blue-300">Accuracy report</p>
          <h2 className="mt-2 font-display text-3xl text-white sm:text-4xl">Evidence-backed claim map</h2>
          <p className="mt-3 text-sm leading-7 text-slate-400">
            {totalClaims} claims extracted, {verifiedCount} verified. Highlights where evidence is strong, where sources disagree, and where claims remain risky.
          </p>
        </div>

        <div className="flex flex-col gap-4 sm:flex-row">
          {verifiedCount > 0 ? (
            <div className="glass-card rounded-[1.5rem] px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Credibility score</p>
              <p className={`mt-2 font-mono text-3xl font-semibold sm:text-4xl ${credibilityColor.text}`}>{credibilityScore}%</p>
              <span className={`mt-2 inline-block rounded-full px-3 py-1 text-xs font-medium ${credibilityColor.badge}`}>{credibilityColor.label}</span>
            </div>
          ) : null}
          <div className="glass-card rounded-[1.5rem] px-4 py-4 sm:px-5">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Decisive verdicts</p>
            <p className="mt-2 font-mono text-3xl font-semibold text-white sm:text-4xl">{decisiveRate}%</p>
            <p className="mt-2 text-sm text-slate-400">Claims judged true or false.</p>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {Object.entries(VERDICT_META).map(([verdict, meta]) => (
          <span key={verdict} className={`rounded-full px-3 py-1.5 text-xs font-medium sm:px-4 sm:py-2 sm:text-sm ${meta.badge}`}>
            {meta.label}: {counts[verdict]}
          </span>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatCard label="Time-sensitive" value={timeSensitiveCount} helper="Need recent evidence." />
        <StatCard label="Conflicts" value={conflictCount} helper="Supporting + conflicting evidence." />
        <StatCard label="Avg confidence" value={`${avgConfidence}%`} helper="Across all verified claims." />
        <StatCard label="Dated sources" value={`${datedCoverage}%`} helper="Sources with publication dates." />
      </div>

      <div className="mt-4 glass-card rounded-[1.5rem] p-4 text-sm text-slate-400">
        Authority coverage: <span className="font-semibold text-white">{authorityCoverage}%</span>
      </div>

      <div className="mt-6 glass-card rounded-[1.5rem] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
          <span>Verdict distribution</span>
          <span className="font-mono">{verifiedCount} verified</span>
        </div>
        <div className="flex h-3 overflow-hidden rounded-full bg-slate-800/60">
          {Object.entries(VERDICT_META).map(([verdict, meta]) => {
            const width = verifiedCount ? (counts[verdict] / verifiedCount) * 100 : 0;
            return (
              <div
                key={verdict}
                className={`${meta.bar} transition-all duration-700`}
                style={{ width: `${width}%` }}
                title={`${meta.label}: ${counts[verdict]}`}
              />
            );
          })}
        </div>
      </div>

      {Object.keys(claimTypeCounts).length ? (
        <div className="mt-6 glass-card rounded-[1.5rem] p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
            <span>Claim mix</span>
            <span className="font-mono">{totalClaims} extracted</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(claimTypeCounts).map(([claimType, count]) => (
              <span key={claimType} className="glass-pill rounded-full px-4 py-2 text-sm text-slate-300">
                {claimType.replace(/_/g, " ")}: {count}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-8 space-y-5">
        {results.map((result, index) => (
          <div key={result.claim_id} className={`animate-fade-in-up delay-${Math.min(index + 1, 6)}`}>
            <ClaimCard
              anchorId={`claim-${result.claim_id}`}
              result={result}
              claim={claimMap[result.claim_id]}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

export default AccuracyReport;
