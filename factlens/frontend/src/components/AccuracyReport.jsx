import ClaimCard from "./ClaimCard";
import { Link } from "react-router-dom";
import { getAverageResultConfidence, getCredibilityScore } from "../lib/sessions";

const VERDICT_META = {
  TRUE: {
    label: "Verify True",
    badge: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20",
    bar: "bg-gradient-to-r from-emerald-500 to-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.3)]",
  },
  FALSE: {
    label: "Factually False",
    badge: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20",
    bar: "bg-gradient-to-r from-rose-500 to-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.3)]",
  },
  PARTIALLY_TRUE: {
    label: "Partially True",
    badge: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20",
    bar: "bg-gradient-to-r from-amber-500 to-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.3)]",
  },
  UNVERIFIABLE: {
    label: "Unverifiable",
    badge: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20",
    bar: "bg-gradient-to-r from-slate-500 to-slate-400",
  },
};

function StatCard({ label, value, helper, delay }) {
  return (
    <div className={`glass-card rounded-3xl p-6 space-y-3 animate-fade-in-up ${delay}`}>
      <p className="label-cap">{label}</p>
      <div className="flex items-baseline gap-2">
        <p className="font-display text-3xl font-bold text-white">{value}</p>
      </div>
      <p className="text-xs leading-relaxed" style={{ color: "var(--ink-2)" }}>{helper}</p>
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

  const avgConfidence = Math.round(getAverageResultConfidence(results) * 100);
  const credibilityScore = getCredibilityScore(results);

  const credibilityColor =
    credibilityScore >= 70
      ? { text: "text-emerald-400", glow: "glow-emerald", label: "High Integrity" }
      : credibilityScore >= 40
      ? { text: "text-amber-400", glow: "glow-amber", label: "Mixed Consensus" }
      : { text: "text-rose-400", glow: "glow-rose", label: "Low Integrity" };


  return (
    <section className="animate-fade-in space-y-12">
      {/* ── Summary Hub ───────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Score Card */}
        {verifiedCount > 0 && (
          <div className={`glass-card rounded-[2rem] p-8 flex flex-col justify-between ${credibilityColor.glow}`}>
            <div className="space-y-4">
              <span className="label-cap">Credibility Score</span>
              <div className="flex flex-col">
                <span className={`font-display text-7xl font-bold shimmer-text leading-tight ${credibilityColor.text}`}>
                  {credibilityScore}%
                </span>
                <span className={`mt-2 text-sm font-bold uppercase tracking-widest ${credibilityColor.text}`}>
                  {credibilityColor.label}
                </span>
              </div>
            </div>
            <p className="mt-8 text-xs leading-relaxed" style={{ color: "var(--ink-2)" }}>
              A weighted blend of the verdict mix and the average verification confidence across analyzed claims.
            </p>
          </div>
        )}

        {/* Breakdown Stats */}
        <div className="grid gap-4 sm:grid-cols-2">
          {Object.entries(VERDICT_META).map(([verdict, meta], i) => (
            <div key={verdict} className={`glass-card rounded-3xl p-6 flex items-center justify-between group animate-fade-in-up delay-${i + 1}`}>
              <div className="space-y-1">
                <p className="text-xs font-bold uppercase tracking-widest" style={{ color: "var(--ink-3)" }}>{meta.label}</p>
                <p className="text-2xl font-bold text-white group-hover:text-blue-300 transition-colors uppercase tracking-widest">
                  {counts[verdict]}
                </p>
              </div>
              <div className={`h-1.5 w-12 rounded-full ${meta.bar}`} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Advanced Signals ───────────────────────────────────── */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard label="Time sensitive" value={claims.filter(c => c.time_sensitive).length} helper="Temporal risk detected." delay="delay-1" />
        <StatCard label="Conflicts" value={results.filter(r => r.conflict_detected).length} helper="Dueling evidence paths." delay="delay-2" />
        <StatCard label="Confidence" value={`${avgConfidence}%`} helper="Mean heuristic certainty." delay="delay-3" />
        <StatCard label="Dated Sources" value={`${verifiedCount ? Math.round((results.reduce((s,r)=>s+(r.retrieval_summary?.dated_count||0),0) / results.reduce((s,r)=>s+(r.retrieval_summary?.source_count||1),0)) * 100) : 0}%`} helper="Temporal traceability rate." delay="delay-4" />
      </div>

      {/* ── Visual Map ────────────────────────────────────────── */}
      <div className="space-y-8">
        <div className="glass-card-static rounded-3xl p-8 space-y-8">
          <div className="flex items-center justify-between">
            <h3 className="label-cap text-blue-400">Verdict Distribution Map</h3>
            <span className="text-xs font-mono" style={{ color: "var(--ink-3)" }}>{verifiedCount} claims analyzed</span>
          </div>
          
          <div className="space-y-4">
            <div className="flex h-4 overflow-hidden rounded-full bg-white/5 shadow-inner">
              {Object.entries(VERDICT_META).map(([verdict, meta]) => {
                const width = verifiedCount ? (counts[verdict] / verifiedCount) * 100 : 0;
                return (
                  <div
                    key={verdict}
                    className={`${meta.bar} transition-all duration-1000 ease-in-out`}
                    style={{ width: `${width}%` }}
                  />
                );
              })}
            </div>
            
            <div className="flex flex-wrap gap-4 px-1">
              {Object.entries(VERDICT_META).map(([verdict, meta]) => (
                <div key={verdict} className="flex items-center gap-2">
                  <div className={`h-1.5 w-1.5 rounded-full ${meta.bar.split(' ')[0]}`} />
                  <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: "var(--ink-2)" }}>
                    {meta.label}: {Math.round(verifiedCount ? (counts[verdict]/verifiedCount)*100 : 0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Individual Claims */}
        <div className="space-y-6">
          <div className="flex items-center gap-4 px-2">
            <span className="label-cap text-blue-400 shrink-0">Verification Trail</span>
            <div className="h-px w-full bg-gradient-to-r from-blue-400/20 to-transparent" />
          </div>
          <div className="space-y-4">
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
        </div>
      </div>
    </section>
  );
}

export default AccuracyReport;
