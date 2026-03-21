import { AlertTriangle, CheckCircle2, Clock3, SearchCheck } from "lucide-react";

import {
  formatSessionDate,
  getFreshestEvidence,
  getSessionStats,
  getSessionTitle,
} from "../lib/sessions";

const VERDICT_META = {
  TRUE: { badge: "bg-emerald-500/12 text-emerald-200 ring-1 ring-inset ring-emerald-400/20", glow: "glow-emerald" },
  FALSE: { badge: "bg-rose-500/12 text-rose-200 ring-1 ring-inset ring-rose-400/20", glow: "glow-rose" },
  PARTIALLY_TRUE: { badge: "bg-amber-500/12 text-amber-200 ring-1 ring-inset ring-amber-400/20", glow: "glow-amber" },
  UNVERIFIABLE: { badge: "bg-slate-500/12 text-slate-200 ring-1 ring-inset ring-slate-400/20", glow: "glow-slate" },
};

function SummaryCard({ icon: Icon, label, value, helper, delay = "" }) {
  return (
    <div className={`glass-card rounded-[1.4rem] px-4 py-4 sm:px-5 sm:py-5 animate-fade-in-up ${delay}`}>
      <div className="flex items-center gap-2 text-slate-400">
        <Icon className="h-4 w-4 shrink-0" />
        <p className="text-xs font-semibold uppercase tracking-[0.2em]">{label}</p>
      </div>
      <p className="mt-2 font-mono text-2xl font-semibold text-white sm:mt-3 sm:text-3xl">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">{helper}</p>
    </div>
  );
}

function getNarrative(stats) {
  if (stats.verifiedCount === 0) {
    return "No claim reached a completed verdict yet.";
  }
  if (stats.conflictCount > 0) {
    return "Conflicting evidence surfaced. Review disputed claims before treating this report as settled.";
  }
  if (stats.unresolvedCount > 0) {
    return "Several claims require manual review because available evidence stayed partial or unverifiable.";
  }
  return "This run resolved its extracted claims cleanly with no unresolved verdicts.";
}

function ReportOverview({ session }) {
  const stats = getSessionStats(session);

  return (
    <section className="glass-card-static rounded-[2rem] p-4 animate-fade-in-up gradient-border sm:p-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Saved report</p>
          <h1 className="mt-2 text-2xl font-semibold text-white sm:text-3xl">
            {getSessionTitle(session)}
          </h1>
          <p className="mt-3 text-sm leading-7 text-slate-400">
            Created {formatSessionDate(session.createdAt)} from {session.inputMode === "url" ? "an article URL" : "pasted text"}. {getNarrative(stats)}
          </p>
        </div>

        <div className="glass-card w-full rounded-[1.5rem] px-4 py-4 sm:px-5 xl:w-auto xl:max-w-md">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Review posture</p>
          <p className="mt-2 text-xl font-semibold text-white sm:text-2xl">
            {stats.conflictCount > 0 ? "Needs careful review" : stats.unresolvedCount > 0 ? "Mostly resolved" : "Clean pass"}
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            {stats.totalClaims} extracted, {stats.verifiedCount} with completed verdicts.
          </p>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2 sm:gap-3">
        {Object.entries(stats.counts).map(([verdict, count]) => (
          <span
            key={verdict}
            className={`rounded-full px-3 py-1.5 text-xs font-medium sm:px-4 sm:py-2 sm:text-sm ${(VERDICT_META[verdict] || VERDICT_META.UNVERIFIABLE).badge}`}
          >
            {verdict.replace(/_/g, " ")}: {count}
          </span>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <SummaryCard icon={SearchCheck} label="Verified" value={stats.verifiedCount} helper="Claims with completed verdicts." delay="delay-1" />
        <SummaryCard icon={AlertTriangle} label="Needs review" value={stats.unresolvedCount} helper="Partial or unverifiable claims." delay="delay-2" />
        <SummaryCard icon={Clock3} label="Freshest evidence" value={getFreshestEvidence(session.results)} helper="Newest publication date found." delay="delay-3" />
        <SummaryCard icon={CheckCircle2} label="Time-sensitive" value={stats.timeSensitiveCount} helper="Claims needing recency care." delay="delay-4" />
      </div>
    </section>
  );
}

export default ReportOverview;
