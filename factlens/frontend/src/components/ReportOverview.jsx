import { AlertCircle, CheckCircle2, Clock, Globe, Youtube, FileText, Zap } from "lucide-react";
import {
  formatSessionDate,
  getFreshestEvidence,
  getSessionStats,
  getSessionTitle,
} from "../lib/sessions";

const VERDICT_META = {
  TRUE: { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20", glow: "glow-emerald" },
  FALSE: { color: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/20", glow: "glow-rose" },
  PARTIALLY_TRUE: { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20", glow: "glow-amber" },
  UNVERIFIABLE: { color: "text-neutral-400", bg: "bg-neutral-500/10", border: "border-neutral-500/20", glow: "" },
};

function StatItem({ icon: Icon, label, value, colorClass = "text-white" }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-neutral-500" />
        <span className="label-cap !text-[9px]">{label}</span>
      </div>
      <p className={`text-3xl font-bold tabular-nums tracking-tighter ${colorClass}`}>{value}</p>
    </div>
  );
}

function ReportOverview({ session }) {
  const stats = getSessionStats(session);
  const credibilityScore = Math.round((stats.counts.TRUE / (stats.totalClaims || 1)) * 100);
  
  const sourceIcon = {
    youtube: <Youtube className="h-4 w-4" />,
    url: <Globe className="h-4 w-4" />,
    text: <FileText className="h-4 w-4" />,
  }[session.inputMode || "text"];

  const sourceLabel = {
    youtube: "YouTube Transcript",
    url: "Web Article",
    text: "Pasted Text",
  }[session.inputMode || "text"];

  return (
    <section className="animate-fade-in-up space-y-10">
      <div className="flex flex-col items-start justify-between gap-8 lg:flex-row lg:items-end">
        <div className="space-y-4 max-w-2xl">
          <div className="flex items-center gap-3">
             <div className="flex items-center gap-2 rounded-full border border-white/5 bg-white/5 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-neutral-400">
                {sourceIcon}
                {sourceLabel}
             </div>
             <div className="flex items-center gap-2 rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-blue-400">
                <Zap className="h-3 w-3 fill-current" />
                AI VERIFIED
             </div>
          </div>
          
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl text-gradient-blue">
            {getSessionTitle(session)}
          </h1>
          
          <p className="text-lg text-neutral-400 leading-relaxed">
            Verification generated on {formatSessionDate(session.createdAt)}. analyzed {stats.totalClaims} atomic claims with cross-reference searches.
          </p>
        </div>

        <div className="glass-card-static glass-card-inner-glow flex flex-col items-center justify-center p-8 text-center ring-1 ring-white/5 lg:p-10">
           <div className="text-6xl font-black tracking-tighter text-white sm:text-7xl">
              {credibilityScore}%
           </div>
           <div className="mt-2 text-[10px] font-bold uppercase tracking-[0.3em] text-blue-400">
              Credibility Score
           </div>
        </div>
      </div>

      <div className="glass-card glass-card-inner-glow border-white/5 bg-neutral-900/40 px-8 py-10 sm:px-10">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4 lg:gap-12">
          <StatItem icon={CheckCircle2} label="TRUE" value={stats.counts.TRUE} colorClass="text-emerald-400" />
          <StatItem icon={AlertCircle} label="FALSE" value={stats.counts.FALSE} colorClass="text-rose-400" />
          <StatItem icon={Clock} label="NEEDS REVIEW" value={stats.unresolvedCount} colorClass="text-amber-400" />
          <StatItem icon={Clock} label="FRESHNESS" value={getFreshestEvidence(session.results)} />
        </div>
      </div>
    </section>
  );
}

export default ReportOverview;
